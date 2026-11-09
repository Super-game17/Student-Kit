"""Point d'entrée Streamlit de StudentKit."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import streamlit as st

from student_kit.core.ai_client import AIClientError, get_ai_client
from student_kit.core.exporters import export_flashcards_csv, export_schedule_pdf
from student_kit.core.flashcards import (
    REVIEW_RATINGS,
    generate_flashcards,
    generate_quiz,
    rate_flashcard,
    save_flashcards,
)
from student_kit.core.pdf_reader import PDFExtractionError, extract_text_from_pdf
from student_kit.core.planner import generate_schedule
from student_kit.core.storage import StudentStorage

st.set_page_config(page_title="StudentKit", page_icon="📚", layout="wide")

WEEKDAYS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")


@st.cache_resource
def get_storage() -> StudentStorage:
    return StudentStorage()


def persist(storage: StudentStorage) -> None:
    storage.save()
    st.session_state["storage_version"] = st.session_state.get("storage_version", 0) + 1


def render_home(storage: StudentStorage) -> None:
    st.title("📚 StudentKit")
    st.caption("Organisez vos révisions et transformez vos cours en supports d'apprentissage.")
    today = date.today().isoformat()
    upcoming = sorted(
        [subject for subject in storage.data["subjects"] if subject.get("exam_date", "") >= today],
        key=lambda subject: subject.get("exam_date", ""),
    )
    sessions_today = [session for session in storage.data["sessions"] if session.get("date") == today]
    sessions = storage.data["sessions"]
    progress = sum(bool(session.get("completed")) for session in sessions) / len(sessions) if sessions else 0
    columns = st.columns(3)
    columns[0].metric("Prochains examens", len(upcoming))
    columns[1].metric("Sessions aujourd'hui", len(sessions_today))
    columns[2].metric("Progression globale", f"{progress:.0%}")
    st.progress(progress)
    left, right = st.columns(2)
    with left:
        st.subheader("Prochains examens")
        if upcoming:
            for subject in upcoming[:5]:
                st.write(f"**{subject.get('name', 'Matière')}** — {subject.get('exam_date')}")
        else:
            st.info("Aucun examen planifié.")
    with right:
        st.subheader("Sessions du jour")
        if sessions_today:
            for session in sessions_today:
                status = "✅" if session.get("completed") else "⬜"
                st.write(f"{status} {session.get('subject_name', 'Matière')} ({session.get('duration_minutes', 50)} min)")
        else:
            st.info("Aucune session prévue aujourd'hui.")
    st.subheader("Dernières ressources")
    cards = storage.data.get("flashcards", [])
    st.write(f"{len(cards)} flashcard(s) sauvegardée(s) localement.")


def render_planner(storage: StudentStorage) -> None:
    st.title("🗓️ Planner")
    subjects = storage.data["subjects"]
    with st.expander("Ajouter une matière", expanded=not subjects):
        with st.form("subject_form", clear_on_submit=True):
            name = st.text_input("Nom de la matière")
            exam_date = st.date_input("Date d'examen", min_value=date.today())
            difficulty = st.slider("Difficulté", 1, 5, 3)
            volume = st.number_input("Chapitres / unités restantes", min_value=0.0, value=4.0, step=1.0)
            mastery = st.slider("Niveau de maîtrise", 1, 5, 2)
            if st.form_submit_button("Ajouter"):
                if not name.strip():
                    st.error("Le nom de la matière est obligatoire.")
                else:
                    storage.add_subject({
                        "id": str(uuid.uuid4()), "name": name.strip(),
                        "exam_date": exam_date.isoformat(), "difficulty": difficulty,
                        "remaining_volume": volume, "mastery": mastery,
                    })
                    st.success("Matière ajoutée.")
                    st.rerun()
    if subjects:
        st.subheader("Matières")
        for subject in subjects:
            label = f"{subject['name']} — examen {subject['exam_date']}"
            with st.expander(label):
                st.write(f"Difficulté : {subject.get('difficulty', 1)}/5 · Volume : {subject.get('remaining_volume', 0)} · Maîtrise : {subject.get('mastery', 1)}/5")
                if st.button("Supprimer", key=f"delete_{subject['id']}"):
                    storage.remove_subject(subject["id"])
                    persist(storage)
                    st.rerun()
        with st.expander("Modifier une matière"):
            selected_id = st.selectbox(
                "Matière à modifier",
                [subject["id"] for subject in subjects],
                format_func=lambda subject_id: next(
                    item["name"] for item in subjects if item["id"] == subject_id
                ),
            )
            selected = next(subject for subject in subjects if subject["id"] == selected_id)
            with st.form("edit_subject_form"):
                edited_name = st.text_input("Nom", value=selected.get("name", ""))
                edited_exam_date = st.date_input(
                    "Date d'examen",
                    value=date.fromisoformat(selected["exam_date"]),
                )
                edited_difficulty = st.slider(
                    "Difficulté", 1, 5, int(selected.get("difficulty", 3)), key="edit_difficulty"
                )
                edited_volume = st.number_input(
                    "Chapitres / unités restantes",
                    min_value=0.0,
                    value=float(selected.get("remaining_volume", 0)),
                    step=1.0,
                    key="edit_volume",
                )
                edited_mastery = st.slider(
                    "Niveau de maîtrise", 1, 5, int(selected.get("mastery", 2)), key="edit_mastery"
                )
                if st.form_submit_button("Enregistrer les modifications"):
                    if not edited_name.strip():
                        st.error("Le nom de la matière est obligatoire.")
                    else:
                        storage.update_subject(
                            selected_id,
                            {
                                "name": edited_name.strip(),
                                "exam_date": edited_exam_date.isoformat(),
                                "difficulty": edited_difficulty,
                                "remaining_volume": edited_volume,
                                "mastery": edited_mastery,
                            },
                        )
                        st.success("Matière modifiée.")
                        st.rerun()
    st.subheader("Disponibilités quotidiennes")
    with st.form("availability_form"):
        availability = {
            str(index): st.number_input(day, min_value=0.0, max_value=12.0, value=float(storage.data["availability"].get(str(index), 0)), step=1.0)
            for index, day in enumerate(WEEKDAYS)
        }
        if st.form_submit_button("Enregistrer les disponibilités"):
            storage.data["availability"] = availability
            persist(storage)
            st.success("Disponibilités enregistrées.")
    if st.button("Générer le planning", type="primary"):
        storage.data["sessions"] = generate_schedule(
            subjects, storage.data["availability"], date.today()
        )
        persist(storage)
        if storage.data["sessions"]:
            st.success(
                f"Planning généré : {len(storage.data['sessions'])} session(s)."
            )
        else:
            st.warning(
                "Aucune session n'a été créée. Vérifiez que les matières ont "
                "un volume restant, une date d'examen future et au moins une "
                "heure de disponibilité avant l'examen."
            )
    sessions = storage.data["sessions"]
    if sessions:
        st.subheader("Planning")
        for session in sessions:
            status = "Terminée" if session.get("completed") else "À faire"
            columns = st.columns([2, 4, 2, 2])
            columns[0].write(session.get("date"))
            columns[1].write(session.get("subject_name"))
            columns[2].write(status)
            if not session.get("completed") and columns[3].button("Terminer", key=f"complete_{session['id']}"):
                storage.update_session(session["id"], {"completed": True})
                st.rerun()
        st.download_button("Exporter le planning en PDF", export_schedule_pdf(sessions), "studentkit-planning.pdf", "application/pdf")
    else:
        st.info(
            "Le planning apparaîtra ici après génération. Une session est "
            "créée uniquement les jours précédant l'examen."
        )


def render_study(storage: StudentStorage) -> None:
    st.title("🧠 Study Assistant")
    source = st.file_uploader("Importer un PDF", type=["pdf"])
    pasted = st.text_area("Ou collez le texte de votre cours", height=180)
    content = pasted.strip()
    if source is not None:
        try:
            content = extract_text_from_pdf(source.getvalue())
            st.success(f"Texte extrait ({len(content)} caractères).")
        except PDFExtractionError as error:
            st.error(str(error))
            content = ""
    subject_options = {"Aucune matière": None, **{item["name"]: item["id"] for item in storage.data["subjects"]}}
    selected_subject = st.selectbox("Associer les cartes à une matière (optionnel)", list(subject_options))
    selected_subject_id = subject_options[selected_subject]
    count = st.slider("Nombre de supports", 1, 10, 5)
    provider = st.selectbox("Mode de génération", ["demo", "ollama"], help="Le mode démo est simulé et n'affirme pas une fiabilité IA.")
    if provider == "demo":
        st.info("Mode démonstration : les supports sont générés localement à partir du texte fourni.")
    col_cards, col_quiz = st.columns(2)
    if col_cards.button("Générer des flashcards", disabled=not bool(content)):
        try:
            cards = generate_flashcards(content, get_ai_client(provider), count)
            for card in cards:
                card["subject_id"] = selected_subject_id
            st.session_state["generated_cards"] = cards
        except (ValueError, AIClientError) as error:
            st.error(str(error))
    if col_quiz.button("Générer un QCM", disabled=not bool(content)):
        try:
            st.session_state["generated_quiz"] = generate_quiz(content, get_ai_client(provider), count)
        except (ValueError, AIClientError) as error:
            st.error(str(error))
    cards = st.session_state.get("generated_cards", [])
    if cards:
        st.subheader("Flashcards")
        if st.button("Sauvegarder les flashcards"):
            save_flashcards(storage, cards)
            st.success("Flashcards sauvegardées localement.")
        st.download_button("Exporter les flashcards CSV", export_flashcards_csv(cards), "studentkit-flashcards.csv", "text/csv")
        for index, card in enumerate(cards):
            with st.expander(f"Carte {index + 1} — {card['question']}"):
                st.write(card["answer"])
                st.caption(card["explanation"])
                rating = st.radio(
                    "Évaluation",
                    sorted(REVIEW_RATINGS),
                    index=None,
                    key=f"rating_{card['id']}",
                    horizontal=True,
                )
                if rating is not None:
                    cards[index] = rate_flashcard(card, rating)
    quiz = st.session_state.get("generated_quiz", [])
    if quiz:
        st.subheader("QCM")
        for index, question in enumerate(quiz):
            correct_answers = question.get(
                "correct_answers", [question["correct_answer"]]
            )
            if len(correct_answers) > 1:
                answer = st.multiselect(
                    question["question"],
                    question["options"],
                    key=f"quiz_{index}",
                )
            else:
                answer = st.radio(
                    question["question"],
                    question["options"],
                    index=None,
                    key=f"quiz_{index}",
                )
            if st.button("Corriger", key=f"correct_{index}"):
                selected_answers = answer if isinstance(answer, list) else (
                    [answer] if answer is not None else []
                )
                if not selected_answers:
                    st.warning("Sélectionnez une réponse avant de corriger.")
                else:
                    is_correct = set(selected_answers) == set(correct_answers)
                    st.write(
                        "✅ Bonne réponse."
                        if is_correct
                        else f"❌ Réponse attendue : {', '.join(correct_answers)}"
                    )
                    st.caption(question["explanation"])
    saved_cards = storage.data.get("flashcards", [])
    if saved_cards:
        st.subheader("Révision des cartes sauvegardées")
        card = saved_cards[0]
        st.write(card["question"])
        if st.toggle("Afficher la réponse", key="show_saved_answer"):
            st.write(card["answer"])


def main() -> None:
    storage = get_storage()
    with st.sidebar:
        st.title("StudentKit")
        page = st.radio("Navigation", ["Accueil", "Planner", "Study Assistant"])
        st.caption("Données conservées localement.")
    if page == "Accueil":
        render_home(storage)
    elif page == "Planner":
        render_planner(storage)
    else:
        render_study(storage)


if __name__ == "__main__":
    main()
