"""Calcul déterministe des priorités et du planning de révision."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Mapping


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def calculate_priority(
    subject: Mapping[str, Any], today: date | datetime | str | None = None
) -> float:
    """Retourne une priorité stable : urgence, difficulté, volume et maîtrise.

    Une échéance passée reçoit la priorité maximale d'urgence. Les valeurs
    utilisateur sont bornées pour éviter qu'une saisie invalide déstabilise le
    classement.
    """
    reference = _as_date(today or date.today())
    exam_date = _as_date(subject["exam_date"])
    days_remaining = (exam_date - reference).days
    urgency = 10.0 if days_remaining <= 0 else 1.0 + 10.0 / (days_remaining + 1)
    difficulty = min(5.0, max(1.0, float(subject.get("difficulty", 1))))
    volume = max(0.0, float(subject.get("remaining_volume", 0)))
    mastery = min(5.0, max(1.0, float(subject.get("mastery", 1))))
    volume_factor = 1.0 + min(volume, 100.0) / 20.0
    mastery_factor = 1.0 + (5.0 - mastery) / 4.0
    return round(urgency * (difficulty / 5.0) * volume_factor * mastery_factor, 6)


def _hours_for_day(availability: Mapping[Any, Any], current: date) -> float:
    keys = (current.isoformat(), str(current.weekday()), current.weekday(), current.strftime("%A").lower())
    for key in keys:
        if key in availability:
            try:
                return max(0.0, float(availability[key]))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def generate_schedule(
    subjects: list[Mapping[str, Any]],
    availability: Mapping[Any, Any],
    start_date: date | datetime | str | None = None,
    session_minutes: int = 50,
) -> list[dict[str, Any]]:
    """Distribue des sessions avant les examens, sans dépasser les disponibilités.

    Une session consomme une heure de disponibilité (50 minutes d'étude et
    10 minutes de pause). Le résultat est trié chronologiquement et reste
    entièrement déterministe pour des entrées identiques.
    """
    if session_minutes <= 0 or session_minutes > 60:
        raise ValueError("session_minutes doit être compris entre 1 et 60.")
    current = _as_date(start_date or date.today())
    eligible = []
    for index, subject in enumerate(subjects):
        volume = max(0.0, float(subject.get("remaining_volume", 0)))
        exam_date = _as_date(subject["exam_date"])
        if volume > 0 and exam_date >= current:
            eligible.append(
                {
                    "index": index,
                    "subject": subject,
                    "exam_date": exam_date,
                    "remaining": volume,
                    "priority": calculate_priority(subject, current),
                }
            )
    if not eligible:
        return []

    end_date = max(item["exam_date"] for item in eligible)
    result: list[dict[str, Any]] = []
    while current < end_date and any(item["remaining"] > 0 for item in eligible):
        slots = int(_hours_for_day(availability, current))
        for _ in range(slots):
            candidates = [
                item for item in eligible if item["remaining"] > 0 and item["exam_date"] > current
            ]
            if not candidates:
                break
            candidates.sort(
                key=lambda item: (-item["priority"], item["exam_date"], item["index"])
            )
            chosen = candidates[0]
            chosen["remaining"] -= 1
            result.append(
                {
                    "id": f"{current.isoformat()}-{len(result) + 1}",
                    "date": current.isoformat(),
                    "subject_id": chosen["subject"].get("id"),
                    "subject_name": chosen["subject"].get("name", "Matière"),
                    "duration_minutes": session_minutes,
                    "break_minutes": 60 - session_minutes,
                    "completed": False,
                }
            )
        current += timedelta(days=1)
    return result
