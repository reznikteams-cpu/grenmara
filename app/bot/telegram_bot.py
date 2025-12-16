from __future__ import annotations

import logging
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from app.storage.db import Database
from app.storage.repo import Repo
from app.bot import handlers
from app.bot.admin import (
    admin_menu, admin_stats, broadcast_start, push_add_start, push_schedule_start,
    on_segment_chosen, on_admin_text, kb_reload
)
from app.bot.middleware import is_admin

log = logging.getLogger(__name__)


def build_application(db: Database, settings, scheduler):
    repo = Repo(db)

    application: Application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .build()
    )

    # ---------- global error handler (CRITICAL) ----------
    async def on_error(update, context):
        log.exception("Unhandled error in update=%s", update, exc_info=context.error)

    application.add_error_handler(on_error)

    # ---------- user commands (NO lambdas) ----------
    async def start_cmd(update, context):
        await handlers.start(update, context, repo, settings)

    async def help_cmd(update, context):
        await handlers.help_cmd(update, context)

    async def profile_cmd(update, context):
        await handlers.profile(update, context, repo, settings)

    async def clear_cmd(update, context):
        await handlers.clear(update, context, repo)

    async def subscribe_cmd(update, context):
        await handlers.subscribe(update, context)

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("profile", profile_cmd))
    application.add_handler(CommandHandler("clear", clear_cmd))
    application.add_handler(CommandHandler("subscribe", subscribe_cmd))

    # ---------- admin commands ----------
    async def admin_cmd(update, context):
        if not is_admin(update.effective_user.id, settings.admin_ids):
            return
        await admin_menu(update, context, repo)

    async def stats_cmd(update, context):
        if not is_admin(update.effective_user.id, settings.admin_ids):
            return
        await admin_stats(update, context, repo)

    async def kb_reload_cmd(update, context):
        if not is_admin(update.effective_user.id, settings.admin_ids):
            return
        await kb_reload(update, context, repo, settings)

    async def broadcast_cmd(update, context):
        if not is_admin(update.effective_user.id, settings.admin_ids):
            return
        await broadcast_start(update, context)

    async def push_add_cmd(update, context):
        if not is_admin(update.effective_user.id, settings.admin_ids):
            return
        await push_add_start(update, context)

    async def push_schedule_cmd(update, context):
        if not is_admin(update.effective_user.id, settings.admin_ids):
            return
        await push_schedule_start(update, context)

    application.add_handler(CommandHandler("admin", admin_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("kb_reload", kb_reload_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    application.add_handler(CommandHandler("push_add", push_add_cmd))
    application.add_handler(CommandHandler("push_schedule", push_schedule_cmd))

    # ---------- callback queries ----------
    async def on_cb(update, context):
        q = update.callback_query
        data = q.data or ""

        if data == "profile":
            await handlers.profile(update, context, repo, settings)
        elif data == "clear":
            await handlers.clear(update, context, repo)
        elif data == "admin" and is_admin(update.effective_user.id, settings.admin_ids):
            await admin_menu(update, context, repo)
        elif data == "admin_stats" and is_admin(update.effective_user.id, settings.admin_ids):
            await admin_stats(update, context, repo)
        elif data == "admin_broadcast" and is_admin(update.effective_user.id, settings.admin_ids):
            await broadcast_start(update, context)
        elif data == "admin_push_add" and is_admin(update.effective_user.id, settings.admin_ids):
            await push_add_start(update, context)
        elif data == "admin_push_schedule" and is_admin(update.effective_user.id, settings.admin_ids):
            await push_schedule_start(update, context)
        elif data == "admin_kb_reload" and is_admin(update.effective_user.id, settings.admin_ids):
            await kb_reload(update, context, repo, settings)
        elif data.startswith("seg_bcast:") or data.startswith("seg_push:"):
            if not is_admin(update.effective_user.id, settings.admin_ids):
                return
            await on_segment_chosen(update, context, repo)

    application.add_handler(CallbackQueryHandler(on_cb))

    # ---------- text messages ----------
    async def on_text(update, context):
        # admin wizard consumes first (if in mode), but should never block user flow
        if is_admin(update.effective_user.id, settings.admin_ids):
            try:
                await on_admin_text(update, context, repo, scheduler)
            except Exception:
                log.exception("Admin text handler failed")

        # normal flow
        await handlers.text_message(update, context, repo, settings)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    return application
