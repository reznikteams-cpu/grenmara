from __future__ import annotations
from app.storage.repo import Repo

def can_use_ai(repo: Repo, user_id: int, free_trial_messages: int) -> tuple[bool, str]:
    user = repo.get_user(user_id)
    if not user:
        return True, ""

    if int(user["is_active_subscription"]) == 1:
        return True, ""

    used = int(user["free_messages_used"] or 0)
    if used < free_trial_messages:
        return True, f"Демо-доступ: {used+1}/{free_trial_messages}"

    return False, "Демо-лимит исчерпан. Оформи подписку, чтобы продолжить 🤍"
