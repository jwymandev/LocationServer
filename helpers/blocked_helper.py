import asyncpg


async def is_user_blocked(db: asyncpg.Connection, blocker_id: str, blocked_id: str) -> bool:
    row = await db.fetchrow(
        "SELECT 1 FROM blocked_users WHERE blocker_id=$1 AND blocked_id=$2",
        blocker_id,
        blocked_id
    )
    return row is not None