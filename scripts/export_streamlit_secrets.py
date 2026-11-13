"""Write Streamlit Cloud secrets TOML from local .env (do not commit the output)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import config

config.load_env.cache_clear()
from modules.config import get_database_url, get_finnhub_api_key, get_groq_api_key

vals = {
    "DATABASE_URL": get_database_url() or "",
    "FINNHUB_API_KEY": get_finnhub_api_key() or "",
    "GROQ_API_KEY": get_groq_api_key() or "",
}

out = ROOT / "_streamlit_secrets_TO_PASTE.toml"
lines = []
for key, value in vals.items():
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    lines.append(f'{key} = "{escaped}"')
out.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("wrote", out.name)
for key, value in vals.items():
    print(f"{key}: {'OK' if value else 'MISSING'} ({len(value)} chars)")
