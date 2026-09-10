from __future__ import annotations

import json
import os
from collections.abc import Generator
from typing import Any

import requests


class OllamaClient:

    def __init__(
        self,
        base_url: str | None = None,
    ):
        """Initialize the Ollama API client.

        Args:
            base_url: Optional base URL of the Ollama API. If not provided,
                the OLLAMA_BASE_URL environment variable is used, falling
                back to the default Ollama URL.

        Returns:
            None.
        """

        self.base_url = (
            base_url
            or os.getenv(
                "OLLAMA_BASE_URL",
                "http://host.docker.internal:11434",
            )
        ).rstrip("/")

    def health(self) -> dict:
        """Check the Ollama service health and retrieve available model data.

        Returns:
            A dictionary containing the response from the Ollama
            /api/tags endpoint.

        Raises:
            requests.HTTPError: If the Ollama API returns an unsuccessful
                HTTP status code.
            requests.RequestException: If the HTTP request fails.
        """

        response = requests.get(
            f"{self.base_url}/api/tags",
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def list_models(self) -> list[dict]:
        """Return the list of models available in Ollama.

        Returns:
            A list of dictionaries containing information about
            available Ollama models.

        Raises:
            requests.HTTPError: If the Ollama API returns an unsuccessful
                HTTP status code.
            requests.RequestException: If the HTTP request fails.
        """

        data = self.health()

        return data.get(
            "models",
            [],
        )

    def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        """Generate a response from an Ollama model.

        Args:
            model: Name of the Ollama model to use.
            prompt: User prompt to send to the model.
            system: Optional system prompt.
            temperature: Sampling temperature used during generation.

        Returns:
            A dictionary containing the complete Ollama generation response.

        Raises:
            requests.HTTPError: If the Ollama API returns an unsuccessful
                HTTP status code.
            requests.RequestException: If the HTTP request fails.
        """

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if system:
            payload["system"] = system

        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=300,
        )

        response.raise_for_status()

        return response.json()

    def generate_stream(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
    ) -> Generator[dict[str, Any], None, None]:
        """Generate a streaming response from an Ollama model.

        Args:
            model: Name of the Ollama model to use.
            prompt: User prompt to send to the model.
            system: Optional system prompt.
            temperature: Sampling temperature used during generation.

        Returns:
            A generator yielding dictionaries containing individual
            response chunks from the Ollama streaming API.

        Raises:
            requests.HTTPError: If the Ollama API returns an unsuccessful
                HTTP status code.
            requests.RequestException: If the HTTP request fails.
        """

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }

        if system:
            payload["system"] = system

        with requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            stream=True,
            timeout=300,
        ) as response:

            response.raise_for_status()

            for line in response.iter_lines(
                decode_unicode=True
            ):
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                yield data
