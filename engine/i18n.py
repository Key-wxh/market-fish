"""
JSON-based i18n — MiroFish-inspired architecture.
Locales loaded from locales/{lang}.json. Dotted key lookup: t("sidebar.title")
Default: English (for GitHub / Product Hunt). Chinese available via toggle.
"""

import json
import os
from pathlib import Path

import streamlit as st

_LOCALES = {}
_LOCALE_DIR = Path(__file__).parent.parent / "locales"


def _load_locale(lang: str) -> dict:
    """Load a locale JSON file. Cached in _LOCALES dict."""
    if lang in _LOCALES:
        return _LOCALES[lang]
    path = _LOCALE_DIR / f"{lang}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            _LOCALES[lang] = json.load(f)
    else:
        _LOCALES[lang] = {}
    return _LOCALES[lang]


def get_lang() -> str:
    """Get current language. Returns 'en' by default (GitHub/PH-friendly)."""
    try:
        if "lang" not in st.session_state:
            st.session_state.lang = "zh"
        return st.session_state.lang
    except Exception:
        return "zh"  # fallback: Chinese for pipeline execution context


def set_lang(lang: str):
    """Set language. Safe outside streamlit context."""
    try:
        st.session_state.lang = lang
    except Exception:
        pass


def t(key: str, **kwargs) -> str:
    """
    Translate a dotted key. Falls back to the key itself if not found.
    Usage: t("sidebar.title") → "⚙️ 配置" (zh) or "Settings" (en)
    Supports {var} interpolation: t("sidebar.agent_limit_warn", n=1000)
    """
    lang = get_lang()
    locale = _load_locale(lang)
    fallback = _load_locale("en")

    parts = key.split(".")
    value = locale
    fb_value = fallback
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part, None)
        else:
            value = None
        if isinstance(fb_value, dict):
            fb_value = fb_value.get(part, None)
        else:
            fb_value = None

    # Fallback: target lang → English → key itself
    result = value if value is not None else (fb_value if fb_value is not None else key)

    # String interpolation — format numbers in code before passing to t()
    if isinstance(result, str) and kwargs:
        for k, v in kwargs.items():
            result = result.replace("{" + k + "}", str(v))

    return result


def tabs() -> list:
    """Return localized tab labels for st.tabs()."""
    en_tabs = _load_locale("en").get("tabs", {})
    return [t(f"tabs.{k}") for k in en_tabs.keys()]
