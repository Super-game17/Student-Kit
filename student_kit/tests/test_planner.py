from datetime import date

from student_kit.core.planner import calculate_priority, generate_schedule


def subject(name="Python", exam_date="2026-11-20", **overrides):
    value = {
        "id": name.lower(),
        "name": name,
        "exam_date": exam_date,
        "difficulty": 3,
        "remaining_volume": 4,
        "mastery": 2,
    }
    value.update(overrides)
    return value


def test_priority_increases_when_exam_is_closer():
    today = date(2026, 11, 9)
    assert calculate_priority(subject(exam_date="2026-11-10"), today) > calculate_priority(
        subject(exam_date="2026-12-10"), today
    )


def test_priority_increases_with_difficulty_volume_and_low_mastery():
    today = date(2026, 11, 9)
    baseline = calculate_priority(subject(), today)
    harder = calculate_priority(
        subject(difficulty=5, remaining_volume=10, mastery=1), today
    )
    assert harder > baseline


def test_schedule_respects_daily_capacity_and_is_deterministic():
    subjects = [subject(remaining_volume=3)]
    availability = {str(i): 1 for i in range(7)}
    first = generate_schedule(subjects, availability, "2026-11-09")
    second = generate_schedule(subjects, availability, "2026-11-09")
    assert first == second
    assert len(first) == 3
    assert all(item["duration_minutes"] == 50 for item in first)
    assert all(not item["completed"] for item in first)


def test_schedule_never_exceeds_daily_capacity():
    subjects = [subject(remaining_volume=10, exam_date="2026-11-13")]
    schedule = generate_schedule(subjects, {"0": 2, "1": 2, "2": 2}, "2026-11-09")
    sessions_per_day = {}
    for session in schedule:
        sessions_per_day[session["date"]] = sessions_per_day.get(session["date"], 0) + 1
    assert sessions_per_day
    assert max(sessions_per_day.values()) <= 2


def test_higher_priority_subject_is_scheduled_first():
    subjects = [
        subject("Lointaine", "2026-11-20", difficulty=1, mastery=5, remaining_volume=1),
        subject("Urgente", "2026-11-10", difficulty=5, mastery=1, remaining_volume=1),
    ]
    schedule = generate_schedule(subjects, {"0": 1}, "2026-11-09")
    assert schedule[0]["subject_name"] == "Urgente"


def test_no_schedule_is_created_without_availability():
    assert generate_schedule(
        [subject(remaining_volume=5)], {"0": 0, "1": 0}, "2026-11-09"
    ) == []


def test_schedule_skips_zero_availability_and_past_exam():
    subjects = [
        subject("Passe", "2026-11-08"),
        subject("Sans volume", remaining_volume=0),
        subject("Disponible", "2026-11-12", remaining_volume=1),
    ]
    schedule = generate_schedule(subjects, {"0": 0, "1": 0, "2": 1}, "2026-11-09")
    assert len(schedule) == 1
    assert schedule[0]["subject_name"] == "Disponible"
    assert schedule[0]["date"] == "2026-11-11"


def test_exam_same_day_does_not_create_late_session():
    assert generate_schedule(
        [subject(exam_date="2026-11-09")], {"0": 8}, "2026-11-09"
    ) == []


def test_invalid_session_duration_is_rejected():
    try:
        generate_schedule([subject()], {"0": 1}, "2026-11-09", session_minutes=61)
    except ValueError as error:
        assert "session_minutes" in str(error)
    else:
        raise AssertionError("Une durée invalide doit lever ValueError.")
