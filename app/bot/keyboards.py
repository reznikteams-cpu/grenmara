from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_kb(is_admin: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Профиль", callback_data="profile")],
        [InlineKeyboardButton("Очистить историю", callback_data="clear")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("Админка", callback_data="admin")])
    return InlineKeyboardMarkup(buttons)

def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("Пуш: создать", callback_data="admin_push_add")],
        [InlineKeyboardButton("Пуш: запланировать", callback_data="admin_push_schedule")],
        [InlineKeyboardButton("KB: обновить", callback_data="admin_kb_reload")],
    ])

def segments_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("all", callback_data=f"{prefix}:all"),
         InlineKeyboardButton("active", callback_data=f"{prefix}:active")],
        [InlineKeyboardButton("inactive", callback_data=f"{prefix}:inactive"),
         InlineKeyboardButton("dormant_7d", callback_data=f"{prefix}:dormant_7d")],
    ])
