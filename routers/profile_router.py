# routers/profile_router.py
import json
import asyncpg
from fastapi import APIRouter, HTTPException, Depends

# Import from modules
from dependencies import get_db, verify_api_key, verify_rocketchat_auth
from models.profile_models import CoreProfile, ExtendedProfile, CombinedProfile

# Create an APIRouter instance
router = APIRouter()

@router.get("/{user_id}", response_model=CombinedProfile)
async def get_profile(
    user_id: str, 
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    """Get a user's profile by user ID."""
    row = await db.fetchrow("SELECT * FROM profiles WHERE user_id=$1", user_id)
    
    if row is None:
        # Return a default profile instead of 404
        core = CoreProfile(
            user_id=user_id,
            username="DefaultUsername",
            name="Default Name",
            avatar=None
        )
        ext = ExtendedProfile(
            birthday="1970-01-01",
            hometown=None,
            description=None,
            interests=None
        )
        return CombinedProfile(coreProfile=core, extendedProfile=ext)
    
    profile_dict = dict(row)
    default_birthday = "1970-01-01"
    
    core = CoreProfile(
        user_id=profile_dict.get("user_id"),
        username=profile_dict.get("username"),
        name=profile_dict.get("name"),
        avatar=profile_dict.get("avatar")
    )
    
    ext = ExtendedProfile(
        birthday=profile_dict.get("birthday") or default_birthday,
        hometown=profile_dict.get("hometown"),
        description=profile_dict.get("description"),
        interests=profile_dict.get("interests")
    )
    
    return CombinedProfile(coreProfile=core, extendedProfile=ext)

@router.put("/{user_id}", response_model=CombinedProfile)
async def update_profile(
    user_id: str, 
    profile: CombinedProfile, 
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    """Update a user's profile."""
    if user_id != profile.coreProfile.user_id:
        raise HTTPException(status_code=400, detail="User ID in path must match user ID in profile")
    
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
        user_id=updated.get("user_id"),
        username=updated.get("username"),
        name=updated.get("name"),
        avatar=updated.get("avatar")
    )
    
    ext = ExtendedProfile(
        birthday=updated.get("birthday"),
        hometown=updated.get("hometown"),
        description=updated.get("description"),
        interests=updated.get("interests")
    )
    
    # Return directly as CombinedProfile to match the response_model
    return CombinedProfile(coreProfile=core, extendedProfile=ext)