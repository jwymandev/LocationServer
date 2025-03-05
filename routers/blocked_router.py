from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg
from dependencies import get_db, get_current_user_id, verify_rocketchat_auth

router = APIRouter()

@router.post("/block", response_model=dict)
async def block_user(
    blocked_id: str,
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    # Insert a record into the blocked_users table.
    try:
        await db.execute(
            """
            INSERT INTO blocked_users (blocker_id, blocked_id)
            VALUES ($1, $2)
            """,
            current_user, blocked_id
        )
        return {"status": "success", "message": "User blocked successfully."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/unblock", response_model=dict)
async def unblock_user(
    blocked_id: str,
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    try:
        await db.execute(
            """
            DELETE FROM blocked_users
            WHERE blocker_id = $1 AND blocked_id = $2
            """,
            current_user, blocked_id
        )
        return {"status": "success", "message": "User unblocked successfully."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))