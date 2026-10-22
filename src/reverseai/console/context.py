"""Per-process state of the console and the services it injects into pipeline calls."""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from reverseai import pipeline
from reverseai.config import load_settings
from reverseai.console.artifacts import ArtifactCache
from reverseai.console.jobs import JobRunner
from reverseai.console.registry import ProjectRegistry
from reverseai.i18n import t
from reverseai.llm.gateway import Gateway
from reverseai.llm.providers import build_providers
from reverseai.messages import PlainError
from reverseai.project import Project
from reverseai.sandbox import LocalSandbox
from reverseai.sandbox.base import Sandbox

GatewayFactory = Callable[[Project], Gateway]
SandboxFactory = Callable[[Path], Sandbox]


def production_gateway(project: Project) -> Gateway:
    """`pipeline.build_gateway` over the providers whose keys are in the environment.

    Refuses with a translated message when no provider key is configured, before any LLM call.
    """
    settings = load_settings()
    if not build_providers(settings, os.environ):
        names = sorted(
            {spec.api_key_env for spec in settings.providers.values() if spec.api_key_env}
        )
        raise PlainError(t("console.no_provider_key", names=", ".join(names)))
    return pipeline.build_gateway(project, settings)


@dataclass
class ConsoleContext:
    projects: ProjectRegistry
    gateway_factory: GatewayFactory = production_gateway
    sandbox_factory: SandboxFactory = LocalSandbox
    operator: str | None = None
    token: str | None = None
    jobs: JobRunner = field(default_factory=JobRunner)
    artifacts: ArtifactCache = field(default_factory=ArtifactCache)
    csrf_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))

    @property
    def operator_initials(self) -> str:
        if not self.operator:
            return t("console.operator_initials")
        parts = self.operator.split()
        return "".join(p[0] for p in parts[:2]).upper()
