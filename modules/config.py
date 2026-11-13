"""Load local secrets from .env / .env.local without printing them."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def load_env() -> None:
    # .env.local wins over .env when both exist.
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=True)


def _secret(name: str) -> str | None:
    """Read from process env first, then Streamlit Cloud secrets."""
    load_env()
    val = (os.getenv(name) or "").strip()
    if val:
        return val
    try:
        import streamlit as st

        raw = st.secrets.get(name)  # type: ignore[attr-defined]
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None
    except Exception:
        return None


def get_database_url() -> str | None:
    return _secret("DATABASE_URL") or _secret("POSTGRES_URL")


def get_finnhub_api_key() -> str | None:
    return _secret("FINNHUB_API_KEY")


def get_groq_api_key() -> str | None:
    """Free chatbot API: https://console.groq.com"""
    return _secret("GROQ_API_KEY")


def get_gemini_api_key() -> str | None:
    """Free chatbot API: https://aistudio.google.com/apikey"""
    return (
        _secret("GEMINI_API_KEY")
        or _secret("GOOGLE_API_KEY")
        or _secret("GOOGLE_AI_API_KEY")
    )
