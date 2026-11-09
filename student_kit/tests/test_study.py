import io
import json

import pytest
from reportlab.pdfgen import canvas

from student_kit.core.ai_client import AIClient, DemoClient
from student_kit.core.flashcards import (
    _parse_json_list,
    generate_flashcards,
    generate_quiz,
    rate_flashcard,
    randomize_quiz_options,
    validate_flashcard,
    validate_quiz_question,
)
from student_kit.core.pdf_reader import PDFExtractionError, extract_text_from_pdf, split_text
from student_kit.core.storage import StudentStorage


def make_pdf(text: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 720, text)
    document.save()
    return output.getvalue()


def test_extract_text_from_pdf():
    extracted = extract_text_from_pdf(make_pdf("La mémoire active améliore les révisions."))
    assert "mémoire active" in extracted


def test_scanned_or_empty_pdf_has_explicit_error():
    with pytest.raises(PDFExtractionError, match="scanné|texte"):
        extract_text_from_pdf(make_pdf(""))


def test_split_text_has_overlap():
    chunks = split_text("abcdefghijklmnopqrstuvwxyz" * 4, chunk_size=30, overlap=5)
    assert len(chunks) > 1
    assert chunks[0][-5:] == chunks[1][:5]


def test_demo_generation_is_based_on_source_and_valid():
    source = "La mémoire active améliore les révisions. La répétition espacée aide la mémorisation."
    cards = generate_flashcards(source, client=DemoClient(), count=2)
    assert len(cards) == 2
    assert all("Réponse reprise directement" in card["explanation"] for card in cards)
    assert all("La mémoire active" in card["answer"] or "La répétition" in card["answer"] for card in cards)


def test_flashcard_and_quiz_validation():
    card = validate_flashcard({"question": "Q", "answer": "R", "explanation": "E"})
    assert card["question"] == "Q"
    with pytest.raises(ValueError):
        validate_flashcard({"question": "Q", "answer": "R"})
    quiz = validate_quiz_question(
        {
            "question": "Q",
            "options": ["A", "B"],
            "correct_answer": "A",
            "explanation": "E",
        }
    )
    assert quiz["correct_answer"] == "A"
    with pytest.raises(ValueError):
        validate_quiz_question(
            {"question": "Q", "options": ["A", "B"], "correct_answer": "C", "explanation": "E"}
        )
    multi = validate_quiz_question(
        {
            "question": "QCM multiple",
            "options": ["A", "B", "C"],
            "correct_answer": ["A", "C"],
            "explanation": "E",
        }
    )
    assert multi["correct_answers"] == ["A", "C"]


def test_quiz_options_are_reordered_without_changing_correct_answer():
    question = {
    "question": "Quelle option est correcte ?",
    "options": ["Bonne réponse", "Distracteur A", "Distracteur B"],
    "correct_answer": "Bonne réponse",
    "explanation": "Justification issue du document.",
    }
    randomized = randomize_quiz_options(question)
    assert set(randomized["options"]) == set(question["options"])
    assert randomized["correct_answer"] == question["correct_answer"]
    assert randomized["options"][0] != randomized["correct_answer"]
    assert randomize_quiz_options(question) == randomized


def test_demo_quiz_has_a_non_first_correct_answer():
    quiz = generate_quiz(
    "La mémoire active améliore les révisions. "
    "La répétition espacée aide la mémorisation.",
    client=DemoClient(),
    count=2,
    )
    assert quiz
    assert all(
        all(answer in item["options"] for answer in item["correct_answers"])
        for item in quiz
    )
    assert all(
        item["options"][0] not in item["correct_answers"] for item in quiz
    )


def test_invalid_quiz_answer_is_rejected():
    with pytest.raises(ValueError):
        validate_quiz_question(
            {
                "question": "Q",
                "options": ["A", "B"],
                "correct_answer": ["A", "C"],
                "explanation": "E",
            }
        )


def test_quiz_with_unrelated_explanation_is_rejected_from_generation():
    class UnsupportedClient(AIClient):
        def generate(self, prompt: str) -> str:
            return json.dumps(
                [
                    {
                        "question": "What is a router?",
                        "options": ["Connects two networks", "Sends to all ports"],
                        "correct_answer": "Connects two networks",
                        "explanation": "A router is sophisticated.",
                    }
                ]
            )

    with pytest.raises(ValueError, match="justif"):
        generate_quiz("A router connects two networks.", UnsupportedClient(), count=1)


def test_review_and_local_storage(tmp_path):
    card = rate_flashcard(
        {"question": "Q", "answer": "R", "explanation": "E"}, "Bien maîtrisé"
    )
    storage = StudentStorage(tmp_path / "student_data.json")
    from student_kit.core.flashcards import save_flashcards

    save_flashcards(storage, [card])
    reloaded = StudentStorage(tmp_path / "student_data.json")
    assert reloaded.data["flashcards"][0]["rating"] == "Bien maîtrisé"
    with pytest.raises(ValueError):
        rate_flashcard(card, "Inconnu")


def test_unrated_flashcard_stays_unrated_until_reviewed():
    card = {"question": "Q", "answer": "R", "explanation": "E"}
    assert "rating" not in card
    assert rate_flashcard(card, "À revoir")["rating"] == "À revoir"


class FixedClient(AIClient):
    def generate(self, prompt: str) -> str:
        return json.dumps(
            [{"question": "Q", "answer": "A", "explanation": "Source"}],
            ensure_ascii=False,
        )


def test_malformed_provider_response_is_rejected():
    class BadClient(AIClient):
        def generate(self, prompt: str) -> str:
            return "not-json"

    with pytest.raises(ValueError, match="JSON"):
        generate_flashcards("Un texte suffisamment long pour être exploitable.", BadClient())


def test_json_parser_accepts_markdown_fence_and_surrounding_text():
    raw = 'Voici le résultat :\n```json\n[{"question":"Q","answer":"A","explanation":"E"}]\n```\n'
    assert _parse_json_list(raw)[0]["question"] == "Q"


def test_json_parser_accepts_ollama_object_wrapper():
    raw = '{"flashcards":[{"question":"Q","answer":"A","explanation":"E"}]}'
    assert _parse_json_list(raw)[0]["answer"] == "A"


def test_json_parser_rejects_unknown_object_wrapper():
    with pytest.raises(ValueError, match="objet JSON"):
        _parse_json_list('{"result":[{"question":"Q"}]}')


def test_json_parser_flattens_topic_mapping_with_lists():
    raw = json.dumps(
        {
            "osi model": [
                {"question": "Q", "answer": "A", "explanation": "E"}
            ],
            "network basics": [],
        }
    )
    assert _parse_json_list(raw)[0]["question"] == "Q"


def test_json_parser_still_rejects_incomplete_json():
    with pytest.raises(ValueError, match="JSON mal formé"):
        _parse_json_list("```json\n[{\"question\": \"Q\"}\n```")
