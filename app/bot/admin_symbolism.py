from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.middleware import is_admin


async def symbolism_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, repo, settings) -> None:
    """
    /symbolism_stats — показывает админам статистику по отсутствующим символам (если ты их логируешь в БД).
    Пока — заглушка: просто подтверждает, что модуль подключен.
    """
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_admin(user_id, settings.admin_ids):
        return

    # Если у тебя уже есть таблица/метод в repo — сюда вставим реальную выборку.
    # Пока просто сообщаем, что команда работает.
    await update.effective_message.reply_text(
        "✅ symbolism_stats подключён.\n"
        "Дальше добавим: список отсутствующих символов + счётчики + последние запросы."
    )
