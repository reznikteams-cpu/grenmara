from __future__ import annotations
import asyncio
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.storage.db import Database
from app.storage.repo import Repo
from app.push.jobs import due_pushes_job

log = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self, db: Database, settings):
        self.db = db
        self.repo = Repo(db)
        self.settings = settings
        self.scheduler = BackgroundScheduler(timezone=settings.scheduler_tz)
        self.telegram_app = None  # injected later by send methods

    def start(self) -> None:
        self.scheduler.add_job(
            lambda: due_pushes_job(self.repo, self),
            trigger=IntervalTrigger(seconds=30),
            id="due_pushes",
            replace_existing=True,
        )
        self.scheduler.start()
        log.info("Scheduler started")

    async def send_broadcast_now(self, broadcast_id: int, segment: str, text: str):
        # Needs telegram bot instance; we fetch it lazily from running application
        # The PTB Application is global in app.main; simplest: use Bot token directly here
        # but for template keep it minimal: use raw HTTP via telegram bot api
        from telegram import Bot
        bot = Bot(self.settings.telegram_bot_token)

        user_ids = self.repo.list_users_by_segment(segment)
        sent = 0
        for uid in user_ids:
            try:
                await bot.send_message(chat_id=uid, text=text)
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                continue
        return sent
