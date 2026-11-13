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


def get_database_url() -> str | None:
    load_env()
    url = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    return url or None


def get_finnhub_api_key() -> str | None:
    load_env()
    key = (os.getenv("FINNHUB_API_KEY") or "").strip()
    return key or None


def get_groq_api_key() -> str | None:
    """Free chatbot API: https://console.groq.com"""
    load_env()
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    return key or None


def get_gemini_api_key() -> str | None:
    """Free chatbot API: https://aistudio.google.com/apikey"""
    load_env()
    key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_AI_API_KEY")
        or ""
    ).strip()
    return key or None
