from dataclasses import dataclass
from typing import cast

from app.core.config import Settings
from app.model_gateway.errors import ModelNotConfiguredError
from app.model_gateway.schemas import ModelRole


@dataclass(frozen=True)
class ModelRegistry:
    settings: Settings

    def model_for(self, role: ModelRole) -> str:
        model = cast(str | None, getattr(self.settings, role.value))
        if not model and role is ModelRole.CHAT:
            model = self._chat_fallback_model()
        if not model:
            raise ModelNotConfiguredError(f"model role is not configured: {role.value}")
        return model

    def configured_models(self) -> dict[ModelRole, str]:
        configured: dict[ModelRole, str] = {}
        for role in ModelRole:
            model = cast(str | None, getattr(self.settings, role.value))
            if model:
                configured[role] = model
        return configured

    def _chat_fallback_model(self) -> str | None:
        for fallback_role in (ModelRole.SUMMARIZER, ModelRole.PLANNER, ModelRole.CODER):
            model = cast(str | None, getattr(self.settings, fallback_role.value))
            if model:
                return model
        return None
