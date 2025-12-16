from __future__ import annotations

import logging
import re
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)

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
    markers = [",", " и ", " рядом", " напротив", " вместе", " нападает", " дерутся", " сраж", " кусает", " гонит", " убег", " в лесу", " в воде", " в доме"]
    return any(m in low for m in markers)


def _extract_symbolism_entry(raw_text: str, key: str) -> str | None:
    """
    Пытаемся вытащить блок по ключу (животное/символ).
    Алгоритм: найти строку, начинающуюся с ключа (или где ключ отдельным словом),
    затем вернуть следующие строки до пустой строки/следующего заголовка.
    """
    if not raw_text or not key:
        return None

    lines = raw_text.splitlines()
    k = key.strip().lower()

    # match line that starts with key or contains it as whole word
    start_idx = None
    for i, ln in enumerate(lines):
        l = ln.strip()
        if not l:
            continue
        ll = l.lower()
        if ll.startswith(k) or re.search(rf"\b{re.escape(k)}\b", ll):
            start_idx = i
            break

    if start_idx is None:
        return None

    out = []
    out.append(lines[start_idx].rstrip())

    for j in range(start_idx + 1, min(start_idx + 80, len(lines))):
        ln = lines[j].rstrip()
        if not ln.strip():
            # stop at first empty line after we started collecting some content
            if len(out) > 1:
                break
            continue
        # heuristic stop on next strong heading
        if re.match(r"^[A-ZА-ЯЁ0-9🐘🦊🐺🦁🦅🦂🕷️].{0,40}$", ln.strip()) and len(out) > 3:
            break
        out.append(ln)

    text = "\n".join(out).strip()
    return text if text else None


async def start(update, context, repo, settings):
    ud = _ud(context)
    ud.clear()
    ud["stage"] = STAGE_FEELINGS
    await update.effective_message.reply_text(
        'Что ты чувствуешь в этой ситуации? Напиши все чувства и телесные ощущения.'
    )


async def help_cmd(update, context):
    await update.effective_message.reply_text(
        "/start — начать\n"
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
    stage = ud.get("stage") or STAGE_FEELINGS

    # Этап 1: чувства
    if stage == STAGE_FEELINGS:
        ud["feelings"] = text

        # позитивные чувства => сразу гипотеза (Этап 4), пропуская зверя
        if _is_positive_feelings(text):
            ud["stage"] = STAGE_ANALYSIS
            ud["animal_scene"] = None
            ud["animal_self"] = None
            await _send_hypothesis_strict(update, context, repo, settings)
            ud["stage"] = STAGE_DONE
            return

        # негативные/напряжённые => Этап 2: зверь
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

    # уточнение "Кем ты себя ощущаешь"
    if stage == STAGE_ANIMAL_SELF:
        ud["animal_self"] = text
        ud["stage"] = STAGE_ANALYSIS
        await _send_hypothesis_strict(update, context, repo, settings)
        ud["stage"] = STAGE_DONE
        return

    # если пользователь пишет дальше — начинаем заново с Этапа 1 (без лишних вопросов)
    ud.clear()
    ud["stage"] = STAGE_FEELINGS
    await msg.reply_text('Что ты чувствуешь в этой ситуации? Напиши все чувства и телесные ощущения.')


async def _send_hypothesis_strict(update, context, repo, settings):
    """
    Строго: символизм и вопросы берём ТОЛЬКО из файла "Символизм" (в KB как raw_text).
    Никаких внешних вопросов (включая "Для чего..."), только гипотеза.
    """
    msg = update.effective_message
    ud = _ud(context)

    feelings = ud.get("feelings") or "—"
    animal_scene = ud.get("animal_scene")
    animal_self = ud.get("animal_self")

    # 1) получить текст "Символизма" из KB
    symbolism_raw = repo.get_document_raw_text_by_title("symbolism")
    if not symbolism_raw:
        # fallback: если у тебя title другой — можно заменить тут на точный
        symbolism_raw = repo.get_document_raw_text_by_title("Символизм")

    if animal_scene:
        # 2) простой образ: если одно слово — пытаемся найти entry
        #    иначе ищем по ключевому слову (первое "животное-похожее" слово)
        key = animal_scene.strip()
        if " " in key:
            # crude key guess: take first token (лучше потом улучшить под формат файла)
            key = key.split()[0]

        entry = _extract_symbolism_entry(symbolism_raw or "", key) if symbolism_raw else None

        if not entry:
            # строго: не домысливаем. просто сообщаем, что в файле не найдено.
            await msg.reply_text(
                "Не нашла этот образ в файле «Символизм» (в базе знаний). "
                "Чтобы я продолжила строго по структуре, образ должен совпасть с формулировкой/словом из файла."
            )
            return

        # 3) отдать символический блок (и только его формулировки)
        parts = []
        parts.append("**Этап 3: Символический анализ (по файлу «Символизм»)**")
        parts.append(entry)

        # 4) гипотеза (без добавочных вопросов)
        parts.append("\n**Этап 4: Гипотеза**")
        parts.append(
            "Связка:\n"
            f"— Чувства/реакция: {feelings}\n"
            f"— Образ: {animal_scene}\n"
            "— Значения и уточнения: см. блок символизма выше.\n\n"
            "Гипотеза формулируется на основе этих трёх уровней. "
            "Если нужно — уточнения задаются только теми вопросами, которые уже перечислены в блоке «Символизм»."
        )

        await msg.reply_text("\n\n".join(parts), parse_mode="Markdown")
        return

    # Если зверя не было (позитивные чувства => Этап 4 сразу), то гипотеза без символизма
    parts = []
    parts.append("**Этап 4: Гипотеза**")
    parts.append(
        "По алгоритму при ресурсных/позитивных чувствах этап зверя пропускается.\n"
        f"— Чувства/ощущения: {feelings}\n"
        "Гипотеза формулируется только на основе запроса и реакций, без символического разбора."
    )
    await msg.reply_text("\n\n".join(parts), parse_mode="Markdown")
