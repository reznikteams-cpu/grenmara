from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes

from app.storage.repo import Repo
from app.bot.keyboards import main_kb
from app.bot.middleware import is_admin, touch_user
from app.billing.access import can_use_ai
from app.knowledge.embeddings import embed_query
from app.knowledge.rag import top_k_chunks, build_context, llm_answer

log = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """Ты — ИИ-ассистент в Telegram.
Отвечай полезно, но строго:
- Используй ТОЛЬКО "Контекст из базы знаний", если он дан.
- Если контекста недостаточно — скажи, что в базе знаний этого нет, и задай уточняющий вопрос.
- Не выдумывай факты из базы знаний.

Контекст из базы знаний:
{kb_context}
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, repo: Repo, settings) -> None:
    await touch_user(repo, update.effective_user)
    adm = is_admin(update.effective_user.id, settings.admin_ids)
    await update.message.reply_text(
        "Привет 🤍 Напиши вопрос — я отвечу с опорой на мою базу знаний.\n"
        "Команды: /help /profile /clear",
        reply_markup=main_kb(adm),
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я отвечаю на вопросы и опираюсь на базу знаний.\n"
        "/profile — статус\n"
        "/clear — очистить историю\n"
        "/subscribe — оформить подписку (заглушка)\n"
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE, repo: Repo, settings) -> None:
    await touch_user(repo, update.effective_user)
    u = repo.get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("Профиль не найден.")
        return
    active = "активна ✅" if int(u["is_active_subscription"]) == 1 else "не активна ❌"
    used = int(u["free_messages_used"] or 0)
    await update.message.reply_text(
        f"Подписка: {active}\n"
        f"Демо-использовано: {used}/{settings.free_trial_messages}"
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE, repo: Repo) -> None:
    repo.clear_messages(update.effective_user.id)
    await update.message.reply_text("История очищена ✅")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # заглушка: тут подключаешь свою оплату/платформу/Telegram Stars/Robokassa webhook
    await update.message.reply_text(
        "Чтобы оформить подписку — подключи оплату в своём биллинге.\n"
        "Если хочешь, скажи какой вариант: Stars / Robokassa / Stripe — и я под это дам код."
    )

async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE, repo: Repo, settings) -> None:
    await touch_user(repo, update.effective_user)
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    if not text:
        return

    allowed, note = can_use_ai(repo, user_id, settings.free_trial_messages)
    if not allowed:
        await update.message.reply_text(note)
        return

    if int(repo.get_user(user_id)["is_active_subscription"]) == 0:
        repo.inc_free_used(user_id)

    # store user message
    repo.add_message(user_id, "user", text)

    # RAG retrieval
    chunks = repo.get_all_chunks()
    kb_context = ""
    if chunks and settings.openai_api_key:
        qemb = embed_query(settings.openai_api_key, settings.embedding_model, text)
        top = top_k_chunks(qemb, chunks, settings.rag_top_k)
        kb_context = build_context(top, settings.rag_max_chars)

    system = SYSTEM_TEMPLATE.format(kb_context=kb_context or "—")
    history = repo.get_recent_messages(user_id, limit=16)

    # Convert to Responses input format
    msgs = [{"role": r["role"], "content": r["content"]} for r in history]

    answer = llm_answer(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        system=system,
        messages=msgs,
    )

    repo.add_message(user_id, "assistant", answer)
    if note:
        answer = f"{answer}\n\n_{note}_"
    await update.message.reply_text(answer)
