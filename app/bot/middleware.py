from __future__ import annotations
from app.storage.repo import Repo

def is_admin(user_id: int, admin_ids: set[int]) -> bool:
    return user_id in admin_ids

async def touch_user(repo: Repo, tg_user) -> None:
    repo.upsert_user(
        user_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )
