from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# stages
STAGE_SITUATION = "situation"
STAGE_FEELINGS = "feelings"
STAGE_ANIMAL = "animal"
STAGE_HYPOTHESIS = "hypothesis"


# ---------- helpers ----------
def _ud(context) -> dict:
    # per-user memory; survives within bot process
    if context.user_data is None:
        context.user_data = {}
    return context.user_data


def _is_positive_feelings(text: str) -> bool:
    t = (text or "").lower()
    positives = ["рад", "радость", "лёгк", "легк", "кайф", "вдохнов", "спокой", "уверен", "приятн"]
    negatives = ["тревог", "страх", "злост", "гнев", "обид", "тяжест", "оцепен", "апат", "стыд", "вина", "напряж"]
    # if contains any negative -> treat as negative
    if any(x in t for x in negatives):
        return False
    if any(x in t for x in positives):
        return True
    # default: treat as negative to continue algorithm
    return False


async def _kb_lookup_symbolism(repo, query: str) -> str | None:
    """
    Tries to retrieve symbolism entry from your KB.
    You may have different repo methods; we attempt several names.
    """
    q = (query or "").strip()
    if not q:
        return None

    # try common method names
    for name in ("kb_search", "search_kb", "knowledge_search", "rag_search", "search_knowledge"):
        fn = getattr(repo, name, None)
        if callable(fn):
            try:
                res = fn(q)
                # allow async or sync
                if hasattr(res, "__await__"):
                    res = await res
                if not res:
                    return None
                # if repo returns list of chunks
                if isinstance(res, list):
                    # take top 1-3 chunks
                    parts = []
                    for item in res[:3]:
                        if isinstance(item, str):
                            parts.append(item)
                        elif isinstance(item, dict):
                            parts.append(item.get("text") or item.get("content") or "")
                        else:
                            parts.append(str(item))
                    txt = "\n\n".join([p for p in parts if p.strip()])
                    return txt.strip() or None
                # if returns string
                if isinstance(res, str):
                    return res.strip() or None
                # fallback
                return str(res).strip() or None
            except Exception:
                log.exception("KB lookup failed for query=%r via %s", q, name)
                return None

    return None


# ---------- commands ----------
async def start(update, context, repo, settings):
    ud = _ud(context)
    ud.clear()
    ud["stage"] = STAGE_SITUATION

    await update.effective_message.reply_text(
        "Опиши ситуацию/запрос одним сообщением.\n\n"
        "Я задам вопросы по методике «Истинный запрос»."
    )


async def help_cmd(update, context):
    await update.effective_message.reply_text(
        "Команды:\n"
        "/start — начать заново\n"
        "/clear — сбросить диалог\n"
        "/profile — профиль\n"
    )


async def profile(update, context, repo, settings):
    await update.effective_message.reply_text("Профиль: в разработке.")


async def clear(update, context, repo):
    ud = _ud(context)
    ud.clear()
    await update.effective_message.reply_text("Ок, сбросила. Напиши /start чтобы начать заново.")


async def subscribe(update, context):
    await update.effective_message.reply_text("Подписка: в разработке.")


