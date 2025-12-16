from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from telegram import Update
from telegram.ext import ContextTypes

from app.storage.repo import Repo
from app.bot.keyboards import admin_kb, segments_kb
from app.knowledge.ingest import KnowledgeIngestor

log = logging.getLogger(__name__)


@dataclass
class AdminState:
    mode: str = ""         # "broadcast_text" | "push_text" | "push_schedule" | "push_schedule_time"
    segment: str = "all"
    draft_text: str = ""


ADMIN_STATE_KEY = "admin_state"


def get_state(ctx: ContextTypes.DEFAULT_TYPE) -> AdminState:
    st = ctx.user_data.get(ADMIN_STATE_KEY)
    if not st:
        st = AdminState()
        ctx.user_data[ADMIN_STATE_KEY] = st
    return st


async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, repo: Repo) -> None:
    await update.effective_message.reply_text("Админка:", reply_markup=admin_kb())


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, repo: Repo) -> None:
    total = repo.db.query("SELECT COUNT(*) AS c FROM users")[0]["c"]
    active = repo.db.query("SELECT COUNT(*) AS c FROM users WHERE is_active_subscription=1")[0]["c"]
    dormant = repo.db.query("SELECT COUNT(*) AS c FROM users WHERE last_seen_at < datetime('now','-7 day')")[0]["c"]
    await update.effective_message.reply_text(
        f"Пользователей: {total}\nАктивные подписки: {active}\nНеактивны 7д+: {dormant}"
    )


async def kb_reload(update: Update, context: ContextTypes.DEFAULT_TYPE, repo: Repo, settings) -> None:
    """
    Полная переиндексация KB из Google Docs.
    Важно: после успешного реиндекса — помечаем KB как ready в app.kb.state,
    иначе остальная система может считать, что KB "не готова".
    """
    await update.effective_message.reply_text("Обновляю KB…")

    ing = KnowledgeIngestor(db=repo.db, settings=settings)
    try:
        indexed = await ing.reindex_all()

        # sync in-memory KB readiness
        try:
            from app.kb.state import kb_mark_ready, kb_set_last_load_ts

            kb_mark_ready(True if indexed > 0 else False)
            kb_set_last_load_ts(int(time.time()))
        except Exception:
            log.exception("Failed to mark KB state after kb_reload")

        if indexed > 0:
            await update.effective_message.reply_text(f"KB обновлена ✅ (chunks: {indexed})")
        else:
            await update.effective_message.reply_text(
                "KB обновлена, но получилась пустой ⚠️\n"
                "Проверь GDOCS_SOURCES и доступ к документам."
            )
    except Exception as e:
        # mark not ready on failure
        try:
            from app.kb.state import kb_mark_ready

            kb_mark_ready(False)
        except Exception:
            pass
        log.exception("KB reload failed: %s", e)
        await update.effective_message.reply_text("Ошибка при об
