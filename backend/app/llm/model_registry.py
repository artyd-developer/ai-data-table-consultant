import json
from datetime import datetime

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import LLMModel
from app.llm.ollama import OllamaClient


class ModelRegistry:
    def __init__(self):
        """Initialize the model registry and Ollama client.

        Returns:
            None.
        """

        self.ollama = OllamaClient()

    def sync_ollama_models(self) -> list[dict]:
        """Get models from Ollama and synchronize them with MariaDB.

        Returns:
            A list of dictionaries containing synchronized model
            information, including identifiers, provider, capabilities,
            context length, pricing, and model parameters.
        """

        ollama_models = self.ollama.list_models()

        db = SessionLocal()

        try:
            result = []

            for item in ollama_models:
                name = item["name"]
                details = item.get("details") or {}

                model = db.scalar(
                    select(LLMModel).where(
                        LLMModel.name == name
                    )
                )

                if model is None:
                    model = LLMModel(
                        name=name,
                        provider="ollama",
                        display_name=name,
                        active=True,
                        context_length=details.get(
                            "context_length"
                        ),
                        input_price_per_1m=0.0,
                        output_price_per_1m=0.0,
                        capabilities=json.dumps(
                            item.get("capabilities", [])
                        ),
                        parameter_size=details.get(
                            "parameter_size"
                        ),
                        quantization_level=details.get(
                            "quantization_level"
                        ),
                        last_synced_at=datetime.utcnow(),
                    )

                    db.add(model)

                else:
                    model.provider = "ollama"
                    model.context_length = details.get(
                        "context_length"
                    )
                    model.capabilities = json.dumps(
                        item.get("capabilities", [])
                    )
                    model.parameter_size = details.get(
                        "parameter_size"
                    )
                    model.quantization_level = details.get(
                        "quantization_level"
                    )
                    model.last_synced_at = datetime.utcnow()

                result.append(model)

            db.commit()

            return [
                {
                    "id": model.id,
                    "name": model.name,
                    "provider": model.provider,
                    "display_name": model.display_name,
                    "active": model.active,
                    "context_length": model.context_length,
                    "input_price_per_1m": model.input_price_per_1m,
                    "output_price_per_1m": model.output_price_per_1m,
                    "capabilities": (
                        json.loads(model.capabilities)
                        if model.capabilities
                        else []
                    ),
                    "parameter_size": model.parameter_size,
                    "quantization_level": model.quantization_level,
                }
                for model in result
            ]

        finally:
            db.close()

    def get_active_models(self) -> list[LLMModel]:
        """Return all active LLM models ordered by name.

        Returns:
            A list of active LLMModel instances sorted by model name.
        """

        db = SessionLocal()

        try:
            stmt = (
                select(LLMModel)
                .where(LLMModel.active.is_(True))
                .order_by(LLMModel.name)
            )

            return db.scalars(stmt).all()

        finally:
            db.close()
