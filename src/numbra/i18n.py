"""Small dictionary-based translation support shared by the terminal UI."""

from collections.abc import Mapping

from .locale_ru import MESSAGES, PLURALS

LANGUAGES = ("auto", "en", "ru")
MISSES: set[str] = set()
_language = "en"


def resolve_language(setting: str, environ: Mapping[str, str]) -> str:
    if setting in ("en", "ru"):
        return setting
    locale = next(
        (environ.get(key, "") for key in ("LC_ALL", "LC_MESSAGES", "LANG") if environ.get(key)), ""
    )
    return "ru" if locale.startswith("ru") else "en"


def set_language(code: str) -> None:
    global _language
    if code not in ("en", "ru"):
        raise ValueError("language must be en or ru")
    _language = code


def current_language() -> str:
    return _language


def t(text: str, context: str = "") -> str:
    if _language == "en":
        return text
    key = f"{context}|{text}" if context else text
    translated = MESSAGES.get(key)
    if translated is None:
        MISSES.add(key)
        return text
    return translated


def tn(count: int, one: str, many: str) -> str:
    if _language == "en":
        return one if count == 1 else many
    forms = PLURALS.get(one)
    if forms is None:
        MISSES.add(one)
        return one if count == 1 else many
    n = abs(count)
    index = (
        0
        if n % 10 == 1 and n % 100 != 11
        else 1
        if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14)
        else 2
    )
    return forms[index]
