from __future__ import annotations

import logging
import time
from telegram.ext import ContextTypes

from app.knowledge.symbolism import (
    build_symbolism_index,
    find_symbol_entry,
    summarize_index,
)
from app.knowledge.ingest import KnowledgeIngestor

log = logging.getLogger(__name__)

STAGE_SITUATION = "situation"
STAGE_FEELINGS = "feelings"
STAGE_ANIMAL = "animal"
STAGE_ANIMAL_SELF = "animal_self"
STAGE_ANALYSIS = "analysis"
STAGE_DONE = "done"


def _ud(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if context.user_data is None:
        context.user_data = {}
    return context.user_data


def _is_positive_feelings(text: str) -> bool:
    t = (text or "").lower()
    positives = ["рад", "радость", "лёгк", "легк", "кайф", "вдохнов", "спокой", "уверен", "приятн"]
    negatives = ["тревог", "страх", "злост", "гнев", "обид", "тяжест", "оцепен", "апат", "стыд", "вина", "напряж"]
    if any(x in t for x in negatives):
        return False
    if any(x in t for x in positives):
        return True
    return False


def _looks_complex_scene(text: str) -> bool:
    low = (text or "").lower()
    markers = [
        ",", " и ", " рядом", " напротив", " вместе",
        " нападает", " дерутся", " сраж", " кусает", " гонит", " убег",
        " в лесу", " в воде", " в доме", " на улице"
    ]
    return any(m in low for m in markers)


async def start(update, context, repo, settings):
    ud = _ud(context)
    ud.clear()
    ud["stage"] = STAGE_SITUATION
    await update.effective_message.reply_text(
        "Что ты хочешь обсудить? Опиши ситуацию/запрос одним сообщением."
    )


async def help_cmd(update, context):
    await update.effective_message.reply_text(
        "/start — начать заново\n"
        "/clear — сбросить\n"
    )


async def clear(update, context, repo):
    _ud(context).clear()
    await update.effective_message.reply_text("Сбросила. Напиши /start чтобы начать заново.")


async def profile(update, context, repo, settings):
    await update.effective_message.reply_text("Профиль: в разработке.")


async def subscribe(update, context):
    await update.effective_message.reply_text("Подписка: в разработке.")


async def text_message(update, context, repo, settings):
    msg = update.effective_message
    text = (msg.text or "").strip()
    if not text:
        return

    ud = _ud(context)
    stage = ud.get("stage") or STAGE_SITUATION

    # Этап 0: запрос/ситуация
    if stage == STAGE_SITUATION:
        ud["situation"] = text
        ud["stage"] = STAGE_FEELINGS
        await msg.reply_text('Что ты чувствуешь в этой ситуации? Напиши все чувства и телесные ощущения.')
        return

    # Этап 1: чувства
    if stage == STAGE_FEELINGS:
        ud["feelings"] = text

        if _is_positive_feelings(text):
            # Этап 4 сразу (пропускаем зверя)
            ud["animal_scene"] = None
            ud["animal_self"] = None
            ud["stage"] = STAGE_ANALYSIS
            await _send_hypothesis_strict(update, context, repo, settings)
            ud["stage"] = STAGE_DONE
            return

        # Этап 2: зверь
        ud["stage"] = STAGE_ANIMAL
        await msg.reply_text(
            "Представь, что ты — зверь, который это чувствует. Какой зверь пришёл? Где он находится? Что он делает?"
        )
        return

    # Этап 2: зверь
    if stage == STAGE_ANIMAL:
        ud["animal_scene"] = text

        if _looks_complex_scene(text):
            ud["stage"] = STAGE_ANIMAL_SELF
            await msg.reply_text("Кем ты себя ощущаешь в этой картинке?")
            return

        ud["animal_self"] = None
        ud["stage"] = STAGE_ANALYSIS
        await _send_hypothesis_strict(update, context, repo, settings)
        ud["stage"] = STAGE_DONE
        return

    # Уточнение: "Кем ты себя ощущаешь"
    if stage == STAGE_ANIMAL_SELF:
        ud["animal_self"] = text
        ud["stage"] = STAGE_ANALYSIS
        await _send_hypothesis_strict(update, context, repo, settings)
        ud["stage"] = STAGE_DONE
        return

    # Новый цикл без лишних вопросов
    ud.clear()
    ud["stage"] = STAGE_SITUATION
    await msg.reply_text("Что ты хочешь обсудить? Опиши ситуацию/запрос одним сообщением.")


async def _notify_admins_missing_symbol(context, settings, user_id: int, username: str | None, requested: str, debug_hint: str):
    """
    Уведомление админам: пользователь запросил символ, которого нет в базе.
    """
    admin_ids = getattr(settings, "admin_ids", []) or []
    if not admin_ids:
        return

    who = f"{user_id}"
    if username:
        who = f"@{username} ({user_id})"

    text = (
        "⚠️ Symbolism missing\n"
        f"User: {who}\n"
        f"Requested: {requested}\n"
        f"Hint: {debug_hint}"
    )

    for aid in admin_ids:
        try:
            await context.bot.send_message(chat_id=aid, text=text)
        except Exception:
            log.exception("Failed to notify admin_id=%s", aid)


def _get_symbolism_raw(repo) -> str | None:
    """
    Нормализуем поиск по title: и английский, и русский.
    """
    return (
        repo.get_document_raw_text_by_title("symbolism")
        or repo.get_document_raw_text_by_title("Символизм")
    )


async def _try_reindex_kb(repo, settings) -> int:
    """
    Попытка восстановить KB, если в базе нет документа.
    Возвращает число чанков, записанных при реиндексации.
    """
    ing = KnowledgeIngestor(db=repo.db, settings=settings)
    indexed = await ing.reindex_all()

    # sync in-memory readiness
    try:
        from app.kb.state import kb_mark_ready, kb_set_last_load_ts

        kb_mark_ready(True if indexed > 0 else False)
        kb_set_last_load_ts(int(time.time()))
    except Exception:
        log.exception("Failed to mark KB state after reindex attempt")

    return indexed


async def _send_hypothesis_strict(update, context, repo, settings):
    """
    Строго:
    - символизм/вопросы: только из файла "Символизм"
    - никаких дополнительных вопросов, не прописанных в алгоритме
    - если символ не найден — сообщаем пользователю и уведомляем админов
    """
    msg = update.effective_message
    ud = _ud(context)

    situation = ud.get("situation") or "—"
    feelings = ud.get("feelings") or "—"
    animal_scene = ud.get("animal_scene")
    animal_self = ud.get("animal_self")

    # 1) Если зверя не было (позитивные чувства) — гипотеза без символизма
    if not animal_scene:
        await msg.reply_text(
            "**Этап 4: Гипотеза**\n\n"
            "По алгоритму при ресурсных/позитивных чувствах этап зверя пропускается.\n"
            f"— Ситуация/запрос: {situation}\n"
            f"— Чувства/ощущения: {feelings}\n",
            parse_mode="Markdown"
        )
        return

    # 2) Достаём сырой текст "Символизм" из KB (БД)
    symbolism_raw = _get_symbolism_raw(repo)

    # Если в БД нет документа — пробуем один раз восстановить KB из Google Docs
    if not symbolism_raw:
        try:
            indexed = await _try_reindex_kb(repo, settings)
            log.warning("Symbolism not found in DB. Reindex attempt wrote %s chunks.", indexed)
        except Exception as e:
            log.exception("Reindex attempt failed: %s", e)

        symbolism_raw = _get_symbolism_raw(repo)

    if not symbolism_raw:
        await msg.reply_text("Файл «Символизм» не загружен в базу знаний.")
        await _notify_admins_missing_symbol(
            context, settings,
            user_id=update.effective_user.id,
            username=update.effective_user.username,
            requested=animal_scene,
            debug_hint="kb_documents missing title=symbolism (even after reindex)"
        )
        return

    # 3) Строим индекс ОДИН РАЗ на запрос (можно кешировать позже)
    sym = build_symbolism_index(symbolism_raw, source_title="symbolism")
    found = find_symbol_entry(sym, animal_scene)

    if not found:
        await msg.reply_text(
            "Не нашла этот образ в файле «Символизм» (в базе знаний). "
            "Чтобы продолжить строго по структуре, образ должен совпасть с формулировкой/словом из файла."
        )

        debug_hint = summarize_index(sym)
        await _notify_admins_missing_symbol(
            context, settings,
            user_id=update.effective_user.id,
            username=update.effective_user.username,
            requested=animal_scene,
            debug_hint=debug_hint
        )
        return

    key, entry = found

    # 4) Вывод: символизм + гипотеза (без лишних вопросов)
    parts = []
    parts.append("**Этап 3: Символический анализ (по файлу «Символизм»)**")
    parts.append(entry)

    parts.append("\n**Этап 4: Гипотеза**")
    parts.append(
        "Связка 3 уровней:\n"
        f"— Ситуация/запрос: {situation}\n"
        f"— Чувства/реакция: {feelings}\n"
        f"— Образ: {animal_scene}\n"
        + (f"— Кем ты себя ощущаешь: {animal_self}\n" if animal_self else "")
        + "\nГипотеза формулируется на основе этих данных и блока «Символизм» выше. "
        "Если нужны уточнения — они задаются только теми вопросами, которые указаны в «Символизме»."
    )

    await msg.reply_text("\n\n".join(parts), parse_mode="Markdown")
