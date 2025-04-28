# routers/profile_router.py
import json
import logging
import asyncpg
from fastapi import APIRouter, HTTPException, Depends, Path, Query
from typing import Optional, List

# Import from modules
from dependencies import get_db, verify_api_key, verify_rocketchat_auth
from models.profile_models import (
    CoreProfile, ExtendedProfile, CombinedProfile, 
    ProfileResponse, ProfileListResponse, ProfileSource
)
from models.shared import APIResponse

# Set up logging
logger = logging.getLogger(__name__)

# Create an APIRouter instance with prefix and tags
router = APIRouter(
    prefix="/api/profile",
    tags=["profiles"],
    responses={404: {"description": "Profile not found"}}
)

@router.get("/{user_id}", response_model=ProfileResponse)
async def get_profile(
    user_id: str = Path(..., description="The user ID to retrieve the profile for"),
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    """
    Retrieve a user's profile by their user ID.
    
    Returns a combined profile with core and extended profile information.
    If the profile doesn't exist, a default profile will be created.
    """
    try:
        row = await db.fetchrow("SELECT * FROM profiles WHERE user_id=$1", user_id)
        
        if row is None:
            # Create a default profile in the database
            core = CoreProfile(
                user_id=user_id,
                username="DefaultUsername",
                name="Default Name",
                avatar=None
            )
            ext = ExtendedProfile(
                birthday=None,
                hometown=None,
                description=None,
                interests=[],
                height=None,
                weight=None,
                position=None
            )
            
            # Create a default profile in the database
            combined = CombinedProfile(coreProfile=core, extendedProfile=ext)
            
            # Insert the default profile
            try:
                query = """
                INSERT INTO profiles (user_id, username, name, avatar, birthday, hometown, description, interests, height, weight, position)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING *;
                """
                
                row = await db.fetchrow(
                    query,
                    user_id,
                    "DefaultUsername",
                    "Default Name",
                    None,
                    None,
                    None,
                    None,
                    json.dumps([]),
                    None,
                    None,
                    None
                )
                
                if row is None:
                    logger.error(f"Failed to create default profile for user {user_id}")
                    # Even if DB insert fails, still return something
                    return ProfileResponse(
                        success=True,
                        profile=combined,
                        message="Temporary profile. Please update your profile.",
                        source=ProfileSource.CUSTOM
                    )
                
                # Successfully created profile
                profile_dict = dict(row)
                
                # Create a default profile album for the user
                from routers.album_router import ensure_profile_album_exists
                await ensure_profile_album_exists(user_id, db)
                
            except Exception as e:
                logger.error(f"Error creating default profile: {str(e)}")
                # Return the default profile even if DB operation failed
                return ProfileResponse(
                    success=True,
                    profile=combined,
                    message="Temporary profile. Please update your profile.",
                    source=ProfileSource.CUSTOM
                )
        else:
            # Profile already exists
            profile_dict = dict(row)
            
            # Ensure profile album exists
            from routers.album_router import ensure_profile_album_exists
            await ensure_profile_album_exists(user_id, db)
        
        # Create core profile
        core = CoreProfile(
            user_id=profile_dict.get("user_id"),
            username=profile_dict.get("username"),
            name=profile_dict.get("name"),
            avatar=profile_dict.get("avatar")
        )
        
        # Parse interests from JSON if needed
        interests = profile_dict.get("interests", [])
        if isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse interests JSON for user {user_id}, defaulting to empty list")
                interests = []
        
        # Create extended profile
        ext = ExtendedProfile(
            birthday=profile_dict.get("birthday"),
            hometown=profile_dict.get("hometown"),
            description=profile_dict.get("description"),
            interests=interests,
            height=profile_dict.get("height"),
            weight=profile_dict.get("weight"),
            position=profile_dict.get("position")
        )
        
        # Create combined profile
        combined = CombinedProfile(
            coreProfile=core, 
            extendedProfile=ext
        )

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
            logger.error(f"Error getting profile album: {str(e)}")

        return ProfileResponse(
            success=True,
            profile=combined,
            message="",
            source=ProfileSource.COMBINED
        )
    
    except Exception as e:
        logger.error(f"Error retrieving profile for user {user_id}: {str(e)}")
        return ProfileResponse(
            success=False,
            message=f"Failed to retrieve profile: {str(e)}",
            source=ProfileSource.CUSTOM,
            error_code=500
        )


@router.put("/{user_id}", response_model=ProfileResponse)
async def update_profile(
    user_id: str = Path(..., description="The user ID to update the profile for"),
    profile_data: dict = None,
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    """
    Update a user's profile.
    
    Accepts either a full CombinedProfile object or just the fields to update.
    The user ID in the path is used to identify the profile.
    """
    logger.info(f"Received profile update for user {user_id}: {profile_data}")
    
    if not profile_data:
        raise HTTPException(status_code=400, detail="Profile data is required")
        
    # Get existing profile to update
    try:
        existing_row = await db.fetchrow("SELECT * FROM profiles WHERE user_id=$1", user_id)
        if not existing_row:
            logger.warning(f"No existing profile found for user {user_id}, will create new profile")
    except Exception as e:
        logger.error(f"Error fetching profile for update: {str(e)}")
        existing_row = None
    
    # Determine if we're receiving a full CombinedProfile or just fields to update
    if "coreProfile" in profile_data:
        # Full CombinedProfile format
        profile = CombinedProfile(**profile_data)
        if user_id != profile.coreProfile.user_id:
            raise HTTPException(status_code=400, detail="User ID in path must match user ID in profile")
            
        core_profile = profile.coreProfile
        ext_profile = profile.extendedProfile
    else:
        # Just fields to update - create profiles from existing data and updates
        if existing_row:
            existing_data = dict(existing_row)
            
            # Create core profile from existing data
            core_profile = CoreProfile(
                user_id=user_id,
                username=existing_data.get("username", "DefaultUsername"),
                name=existing_data.get("name", "Default Name"),
                avatar=existing_data.get("avatar")
            )
            
            # Parse existing interests
            interests = existing_data.get("interests", [])
            if isinstance(interests, str):
                try:
                    interests = json.loads(interests)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse interests JSON, defaulting to empty list")
                    interests = []
                    
            # Create extended profile by merging existing data with updates
            ext_profile = ExtendedProfile(
                birthday=existing_data.get("birthday"),
                hometown=existing_data.get("hometown"),
                description=existing_data.get("description"),
                interests=interests,
                height=existing_data.get("height"),
                weight=existing_data.get("weight"),
                position=existing_data.get("position")
            )
            
            # Update with new values
            for field, value in profile_data.items():
                if hasattr(ext_profile, field):
                    setattr(ext_profile, field, value)
        else:
            # No existing profile, create minimal versions
            core_profile = CoreProfile(
                user_id=user_id,
                username="DefaultUsername",
                name="Default Name",
                avatar=None
            )
            
            # Initialize extended profile with provided data
            ext_profile = ExtendedProfile()
            for field, value in profile_data.items():
                if hasattr(ext_profile, field):
                    setattr(ext_profile, field, value)
    
    # Prepare interests data
    interests_json = "[]"
    if ext_profile and ext_profile.interests is not None:
        try:
            interests_json = json.dumps(ext_profile.interests)
        except Exception as e:
            logger.error(f"Failed to encode interests for user {user_id}: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Failed to encode interests: {str(e)}")
    
    query = """
    INSERT INTO profiles (user_id, username, name, avatar, birthday, hometown, description, interests, height, weight, position)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    ON CONFLICT (user_id)
    DO UPDATE SET
        username = EXCLUDED.username,
        name = EXCLUDED.name,
        avatar = EXCLUDED.avatar,
        birthday = EXCLUDED.birthday,
        hometown = EXCLUDED.hometown,
        description = EXCLUDED.description,
        interests = EXCLUDED.interests,
        height = EXCLUDED.height,
        weight = EXCLUDED.weight,
        position = EXCLUDED.position
    RETURNING *;
    """
    
    try:
        # Handle birthday date format conversion
        birthday_value = None
        if ext_profile.birthday:
            try:
                # If it's already a date object, use it directly
                from datetime import date
                if isinstance(ext_profile.birthday, (date, datetime)):
                    birthday_value = ext_profile.birthday
                else:
                    # Try to parse the string to a date
                    from dateutil import parser
                    birthday_value = parser.parse(ext_profile.birthday).date()
            except Exception as e:
                logger.error(f"Error parsing birthday: {str(e)}")
                # Just use None if there's an error
                birthday_value = None
                
        logger.info(f"Prepared query parameters: user_id={core_profile.user_id}, birthday={birthday_value}, height={ext_profile.height}, weight={ext_profile.weight}, position={ext_profile.position}")
                
        row = await db.fetchrow(
            query,
            core_profile.user_id,
            core_profile.username,
            core_profile.name,
            core_profile.avatar,
            birthday_value,
            ext_profile.hometown,
            ext_profile.description,
            interests_json,
            ext_profile.height,
            ext_profile.weight,
            ext_profile.position
        )
        
        if row is None:
            logger.error(f"Profile update failed for user {user_id} - no rows returned")
            raise HTTPException(status_code=500, detail="Profile update failed - no rows returned")
            
        updated = dict(row)
        
        # Parse interests from JSON if needed
        interests = updated.get("interests", [])
        if isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse interests JSON for updated user {user_id}, defaulting to empty list")
                interests = []
        
        core = CoreProfile(
            user_id=updated.get("user_id"),
            username=updated.get("username"),
            name=updated.get("name"),
            avatar=updated.get("avatar")
        )
        
        # Get birthday value
        birthday_value = updated.get("birthday")
        if isinstance(birthday_value, str):
            try:
                # If it's a string, try to parse it properly for client usage
                from dateutil import parser
                birthday_value = parser.parse(birthday_value).isoformat().split('T')[0]
            except Exception as e:
                logger.error(f"Error parsing birthday string: {str(e)}")
                
        ext = ExtendedProfile(
            birthday=birthday_value,
            hometown=updated.get("hometown"),
            description=updated.get("description"),
            interests=interests,
            height=updated.get("height"),
            weight=updated.get("weight"),
            position=updated.get("position")
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
            logger.error(f"Error getting profile album: {str(e)}")
        
        return ProfileResponse(
            success=True,
            profile=combined,
            message="Profile updated successfully",
            source=ProfileSource.CUSTOM
        )
        
    except Exception as e:
        # Log the error for debugging
        logger.error(f"Database error updating profile for user {user_id}: {str(e)}")
        return ProfileResponse(
            success=False,
            message=f"Failed to update profile: {str(e)}",
            source=ProfileSource.CUSTOM,
            error_code=500
        )

@router.get("/search", response_model=ProfileListResponse)
async def search_profiles(
    query: str = Query(None, description="Search term for profile names or usernames"),
    page: int = Query(1, description="Page number for pagination", ge=1),
    per_page: int = Query(20, description="Results per page", ge=1, le=100),
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    """
    Search for user profiles by name or username.
    
    Returns a paginated list of matching profiles.
    """
    try:
        # Calculate offset for pagination
        offset = (page - 1) * per_page
        
        # Build the SQL query based on whether a search term is provided
        if query:
            # Add full-text search or LIKE patterns for name and username
            count_query = """
            SELECT COUNT(*) FROM profiles 
            WHERE username ILIKE $1 OR name ILIKE $1
            """
            
            search_query = """
            SELECT * FROM profiles 
            WHERE username ILIKE $1 OR name ILIKE $1
            ORDER BY name ASC
            LIMIT $2 OFFSET $3
            """
            
            search_pattern = f"%{query}%"
            count_row = await db.fetchrow(count_query, search_pattern)
            rows = await db.fetch(search_query, search_pattern, per_page, offset)
        else:
            # No search term, return all profiles (paginated)
            count_query = "SELECT COUNT(*) FROM profiles"
            search_query = """
            SELECT * FROM profiles 
            ORDER BY name ASC
            LIMIT $1 OFFSET $2
            """
            
            count_row = await db.fetchrow(count_query)
            rows = await db.fetch(search_query, per_page, offset)
        
        # Get total count
        total_count = count_row["count"] if count_row else 0
        
        # Build profile objects
        profiles = []
        for row in rows:
            profile_dict = dict(row)
            
            # Parse interests from JSON if needed
            interests = profile_dict.get("interests", [])
            if isinstance(interests, str):
                try:
                    interests = json.loads(interests)
                except json.JSONDecodeError:
                    interests = []
            
            core = CoreProfile(
                user_id=profile_dict.get("user_id"),
                username=profile_dict.get("username"),
                name=profile_dict.get("name"),
                avatar=profile_dict.get("avatar")
            )
            
            ext = ExtendedProfile(
                birthday=profile_dict.get("birthday"),
                hometown=profile_dict.get("hometown"),
                description=profile_dict.get("description"),
                interests=interests,
                height=profile_dict.get("height"),
                weight=profile_dict.get("weight"),
                position=profile_dict.get("position")
            )
            
            combined = CombinedProfile(coreProfile=core, extendedProfile=ext)
            profiles.append(combined)
        
        return ProfileListResponse(
            success=True,
            profiles=profiles,
            total=total_count,
            page=page,
            per_page=per_page,
            message=f"Found {len(profiles)} profiles",
            source=ProfileSource.CUSTOM
        )
            
    except Exception as e:
        logger.error(f"Error searching profiles: {str(e)}")
        return ProfileListResponse(
            success=False,
            message=f"Failed to search profiles: {str(e)}",
            source=ProfileSource.CUSTOM,
            error_code=500
        )