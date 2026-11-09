"""Génération, validation et révision des supports d'étude."""

from __future__ import annotations

import json
import hashlib
import re
import uuid
from typing import Any, Iterable, Mapping

from .ai_client import AIClient, DemoClient
from .pdf_reader import split_text, validate_text
from .storage import StudentStorage

REVIEW_RATINGS = {"À revoir", "Difficile", "Bien maîtrisé"}


def validate_flashcard(card: Mapping[str, Any]) -> dict[str, str]:
    """Valide une carte Q/R et retourne une copie normalisée."""
    required = ("question", "answer", "explanation")
    if any(not isinstance(card.get(key), str) or not card[key].strip() for key in required):
        raise ValueError("Une flashcard doit contenir question, answer et explanation.")
    return {key: card[key].strip() for key in required}


def validate_quiz_question(question: Mapping[str, Any]) -> dict[str, Any]:
    """Valide une question QCM avec une ou plusieurs bonnes réponses."""
    prompt = question.get("question")
    options = question.get("options")
    answer = question.get("correct_answer")
    if isinstance(answer, str):
        correct_answers = [answer.strip()]
    elif isinstance(answer, list) and answer:
        correct_answers = [
            item.strip() for item in answer
            if isinstance(item, str) and item.strip()
        ]
        if len(correct_answers) != len(answer):
            correct_answers = []
    else:
        correct_answers = []
    normalized_options = (
        [option.strip() for option in options]
        if isinstance(options, list)
        and all(isinstance(option, str) and option.strip() for option in options)
        else []
    )
    explanation = question.get("explanation")
    if (
        not isinstance(prompt, str)
        or not prompt.strip()
        or not isinstance(options, list)
        or len(normalized_options) < 2
        or len(set(normalized_options)) != len(normalized_options)
        or not correct_answers
        or not all(item in normalized_options for item in correct_answers)
        or not isinstance(explanation, str)
        or not explanation.strip()
    ):
        raise ValueError(
            "Un QCM doit contenir une question, des options distinctes, "
            "une réponse correcte et une explication."
        )
    return {
        "question": prompt.strip(),
        "options": normalized_options,
        "correct_answer": (
            correct_answers[0] if len(correct_answers) == 1 else correct_answers
        ),
        "correct_answers": correct_answers,
        "explanation": explanation.strip(),
    }


def randomize_quiz_options(question: Mapping[str, Any]) -> dict[str, Any]:
    """Mélange les options de manière stable sans perdre la bonne réponse."""
    validated = validate_quiz_question(question)
    options = validated["options"]
    ranked = sorted(
        options,
        key=lambda option: hashlib.sha256(
            f"{validated['question']}\0{option}".encode("utf-8")
        ).hexdigest(),
    )
    correct_answers = validated["correct_answers"]
    if ranked[0] in correct_answers and len(ranked) > len(correct_answers):
        first_incorrect = next(option for option in ranked if option not in correct_answers)
        ranked.remove(first_incorrect)
        ranked.insert(0, first_incorrect)
    return {**validated, "options": ranked}


def _answer_is_supported_by_explanation(question: Mapping[str, Any]) -> bool:
    """Écarte une réponse dont l'explication ne contient aucun terme clé."""
    stop_words = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "in", "is", "it", "of", "on", "or", "that", "the", "this", "to",
        "un", "une", "des", "de", "du", "et", "est", "la", "le", "les",
        "que", "qui", "dans", "pour", "sur",
    }

    def keywords(value: str) -> set[str]:
        return {
            token for token in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", value.casefold())
            if token not in stop_words
        }

    answer_terms = set().union(
        *(keywords(answer) for answer in question["correct_answers"])
    )
    return bool(answer_terms & keywords(question["explanation"]))


def _parse_json_list(raw: str) -> list[dict[str, Any]]:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Le fournisseur IA a renvoyé une réponse vide.")
    candidate = raw.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        # Certains modèles ajoutent une phrase avant ou après le tableau JSON.
        # On ne récupère que le premier tableau complet, sans réparer son contenu.
        start = candidate.find("[")
        if start < 0:
            raise ValueError(
                "Le fournisseur IA a renvoyé un JSON mal formé. "
                "Réessayez ou utilisez le mode démo."
            ) from exc
        try:
            payload, _ = json.JSONDecoder().raw_decode(candidate[start:])
        except json.JSONDecodeError as nested_error:
            raise ValueError(
                "Le fournisseur IA a renvoyé un JSON mal formé. "
                "Réessayez ou utilisez le mode démo."
            ) from nested_error
    if isinstance(payload, dict):
        list_values = [
            value
            for key, value in payload.items()
            if key.casefold() in {"flashcards", "questions", "items", "data"}
            and isinstance(value, list)
        ]
        if len(list_values) == 1:
            payload = list_values[0]
        else:
            mapping_values = list(payload.values())
            flattened = [
                    item
                    for value in mapping_values
                    for item in value
                ] if mapping_values and all(isinstance(value, list) for value in mapping_values) else []
            if flattened and all(
                isinstance(item, dict)
                and {"question", "explanation"}.issubset(item)
                for item in flattened
            ):
                payload = flattened
            elif mapping_values and all(
                isinstance(value, dict)
                and {"question", "explanation"}.issubset(value)
                for value in mapping_values
            ):
                payload = mapping_values
            else:
                keys = ", ".join(str(key) for key in payload)
                raise ValueError(
                    "Le fournisseur IA a renvoyé un objet JSON au lieu d'une liste. "
                    f"Clés reçues: {keys}. Vérifiez le modèle Ollama sélectionné."
                )
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(
            "Le fournisseur IA doit renvoyer une liste JSON d'objets."
        )
    return payload


