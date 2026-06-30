"""
Minimal i18n — language toggle for Streamlit UI.
Usage: T("中文", "English") → returns the active language's string.
"""

import streamlit as st


def _get_lang():
    """Lazy-init language state — safe outside streamlit context."""
    try:
        if "lang" not in st.session_state:
            st.session_state.lang = "zh"
        return st.session_state.lang
    except Exception:
        return "zh"  # fallback outside streamlit


def set_lang(lang: str):
    try:
        st.session_state.lang = lang
    except Exception:
        pass


def T(zh: str, en: str) -> str:
    """Return string in current language."""
    return zh if _get_lang() == "zh" else en


# ── Tab labels (used in st.tabs) ──
TABS_ZH = ["📊 产品预测", "📋 证据报告", "🤖 Agent 总览", "🕸️ Agent 图谱",
           "💬 Agent 对话", "🕸️ 耦合 & 网络", "🧠 RL 策略", "📋 原始数据"]
TABS_EN = ["📊 Products", "📋 Evidence", "🤖 Agents", "🕸️ Graph",
           "💬 Chat", "🕸️ Network", "🧠 RL Strategy", "📋 Raw Data"]

def tabs():
    return [T(zh, en) for zh, en in zip(TABS_ZH, TABS_EN)]
