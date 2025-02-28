from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel
from typing import List, Optional
import asyncpg
import json

router = APIRouter(prefix="/profile", tags=["profile"])

# Define your Pydantic models

class CoreProfile(BaseModel):
    user_id: str
    username: str
    name: str
    avatar: Optional[str] = None   # Base64 or binary as text

class ExtendedProfile(BaseModel):
    birthday: str                 # Expected format "yyyy-mm-dd"
    hometown: Optional[str] = None
    description: Optional[str] = None
    interests: Optional[List[str]] = None

class CombinedProfile(BaseModel):
    coreProfile: CoreProfile
    extendedProfile: ExtendedProfile

# Dependency to get a database connection.
async def get_db(request: Request) -> asyncpg.Connection:
    pool = request.app.state.db_pool
    async with pool.acquire() as connection:
        yield connection

@router.get("/{user_id}", response_model=CombinedProfile)
async def get_profile(user_id: str, db: asyncpg.Connection = Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM profiles WHERE user_id=$1", user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile_dict = dict(row)
    # Create the core and extended profile parts.
    core = CoreProfile(
        user_id = profile_dict.get("user_id"),
        username = profile_dict.get("username"),
        name = profile_dict.get("name"),
        avatar = profile_dict.get("avatar")
    )
    ext = ExtendedProfile(
        birthday = profile_dict.get("birthday"),
        hometown = profile_dict.get("hometown"),
        description = profile_dict.get("description"),
        interests = profile_dict.get("interests")  # assuming this is stored as JSON in the DB
    )
    return CombinedProfile(coreProfile=core, extendedProfile=ext)

@router.put("/{user_id}", response_model=CombinedProfile)
async def update_profile(user_id: str, profile: CombinedProfile, db: asyncpg.Connection = Depends(get_db)):
    # Here we update all fields (both core and extended) in one query.
    query = """
    INSERT INTO profiles (user_id, username, name, avatar, birthday, hometown, description, interests)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
    ON CONFLICT (user_id)
    DO UPDATE SET
        username = EXCLUDED.username,
        name = EXCLUDED.name,
        avatar = EXCLUDED.avatar,
        birthday = EXCLUDED.birthday,
        hometown = EXCLUDED.hometown,
        description = EXCLUDED.description,
        interests = EXCLUDED.interests
    RETURNING *;
    """
    # Note: interests is converted to JSON.
    row = await db.fetchrow(
        query,
        profile.coreProfile.user_id,
        profile.coreProfile.username,
        profile.coreProfile.name,
        profile.coreProfile.avatar,
        profile.extendedProfile.birthday,
        profile.extendedProfile.hometown,
        profile.extendedProfile.description,
        json.dumps(profile.extendedProfile.interests) if profile.extendedProfile.interests is not None else None,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Profile update failed")
    updated = dict(row)
    core = CoreProfile(
        user_id = updated.get("user_id"),
        username = updated.get("username"),
        name = updated.get("name"),
        avatar = updated.get("avatar")
    )
    ext = ExtendedProfile(
        birthday = updated.get("birthday"),
        hometown = updated.get("hometown"),
        description = updated.get("description"),
        interests = updated.get("interests")
    )
    return CombinedProfile(coreProfile=core, extendedProfile=ext)