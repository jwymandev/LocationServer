# routers/profile_router.py
import json
import asyncpg
from fastapi import APIRouter, HTTPException, Depends

# Import from modules
from dependencies import get_db, verify_api_key, verify_rocketchat_auth
from models.profile_models import CoreProfile, ExtendedProfile, CombinedProfile
from models.shared import APIResponse

# Create an APIRouter instance
router = APIRouter()

@router.get("/{user_id}", response_model=APIResponse[CombinedProfile])
async def get_profile(
    user_id: str, 
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    row = await db.fetchrow("SELECT * FROM profiles WHERE user_id=$1", user_id)
    
    if row is None:
        # Create a default profile in the database instead of just returning a temporary one
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
        
        # Create a default profile in the database
        combined = CombinedProfile(coreProfile=core, extendedProfile=ext)
        
        # Insert the default profile
        try:
            query = """
            INSERT INTO profiles (user_id, username, name, avatar, birthday, hometown, description, interests)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *;
            """
            
            row = await db.fetchrow(
                query,
                user_id,
                "DefaultUsername",
                "Default Name",
                None,
                "1970-01-01",
                None,
                None,
                None
            )
            
            if row is None:
                print(f"Failed to create default profile for user {user_id}")
                # Even if DB insert fails, still return something
                return {
                    "status": "success",
                    "data": combined,
                    "message": "Temporary profile. Please update your profile."
                }
            
            # Successfully created profile
            profile_dict = dict(row)
            
            # Create a default profile album for the user
            from routers.album_router import ensure_profile_album_exists
            await ensure_profile_album_exists(user_id, db)
            
        except Exception as e:
            print(f"Error creating default profile: {str(e)}")
            # Return the default profile even if DB operation failed
            return {
                "status": "success",
                "data": combined,
                "message": "Temporary profile. Please update your profile."
            }
    else:
        # Profile already exists
        profile_dict = dict(row)
        
        # Ensure profile album exists
        from routers.album_router import ensure_profile_album_exists
        await ensure_profile_album_exists(user_id, db)
    
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
    combined = CombinedProfile(coreProfile=core, extendedProfile=ext)

    # Get profile album information
    try:
        album_row = await db.fetchrow(
            "SELECT * FROM albums WHERE user_id = $1 AND is_profile_album = TRUE", 
            user_id
        )
        
        if album_row:
            album_dict = dict(album_row)
            album_id = album_dict.get("album_id")
            
            # Include album ID in the response
            combined.profileAlbumId = album_id
    except Exception as e:
        print(f"Error getting profile album: {str(e)}")

    return {
        "status": "success",
        "data": combined,
        "message": ""
    }


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
    
    # Prepare interests data
    interests_json = None
    if profile.extendedProfile.interests is not None:
        try:
            interests_json = json.dumps(profile.extendedProfile.interests)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to encode interests: {str(e)}")
    
    query = """
    INSERT INTO profiles (user_id, username, name, avatar, birthday, hometown, description, interests)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
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
    
    try:
        row = await db.fetchrow(
            query,
            profile.coreProfile.user_id,
            profile.coreProfile.username,
            profile.coreProfile.name,
            profile.coreProfile.avatar,
            profile.extendedProfile.birthday,
            profile.extendedProfile.hometown,
            profile.extendedProfile.description,
            interests_json
        )
        
        if row is None:
            raise HTTPException(status_code=500, detail="Profile update failed - no rows returned")
            
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
        
        return CombinedProfile(coreProfile=core, extendedProfile=ext)
        
    except Exception as e:
        # Log the error for debugging
        print(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")