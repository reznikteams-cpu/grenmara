from __future__ import annotations
import json
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_ids: set[int]

    openai_api_key: str
    openai_model: str
    embedding_model: str

    database_url: str

    gdocs_sources: list[dict]
    rag_top_k: int
    rag_max_chars: int

    free_trial_messages: int
    scheduler_tz: str
    log_level: str

def _parse_admin_ids(raw: str) -> set[int]:
    ids = set()
    for x in (raw or "").split(","):
        x = x.strip()
        if not x:
            continue
        ids.add(int(x))
    return ids

def _parse_json(raw: str, default):
    if not raw:
        return default
    return json.loads(raw)

def get_settings() -> Settings:
    return Settings(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),

        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),

        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/bot.sqlite"),

        gdocs_sources=_parse_json(os.getenv("GDOCS_SOURCES", "[]"), []),
        rag_top_k=int(os.getenv("RAG_TOP_K", "5")),
        rag_max_chars=int(os.getenv("RAG_MAX_CHARS", "6000")),

        free_trial_messages=int(os.getenv("FREE_TRIAL_MESSAGES", "3")),
        scheduler_tz=os.getenv("SCHEDULER_TZ", "Europe/Vilnius"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )

