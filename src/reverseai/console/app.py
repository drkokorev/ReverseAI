"""The console application factory."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import Response

from reverseai.console.context import ConsoleContext, GatewayFactory, SandboxFactory
from reverseai.console.registry import ProjectInvalid, ProjectNotFound, ProjectRegistry
from reverseai.console.routes import CsrfRejected, auth, costs, overview, parity, phases
from reverseai.console.routes import lang as lang_routes
from reverseai.console.routes import projects as projects_routes
from reverseai.console.routes import release as release_routes
from reverseai.console.security import (
    ErrorPageMiddleware,
    LanguageMiddleware,
    SecurityHeadersMiddleware,
    TokenAuthMiddleware,
)
from reverseai.console.templating import STATIC_DIR, render_error
from reverseai.i18n import DEFAULT_LANG, normalize, t

_LOG = logging.getLogger("reverseai.console")


def internal_error(request: Request, exc: Exception) -> Response:
    """Any unexpected failure: the console's 500 page; the traceback goes to the server log."""
    _LOG.error("console request %s %s failed", request.method, request.url.path, exc_info=exc)
    return render_error(request, 500, t("errors.internal.title"),
                        t("errors.internal.message", error=type(exc).__name__))


def create_app(
    projects_root: Path,
    *,
    gateway_factory: GatewayFactory | None = None,
    sandbox_factory: SandboxFactory | None = None,
    operator: str | None = None,
    token: str | None = None,
    allowed_hosts: Sequence[str] | None = None,
    lang: str | None = None,
) -> FastAPI:
    """The console over every project in `projects_root`.

    `gateway_factory` / `sandbox_factory` default to the production ones (provider keys from
    the environment, `LocalSandbox`); tests inject a scripted gateway. With `token`, every
    page requires it; with `allowed_hosts`, other Host headers are refused (DNS rebinding).
    `lang` is the default display language (English when omitted); a viewer's EN/RU choice
    in the header overrides it for that browser.
    """
    default_lang = normalize(lang) if lang is not None else DEFAULT_LANG
    if default_lang is None:
        raise ValueError(f"unsupported console language {lang!r}")
    context = ConsoleContext(projects=ProjectRegistry(Path(projects_root)), operator=operator,
                             token=token)
    if gateway_factory is not None:
        context.gateway_factory = gateway_factory
    if sandbox_factory is not None:
        context.sandbox_factory = sandbox_factory

    app = FastAPI(title="ReverseAI", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.console = context
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for router in (auth.router, lang_routes.router, projects_routes.router, overview.router,
                   phases.router, release_routes.router, parity.router, costs.router):
        app.include_router(router)

    @app.exception_handler(ProjectNotFound)
    def _not_found(request: Request, exc: ProjectNotFound) -> Response:
        return render_error(request, 404, t("errors.project_not_found.title"),
                            t("errors.project_not_found.message"))

    @app.exception_handler(ProjectInvalid)
    def _invalid(request: Request, exc: ProjectInvalid) -> Response:
        return render_error(request, 500, t("errors.project_invalid.title"),
                            t("errors.project_invalid.message", name=exc.name, reason=exc.reason))

    @app.exception_handler(RequestValidationError)
    def _bad_request(request: Request, exc: RequestValidationError) -> Response:
        fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
        message = t("errors.bad_request.message")
        if fields:
            message += " " + t("errors.bad_request.fields", fields=", ".join(fields))
        return render_error(request, 400, t("errors.bad_request.title"), message)

    @app.exception_handler(CsrfRejected)
    def _csrf(request: Request, exc: CsrfRejected) -> Response:
        return render_error(request, 403, t("errors.csrf.title"), t("errors.csrf.message"))

    @app.exception_handler(StarletteHTTPException)
    def _http(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code == 404:
            return render_error(request, 404, t("errors.not_found.title"),
                                t("errors.not_found.message"))
        return render_error(request, exc.status_code, t("errors.http.title"), str(exc.detail))

    app.add_middleware(ErrorPageMiddleware, render=internal_error)  # innermost
    if token is not None:
        app.add_middleware(TokenAuthMiddleware, token=token, unauthorized=auth.unauthorized)
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(LanguageMiddleware, default=default_lang)  # outermost
    return app