def generate_flashcards(
    text: str,
    client: AIClient | None = None,
    count: int = 5,
    chunk_size: int = 4000,
    overlap: int = 400,
) -> list[dict[str, Any]]:
    """Génère et valide des cartes à partir du texte fourni uniquement."""
    if count <= 0:
        raise ValueError("count doit être positif.")
    source = validate_text(text)
    provider = client or DemoClient()
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in split_text(source, chunk_size, overlap):
        prompt = (
            "Réponds uniquement avec un tableau JSON racine, jamais un objet JSON "
            "enveloppant ce tableau. Chaque objet contient question, answer et "
            "explanation. Les questions/réponses doivent être fondées exclusivement "
            "sur SOURCE. N'invente aucune information.\nSOURCE:\n" + chunk
        )
        for raw_card in _parse_json_list(provider.generate(prompt)):
            card = validate_flashcard(raw_card)
            key = card["question"].casefold()
            if key not in seen:
                card["id"] = str(uuid.uuid4())
                card["rating"] = None
                cards.append(card)
                seen.add(key)
            if len(cards) >= count:
                return cards
    return cards


def generate_quiz(
    text: str,
    client: AIClient | None = None,
    count: int = 5,
    chunk_size: int = 4000,
    overlap: int = 400,
) -> list[dict[str, Any]]:
    """Génère et valide des QCM ; la réponse doit faire partie des options."""
    source = validate_text(text)
    provider = client or DemoClient()
    questions: list[dict[str, Any]] = []
    for chunk in split_text(source, chunk_size, overlap):
        prompt = (
            "Réponds uniquement avec un tableau JSON racine, jamais un objet JSON "
            "enveloppant ce tableau. Chaque QCM contient question, options, "
            "correct_answer et explanation. Il doit y avoir exactement UNE seule "
            "bonne réponse par QCM : correct_answer doit être une chaîne de texte, "
            "jamais une liste, un tableau ou plusieurs réponses, et doit être "
            "copié exactement parmi les options. Les autres options doivent être "
            "des distracteurs plausibles mais fausses selon SOURCE. Si plusieurs "
            "faits sont vrais dans SOURCE, reformule la question pour ne viser "
            "qu'un seul fait et une seule option correcte ; ne crée jamais de "
            "QCM du type « sélectionnez toutes les réponses correctes ». "
            "L'explication doit justifier uniquement cette réponse à partir de "
            "SOURCE. Si le document ne permet pas de trancher avec une seule "
            "réponse, omets la question. N'invente aucune information. "
            "Format obligatoire : [{\"question\":\"...\",\"options\":[\"...\","
            "\"...\",\"...\"],\"correct_answer\":\"une seule option\","
            "\"explanation\":\"...\"}].\nSOURCE:\n" + chunk
        )
        invalid_questions = 0
        for raw_question in _parse_json_list(provider.generate(prompt)):
            try:
                candidate = randomize_quiz_options(raw_question)
                if not _answer_is_supported_by_explanation(candidate):
                    invalid_questions += 1
                    continue
                questions.append(candidate)
            except ValueError:
                invalid_questions += 1
            if len(questions) >= count:
                return questions
        if invalid_questions and not questions:
            raise ValueError(
                "Ollama a généré des QCM dont les réponses ou les justifications "
                "ne correspondent pas au document."
            )
    return questions


def rate_flashcard(card: Mapping[str, Any], rating: str) -> dict[str, Any]:
    """Ajoute une évaluation de révision sans modifier la carte d'origine."""
    if rating not in REVIEW_RATINGS:
        raise ValueError(f"Évaluation inconnue: {rating}.")
    updated = dict(card)
    updated["rating"] = rating
    return updated


def save_flashcards(storage: StudentStorage, cards: Iterable[Mapping[str, Any]]) -> None:
    """Ajoute des cartes validées dans la collection locale."""
    for card in cards:
        saved = validate_flashcard(card)
        saved.update(
            {
                key: card[key]
                for key in ("id", "rating", "subject_id")
                if key in card
            }
        )
        storage.data.setdefault("flashcards", []).append(saved)
    storage.save()
