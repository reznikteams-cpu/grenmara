from __future__ import annotations

import logging
import re
from telegram.ext import ContextTypes

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


def _norm(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    # убрать «мусор» по краям: эмодзи, тире, двоеточия, маркеры
    s = re.sub(r"^[^\wа-яё]+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^\wа-яё]+$", "", s, flags=re.IGNORECASE)
    # схлопнуть пробелы
    s = re.sub(r"\s+", " ", s)
    return s


def _guess_key(animal_scene: str) -> str:
    """
    Берем первое 'слово из букв' (кириллица/латиница), игнорируя эмодзи/знаки.
    Пример: '🐘 Слон на дороге' -> 'слон'
            'Тигрица, на которую нападают' -> 'тигрица'
    """
    t = _norm(animal_scene)
    m = re.search(r"[a-zа-яё]+", t, flags=re.IGNORECASE)
    return (m.group(0) if m else t).strip()


def _extract_symbolism_entry(raw_text: str, key: str) -> str | None:
    """
    Находит блок по ключу даже если заголовок выглядит как:
    '🐘 Слон', '— Слон', 'Слон:', 'СЛОН', etc.
    """
    if not raw_text:
        return None

    k = _norm(key)
    if not k:
        return None

    lines = raw_text.splitlines()

    def clean_heading(line: str) -> str:
        # нормализуем строку и отдельно убираем распространенные разделители внутри
        x = _norm(line)
        x = x.replace(":", "").replace("—", " ").replace("-", " ")
        x = re.sub(r"\s+", " ", x).strip()
        return x

    start_idx = None
    for i, ln in enumerate(lines):
        l = ln.strip()
        if not l:
            continue

        h = clean_heading(l)

        # точное совпадение заголовка: "слон" или "слон (что-то)" или "слон — ..."
        if h == k or h.startswith(k + " ") or h.startswith(k + "("):
            start_idx = i
            break

        # ключ как отдельное слово в начале (после эмодзи/тире): "слон ..." 
        if re.match(rf"^{re.escape(k)}\b", h, flags=re.IGNORECASE):
            start_idx = i
            break

    if start_idx is None:
        return None

    out = [lines[start_idx].rstrip()]

    # соберем тело до следующего “похожего заголовка” или пустой строки
    for j in range(start_idx + 1, min(start_idx + 200, len(lines))):
        ln = lines[j].rstrip()
        if not ln.strip():
            if len(out) > 1:
                break
            continue

        # если встретили новый заголовок (эмодзи/тире + одно слово/короткая строка)
        h = clean_heading(ln)
        if len(out) > 3 and (len(h) <= 40) and re.match(r"^[a-zа-яё0-9 ]+$", h, flags=re.IGNORECASE):
            # эвристика: короткая "чистая" строка — вероятный заголовок следующего символа
            # но не режем, если это продолжение вопроса/списка
            if not h.startswith(("—", "-", "*")):
                # если это не похоже на продолжение пункта
                break

        out.append(ln)

    text = "\n".join(out).strip()
    return text if text else None



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

    # Этап 0: запрос/ситуация (то, что человек хочет обсудить)
    if stage == STAGE_SITUATION:
        ud["situation"] = text
        ud["stage"] = STAGE_FEELINGS
        await msg.reply_text('Что ты чувствуешь в этой ситуации? Напиши все чувства и телесные ощущения.')
        return

    # Этап 1: чувства
    if stage == STAGE_FEELINGS:
        ud["feelings"] = text

        # позитивные чувства => сразу гипотеза (Этап 4), пропуская зверя
        if _is_positive_feelings(text):
            ud["stage"] = STAGE_ANALYSIS
            ud["animal_scene"] = None
            ud["animal_self"] = None
            await _send_hypothesis_strict(update, context, repo)
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
        await _send_hypothesis_strict(update, context, repo)
        ud["stage"] = STAGE_DONE
        return

    # Уточнение "Кем ты себя ощущаешь"
    if stage == STAGE_ANIMAL_SELF:
        ud["animal_self"] = text
        ud["stage"] = STAGE_ANALYSIS
        await _send_hypothesis_strict(update, context, repo)
        ud["stage"] = STAGE_DONE
        return

    # Если пользователь пишет дальше — начинаем новый цикл с Этапа 0 (без лишних вопросов)
    ud.clear()
    ud["stage"] = STAGE_SITUATION
    await msg.reply_text("Что ты хочешь обсудить? Опиши ситуацию/запрос одним сообщением.")


async def _send_hypothesis_strict(update, context, repo):
    """
    Строго:
    - символизм и вопросы берём ТОЛЬКО из файла "Символизм" (в KB как raw_text)
    - никаких дополнительных вопросов, которых нет в алгоритме
    """
    msg = update.effective_message
    ud = _ud(context)

    situation = ud.get("situation") or "—"
    feelings = ud.get("feelings") or "—"
    animal_scene = ud.get("animal_scene")
    animal_self = ud.get("animal_self")

    symbolism_raw = repo.get_document_raw_text_by_title("symbolism")
    if not symbolism_raw:
        symbolism_raw = repo.get_document_raw_text_by_title("Символизм")

    # Если зверя не было (ресурсные чувства) — гипотеза без символизма
    if not animal_scene:
        await msg.reply_text(
            "**Этап 4: Гипотеза**\n\n"
            "По алгоритму при ресурсных/позитивных чувствах этап зверя пропускается.\n"
            f"— Ситуация/запрос: {situation}\n"
            f"— Чувства/ощущения: {feelings}\n",
            parse_mode="Markdown"
        )
        return

    # Ключ для поиска в символизме: для простого образа — одно слово; для сцены — первое слово (потом улучшим под формат файла)
    key = animal_scene.strip()
    if " " in key:
        key = key.split()[0]

    entry = _extract_symbolism_entry(symbolism_raw or "", key) if symbolism_raw else None
    if not entry:
        await msg.reply_text(
            "Не нашла этот образ в файле «Символизм» (в базе знаний). "
            "Чтобы продолжить строго по структуре, образ должен совпасть с формулировкой/словом из файла."
        )
        return

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
