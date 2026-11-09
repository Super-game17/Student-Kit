"""Persistance locale des données StudentKit.

Le fichier est écrit de manière atomique afin qu'un rechargement Streamlit
ne puisse pas laisser un JSON partiellement écrit.
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


DEFAULT_DATA = {
    "subjects": [],
    "exams": [],
    "availability": {},
    "sessions": [],
    "flashcards": [],
    "quizzes": [],
}


class StudentStorage:
    """Charge et sauvegarde les données utilisateur dans un fichier JSON local."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else self._default_path()
        self.data = self._load()

    @staticmethod
    def _default_path() -> Path:
        return Path(__file__).resolve().parents[2] / "data" / "student_data.json"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return deepcopy(DEFAULT_DATA)
        try:
            with self.path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Impossible de lire les données locales: {self.path}") from exc
        if not isinstance(loaded, dict):
            raise ValueError("Le fichier de données doit contenir un objet JSON.")
        data = deepcopy(DEFAULT_DATA)
        data.update(loaded)
        return data

    def save(self) -> None:
        """Sauvegarde toutes les données, avec remplacement atomique."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f"{self.path.stem}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary_name, self.path)
        except OSError as exc:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise RuntimeError(f"Impossible de sauvegarder les données: {self.path}") from exc

    def replace(self, data: Mapping[str, Any]) -> None:
        """Remplace les données par une structure complète puis la sauvegarde."""
        self.data = deepcopy(DEFAULT_DATA)
        self.data.update(dict(data))
        self.save()

    def add_subject(self, subject: Mapping[str, Any]) -> None:
        self.data["subjects"].append(dict(subject))
        self.save()

    def update_subject(self, subject_id: str, updates: Mapping[str, Any]) -> bool:
        for subject in self.data["subjects"]:
            if subject.get("id") == subject_id:
                subject.update(dict(updates))
                self.save()
                return True
        return False

    def remove_subject(self, subject_id: str) -> bool:
        subjects = self.data["subjects"]
        remaining = [subject for subject in subjects if subject.get("id") != subject_id]
        changed = len(remaining) != len(subjects)
        if changed:
            self.data["subjects"] = remaining
            self.save()
        return changed

    def add_session(self, session: Mapping[str, Any]) -> None:
        self.data["sessions"].append(dict(session))
        self.save()

    def update_session(self, session_id: str, updates: Mapping[str, Any]) -> bool:
        for session in self.data["sessions"]:
            if session.get("id") == session_id:
                session.update(dict(updates))
                self.save()
                return True
        return False

    def clear(self) -> None:
        """Supprime les données applicatives en conservant le fichier valide."""
        self.data = deepcopy(DEFAULT_DATA)
        self.save()
