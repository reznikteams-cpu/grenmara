from __future__ import annotations
import asyncio
import logging

log = logging.getLogger(__name__)

def due_pushes_job(repo, scheduler_service):
    # called from thread; run async via loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.create_task(_send_due(repo, scheduler_service))

async def _send_due(repo, scheduler_service):
    from telegram import Bot
    bot = Bot(scheduler_service.settings.telegram_bot_token)

    due = repo.get_due_pushes()
    if not due:
        return

    for push in due:
        push_id = int(push["id"])
        segment = push["segment"]
        text = push["text"]
        user_ids = repo.list_users_by_segment(segment)

        ok = 0
        for uid in user_ids:
            try:
                await bot.send_message(chat_id=uid, text=text)
                ok += 1
                await asyncio.sleep(0.05)
            except Exception:
                continue

        repo.mark_push_sent(push_id)
        log.info("Push %s sent to %s users in segment=%s", push_id, ok, segment)
