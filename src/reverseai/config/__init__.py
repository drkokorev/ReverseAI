"""Settings: providers, models with prices, and role -> model routing."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path(__file__).with_name("default.yaml")


class _Strict(BaseModel):
    """A misspelled key in the settings is an error, never a silently ignored default."""

    model_config = ConfigDict(extra="forbid")


class ProviderSpec(_Strict):
    name: str = ""
    kind: Literal["anthropic", "openai", "fake"]
    base_url: str | None = None
    api_key_env: str | None = None
    jurisdiction: Literal["us", "eu", "cn", "self"]


class ModelSpec(_Strict):
    id: str = ""
    provider: str
    input_per_mtok: float
    output_per_mtok: float
    cached_input_per_mtok: float = 0.0


class RoleSpec(_Strict):
    candidates: list[str] = Field(min_length=1)
    max_output_tokens: int = 8192


class Settings(_Strict):
    providers: dict[str, ProviderSpec]
    models: dict[str, ModelSpec]
    roles: dict[str, RoleSpec]

    @model_validator(mode="after")
    def _check_references(self) -> Settings:
        # Fill in the name/id from the mapping key when omitted in YAML.
        for key, provider in self.providers.items():
            provider.name = provider.name or key
        for key, model in self.models.items():
            model.id = model.id or key
        for key, model in self.models.items():
            if model.provider not in self.providers:
                raise ValueError(f"model {key!r} references unknown provider {model.provider!r}")
        for key, role in self.roles.items():
            for candidate in role.candidates:
                if candidate not in self.models:
                    raise ValueError(f"role {key!r} references unknown model {candidate!r}")
        return self


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from ``path`` or from the packaged ``default.yaml``."""
    source = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    return Settings.model_validate(data)