# ---------- main flow ----------
async def text_message(update, context, repo, settings):
    msg = update.effective_message
    text = (msg.text or "").strip()
    if not text:
        return

    ud = _ud(context)
    stage = ud.get("stage") or STAGE_SITUATION

    # 0) Situation (not in your excerpt, but needed to anchor "this situation")
    if stage == STAGE_SITUATION:
        ud["situation"] = text
        ud["stage"] = STAGE_FEELINGS
        await msg.reply_text('Что ты чувствуешь в этой ситуации? Напиши все чувства и телесные ощущения.')
        return

    # 1) Feelings
    if stage == STAGE_FEELINGS:
        ud["feelings"] = text

        if _is_positive_feelings(text):
            ud["stage"] = STAGE_HYPOTHESIS
            # go straight to hypothesis (skip animal)
            await _send_hypothesis(update, context, repo, settings, skip_animal=True)
            return

        ud["stage"] = STAGE_ANIMAL
        await msg.reply_text("Представь, что ты — зверь, который это чувствует. Какой зверь пришёл? Где он находится? Что он делает?")
        return

    # 2) Animal
    if stage == STAGE_ANIMAL:
        ud["animal_scene"] = text

        # if multiple animals/scene -> ask уточнение (as per prompt)
        low = text.lower()
        multi_markers = [",", " и ", " рядом", " напротив", " вместе", " нападает", " гонит", " дерутся", " сраж", " кусает"]
        if any(m in low for m in multi_markers):
            ud["stage"] = STAGE_ANIMAL  # keep, but expect "who am I"
            ud["need_self"] = True
            await msg.reply_text("Кем ты себя ощущаешь в этой картинке?")
            return

        # otherwise proceed to symbolism analysis -> hypothesis
        ud["stage"] = STAGE_HYPOTHESIS
        await _send_hypothesis(update, context, repo, settings, skip_animal=False)
        return

    # if waiting for "who am I" уточнение
    if stage == STAGE_ANIMAL and ud.get("need_self"):
        ud["animal_self"] = text
        ud["need_self"] = False
        ud["stage"] = STAGE_HYPOTHESIS
        await _send_hypothesis(update, context, repo, settings, skip_animal=False)
        return

    # 4) Hypothesis stage: treat as new situation unless user explicitly continues
    # (so bot never "stops" after 1 cycle)
    ud.clear()
    ud["stage"] = STAGE_SITUATION
    ud["situation"] = text
    ud["stage"] = STAGE_FEELINGS
    await msg.reply_text('Приняла. Что ты чувствуешь в этой ситуации? Напиши все чувства и телесные ощущения.')


async def _send_hypothesis(update, context, repo, settings, skip_animal: bool):
    msg = update.effective_message
    ud = _ud(context)

    situation = ud.get("situation", "—")
    feelings = ud.get("feelings", "—")
    animal_scene = ud.get("animal_scene", "") if not skip_animal else ""
    animal_self = ud.get("animal_self", "")

    # symbolism lookup (strictly from file: we use KB)
    symbolism_text = None
    if not skip_animal and animal_scene:
        symbolism_text = await _kb_lookup_symbolism(repo, animal_scene)

    # If KB not available, we must not invent symbolism
    if not skip_animal and animal_scene and not symbolism_text:
        await msg.reply_text(
            "Я вижу образ, но сейчас не могу безопасно расшифровать его по «Символизму» (нет доступа к базе символов в боте).\n\n"
            "Проверь, что база знаний загружена (kb_reload) или включи доступ к «Символизм» в KB.\n"
            "Пока — зафиксирую данные и задам следующий вопрос по алгоритму:\n\n"
            "Для чего тебе мог быть нужен этот опыт? Что он показывает твоей психике?"
        )
        return

    # compose hypothesis without adding external knowledge
    parts = []
    parts.append(f"**Запрос / ситуация:** {situation}")
    parts.append(f"**Чувства и телесные ощущения:** {feelings}")

    if not skip_animal:
        parts.append(f"**Образ зверя / сцена:** {animal_scene}")
        if animal_self:
            parts.append(f"**Кем ты себя ощущаешь в картинке:** {animal_self}")

        parts.append("**Символический разбор (по файлу «Символизм»):**")
        parts.append(symbolism_text.strip())

    parts.append("\n**Гипотеза (сборка 3 уровней):**")
    parts.append(
        "Это может быть ситуация, где проявляется внутренний паттерн, связанный с тем, как ты переживаешь напряжение/опасность/контакт в этой истории. "
        "Чтобы не додумывать, я проверю через смысл опыта."
        if not skip_animal else
        "Раз чувства в основном ресурсные/позитивные, я собираю гипотезу напрямую через смысл опыта, без образа зверя."
    )

    parts.append("\n**Вопрос:**")
    parts.append("Для чего тебе мог быть нужен этот опыт? Что он показывает твоей психике?")

    await msg.reply_text("\n\n".join(parts), parse_mode="Markdown")
