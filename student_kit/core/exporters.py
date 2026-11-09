"""Exports des supports StudentKit."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def export_schedule_pdf(
    sessions: Iterable[Mapping[str, object]],
    title: str = "Planning StudentKit",
) -> bytes:
    """Retourne un PDF lisible contenant les sessions fournies."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    rows = [["Date", "Matière", "Durée", "Statut"]]
    for session in sorted(sessions, key=lambda item: str(item.get("date", ""))):
        rows.append(
            [
                str(session.get("date", "")),
                str(session.get("subject_name", "Matière")),
                f"{session.get('duration_minutes', 50)} min",
                "Terminée" if session.get("completed", False) else "À faire",
            ]
        )
    table = Table(rows, repeatRows=1, colWidths=[30 * mm, 80 * mm, 30 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#315C8C")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    document.build(
        [Paragraph(title, styles["Title"]), Spacer(1, 8), Paragraph(
            f"Exporté le {date.today().isoformat()}", styles["Normal"]
        ), Spacer(1, 12), table]
    )
    return buffer.getvalue()


def export_flashcards_csv(cards: Iterable[Mapping[str, object]]) -> bytes:
    """Retourne les flashcards en CSV UTF-8 compatible tableur."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["id", "question", "answer", "explanation", "rating", "subject_id"])
    for card in cards:
        writer.writerow(
            [
                card.get("id", ""),
                card.get("question", ""),
                card.get("answer", ""),
                card.get("explanation", ""),
                card.get("rating", ""),
                card.get("subject_id", ""),
            ]
        )
    return output.getvalue().encode("utf-8-sig")
