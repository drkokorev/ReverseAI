"""User-facing text: English (default) and Russian catalogs behind one lookup, `t()`.

Every string a person reads (CLI output, console pages, job logs, errors, generated documents)
is a catalog entry; code never hardcodes it. The active language lives in a context variable:
the CLI sets it from `--lang` / `REVERSEAI_LANG`, the console per request (cookie or the
`--lang` default), and console jobs inherit the language of the request that started them.

An entry is a `str.format` template (literal braces are doubled) or, where a count appears, a
dict of plural forms keyed by `plural_form()`: English `one`/`other`, Russian
`one`/`few`/`many`. The count is passed as `count=`.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, TypeVar

from reverseai.i18n import en, ru

LANGS: tuple[str, ...] = ("en", "ru")
DEFAULT_LANG = "en"
LANG_ENV = "REVERSEAI_LANG"
CATALOGS: dict[str, dict[str, Any]] = {"en": en.MESSAGES, "ru": ru.MESSAGES}

_current: contextvars.ContextVar[str] = contextvars.ContextVar(
    "reverseai_lang", default=DEFAULT_LANG
)


def normalize(lang: str | None) -> str | None:
    """`lang` as a supported code (`en`, `RU`, `ru-RU` → `ru`), or None when unsupported."""
    if not lang:
        return None
    code = lang.strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGS else None


def env_language() -> str:
    """The language named by `REVERSEAI_LANG`, else the default (English)."""
    return normalize(os.environ.get(LANG_ENV)) or DEFAULT_LANG


def get_language() -> str:
    return _current.get()


def set_language(lang: str) -> contextvars.Token[str]:
    code = normalize(lang)
    if code is None:
        raise ValueError(f"unsupported language {lang!r}; expected one of {', '.join(LANGS)}")
    return _current.set(code)


@contextlib.contextmanager
def use_language(lang: str) -> Iterator[None]:
    token = set_language(lang)
    try:
        yield
    finally:
        _current.reset(token)


def plural_form(lang: str, count: int) -> str:
    n = abs(int(count))
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    return "one" if n == 1 else "other"


def t(key: str, /, lang: str | None = None, **params: Any) -> str:
    """The catalog entry `key` in `lang` (default: the active language), formatted.

    A key missing from the language falls back to English; a key missing from English is a
    bug and raises KeyError (tests check that both catalogs have the same keys).
    """
    code = normalize(lang) or get_language()
    entry = CATALOGS[code].get(key)
    if entry is None:
        code, entry = DEFAULT_LANG, CATALOGS[DEFAULT_LANG][key]
    if isinstance(entry, dict):
        entry = entry[plural_form(code, params["count"])]
    return entry.format(**params)


def has(key: str) -> bool:
    """Whether `key` is a catalog entry (every entry exists in English)."""
    return key in CATALOGS[DEFAULT_LANG]


K = TypeVar("K")


class Labels(Mapping[K, str]):
    """A fixed set of keys whose labels are looked up in the active language on every access.

    Module-level label tables (phases, roles, modes) are built at import time, before any
    language is chosen; this keeps them as mappings while their text follows the language.
    """

    def __init__(self, prefix: str, keys: Iterable[K], name: Callable[[K], str] = str) -> None:
        self._prefix = prefix
        self._keys = list(keys)
        self._name = name

    def __getitem__(self, key: K) -> str:
        if key not in self._keys:
            raise KeyError(key)
        return t(f"{self._prefix}.{self._name(key)}")

    def __iter__(self) -> Iterator[K]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def __contains__(self, key: object) -> bool:
        return key in self._keys


__all__ = [
    "CATALOGS",
    "DEFAULT_LANG",
    "LANGS",
    "LANG_ENV",
    "Labels",
    "env_language",
    "get_language",
    "has",
    "normalize",
    "plural_form",
    "set_language",
    "t",
    "use_language",
]
