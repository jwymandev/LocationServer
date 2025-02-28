from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel
from typing import List, Optional
import asyncpg
import json
from contextlib import asynccontextmanager

router = APIRouter(prefix="/profile", tags=["profile"])

# Define your Pydantic model for profile data.
class Profile(BaseModel):
    user_id: str
    name: str
    hometown: Optional[str] = None
    description: Optional[str] = None
    profile_pictures: Optional[List[str]] = None
    albums: Optional[List[dict]] = None
    travel_plans: Optional[List[dict]] = None
    interests: Optional[List[str]] = None

# Dependency to get a database connection.
async def get_db(request: Request) -> asyncpg.Connection:
    pool = request.app.state.db_pool
    async with pool.acquire() as connection:
        yield connection

@router.get("/{user_id}", response_model=Profile)
async def get_profile(user_id: str, db: asyncpg.Connection = Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM profiles WHERE user_id=$1", user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile_dict = dict(row)
    return Profile(**profile_dict)

@router.put("/{user_id}", response_model=Profile)
async def update_profile(user_id: str, profile: Profile, db: asyncpg.Connection = Depends(get_db)):
    # (Perform authentication check as needed.)
    query = """
    INSERT INTO profiles (user_id, name, hometown, description, profile_pictures, albums, travel_plans, interests)
    VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb)
    ON CONFLICT (user_id)
    DO UPDATE SET
        name = EXCLUDED.name,
        hometown = EXCLUDED.hometown,
        description = EXCLUDED.description,
        profile_pictures = EXCLUDED.profile_pictures,
        albums = EXCLUDED.albums,
        travel_plans = EXCLUDED.travel_plans,
        interests = EXCLUDED.interests
    RETURNING *;
    """
    row = await db.fetchrow(
        query,
        profile.user_id,
        profile.name,
        profile.hometown,
        profile.description,
        json.dumps(profile.profile_pictures) if profile.profile_pictures is not None else None,
        json.dumps(profile.albums) if profile.albums is not None else None,
        json.dumps(profile.travel_plans) if profile.travel_plans is not None else None,
        json.dumps(profile.interests) if profile.interests is not None else None,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Profile update failed")
    return Profile(**dict(row))