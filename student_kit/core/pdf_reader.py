"""Lecture et préparation de documents PDF pour l'assistant d'étude."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


MIN_TEXT_LENGTH = 20


class PDFExtractionError(ValueError):
    """Document PDF inexploitable pour une génération fondée sur son texte."""


def extract_text_from_pdf(source: str | Path | bytes | BinaryIO) -> str:
    """Extrait le texte d'un PDF ou lève une erreur explicite si nécessaire."""
    try:
        if isinstance(source, (str, Path)):
            reader = PdfReader(str(source))
        elif isinstance(source, bytes):
            reader = PdfReader(BytesIO(source))
        else:
            reader = PdfReader(source)
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except (OSError, PdfReadError, TypeError, ValueError) as exc:
        raise PDFExtractionError(
            "Impossible de lire ce PDF. Vérifiez qu'il est valide et non protégé."
        ) from exc
    if len(" ".join(text.split())) < MIN_TEXT_LENGTH:
        raise PDFExtractionError(
            "Ce PDF ne contient pas assez de texte exploitable. "
            "Il est peut-être scanné, image-only ou illisible."
        )
    return text


def validate_text(text: str, minimum_length: int = MIN_TEXT_LENGTH) -> str:
    """Normalise et valide un texte collé ou extrait."""
    if not isinstance(text, str):
        raise ValueError("Le contenu doit être une chaîne de caractères.")
    normalized = " ".join(text.split()).strip()
    if len(normalized) < minimum_length:
        raise ValueError(
            "Le contenu est trop court pour générer des supports d'étude."
        )
    return normalized


def split_text(text: str, chunk_size: int = 4000, overlap: int = 400) -> list[str]:
    """Découpe un texte en morceaux avec chevauchement en caractères."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size doit être positif et supérieur à overlap.")
    normalized = validate_text(text, minimum_length=1)
    if len(normalized) <= chunk_size:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = end - overlap
    return chunks
