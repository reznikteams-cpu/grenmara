# TG AI RAG Paid Bot

Платный Telegram-бот на базе LLM, который отвечает с опорой на Google Docs (RAG),
умеет делать рассылки/пуши через админку в Telegram и управляет доступом по подписке.

## Возможности
- Paywall: демо-лимит для новых, доступ по `is_active_subscription`
- RAG: загрузка Google Docs через export-URL, чанкинг, эмбеддинги, поиск top-k
- Админка в Telegram: /admin, /broadcast, /push_add, /push_schedule, /stats
- Уведомления: напоминания неактивным + опциональные рассылки по сегментам
- Хранилище: SQLite (по умолчанию)

## Быстрый старт (локально)
1) Создай бота у @BotFather и получи токен
2) Скопируй `.env.example` → `.env` и заполни
3) Установи зависимости:
   ```bash
   pip install -r requirements.txt
