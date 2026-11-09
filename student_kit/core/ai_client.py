"""Fournisseurs de génération IA interchangeables et mode démonstration."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

import requests


class AIClientError(RuntimeError):
    """Erreur explicite d'un fournisseur IA ou de sa réponse."""


class AIClient(ABC):
    """Contrat minimal utilisé par la logique de génération."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Retourne la réponse brute du fournisseur."""


class OllamaClient(AIClient):
    """Client Ollama local via son API HTTP, sans clé API."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2")
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload: Any = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise AIClientError(
                "Ollama est indisponible ou a renvoyé une réponse invalide."
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
            raise AIClientError("La réponse Ollama ne contient pas de champ 'response'.")
        return payload["response"]


class DemoClient(AIClient):
    """Fournisseur local sans réseau, fondé sur le contenu reçu."""

    def generate(self, prompt: str) -> str:
        source = prompt.split("SOURCE:\n", 1)[-1].strip()
        sentences = [part.strip() for part in source.replace("\n", " ").split(".") if part.strip()]
        if "QCM" in prompt:
            questions = [
                {
                    "question": f"Quelle affirmation est reprise dans le document : « {sentence} » ?",
                    "options": [sentence, "Information absente du document"],
                    "correct_answer": sentence,
                    "explanation": (
                        f"La réponse correcte est reprise directement : {sentence}."
                    ),
                }
                for sentence in sentences[:3]
            ]
            return json.dumps(questions, ensure_ascii=False)
        cards = [
            {
                "question": f"Quel est le point important présenté dans : « {sentence} » ?",
                "answer": sentence,
                "explanation": "Réponse reprise directement du document fourni.",
            }
            for sentence in sentences[:3]
        ]
        return json.dumps(cards, ensure_ascii=False)


def get_ai_client(provider: str | None = None) -> AIClient:
    """Sélectionne Ollama si explicitement demandé, sinon le mode démo."""
    selected = (provider or os.getenv("AI_PROVIDER", "demo")).lower()
    if selected == "ollama":
        return OllamaClient()
    if selected in {"demo", "simulation"}:
        return DemoClient()
    raise AIClientError(
        f"Fournisseur IA inconnu: {selected}. Utilisez 'demo' ou 'ollama'."
    )
