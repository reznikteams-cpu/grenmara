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
        await update.effective_message.reply_text("Ошибка при обновлении KB ❌ (см. логи)")


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = get_state(context)
    st.mode = "broadcast_text"
    st.draft_text = ""
    await update.effective_message.reply_text("Выбери сегмент для рассылки:", reply_markup=segments_kb("seg_bcast"))


async def push_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = get_state(context)
    st.mode = "push_text"
    st.draft_text = ""
    await update.effective_message.reply_text("Текст пуша (одним сообщением):")


async def push_schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = get_state(context)
    st.mode = "push_schedule"
    await update.effective_message.reply_text("Выбери сегмент:", reply_markup=segments_kb("seg_push"))


async def on_segment_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, repo: Repo) -> None:
    query = update.callback_query
    await query.answer()
    st = get_state(context)

    data = query.data  # e.g. seg_bcast:active
    prefix, seg = data.split(":", 1)
    st.segment = seg

    if prefix == "seg_bcast":
        st.mode = "broadcast_text"
        await query.message.reply_text(f"Ок, сегмент: {seg}\nТеперь отправь текст рассылки одним сообщением.")
    elif prefix == "seg_push":
        st.mode = "push_schedule_time"
        await query.message.reply_text(
            f"Сегмент: {seg}\nТеперь отправь дату/время запуска в формате: YYYY-MM-DD HH:MM\n(по локальному времени сервера)"
        )


async def on_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE, repo: Repo, scheduler_service) -> None:
    st = get_state(context)
    text = (update.message.text or "").strip()
    if not text:
        return

    if st.mode == "broadcast_text":
        st.draft_text = text
        bid = repo.create_broadcast(admin_id=update.effective_user.id, segment=st.segment, text=st.draft_text)
        await update.message.reply_text(f"Рассылка создана (id={bid}). Начинаю отправку…")
        await scheduler_service.send_broadcast_now(broadcast_id=bid, segment=st.segment, text=st.draft_text)
        st.mode = ""
        st.draft_text = ""
        return

    if st.mode == "push_text":
        st.draft_text = text
        await update.message.reply_text("Ок. Теперь /push_schedule чтобы запланировать, или отправь /admin.")
        return

    if st.mode == "push_schedule_time":
        run_at = text  # expects "YYYY-MM-DD HH:MM"
        if not st.draft_text:
            await update.message.reply_text("Сначала создай текст пуша: /push_add")
            return

        pid = repo.create_scheduled_push(
            admin_id=update.effective_user.id,
            segment=st.segment,
            text=st.draft_text,
            run_at_iso=run_at,
        )
        await update.message.reply_text(f"Запланировано ✅ push_id={pid} на {run_at} сегмент={st.segment}")
        st.mode = ""
        return
