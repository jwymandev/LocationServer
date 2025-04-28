import json
import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from typing import List, Optional
from dependencies import get_db, verify_rocketchat_auth
import asyncpg

router = APIRouter()

# Define get_current_user_id locally since it's not available in dependencies
async def get_current_user_id(request: Request):
    """Get current user ID from the X-User-Id header."""
    user_id = request.headers.get("X-User-Id")
    
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Missing X-User-Id header"
        )
    
    return user_id

@router.post("/add")
async def add_favorite(
    favorite_user_id: str = Body(..., embed=True),
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    """Add a user to favorites."""
    # Check if user exists
    user_exists = await db.fetchval("SELECT EXISTS(SELECT 1 FROM profiles WHERE user_id = $1)", favorite_user_id)
    if not user_exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if already favorited
    already_favorited = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM user_favorites WHERE user_id = $1 AND favorite_user_id = $2)",
        current_user, favorite_user_id
    )
    
    if already_favorited:
        raise HTTPException(status_code=400, detail="User is already favorited")
    
    # Create favorite record
    favorite_id = str(uuid.uuid4())
    created_at = datetime.datetime.now()
    
    try:
        await db.execute(
            """
            INSERT INTO user_favorites (favorite_id, user_id, favorite_user_id, created_at)
            VALUES ($1, $2, $3, $4)
            """,
            favorite_id, current_user, favorite_user_id, created_at
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add favorite: {str(e)}")
    
    # Get profile info for the favorited user
    profile = await db.fetchrow("SELECT * FROM profiles WHERE user_id = $1", favorite_user_id)
    
    if not profile:
        return {
            "favorite_id": favorite_id,
            "user_id": current_user,
            "favorite_user_id": favorite_user_id,
            "created_at": created_at.isoformat(),
            "profile": None
        }
    
    # Convert the profile to a dictionary
    profile_dict = dict(profile)
    
    # Parse interests JSON if present
    if profile_dict.get("interests") and isinstance(profile_dict["interests"], str):
        try:
            profile_dict["interests"] = json.loads(profile_dict["interests"])
        except:
            profile_dict["interests"] = []
    
    return {
        "favorite_id": favorite_id,
        "user_id": current_user,
        "favorite_user_id": favorite_user_id,
        "created_at": created_at.isoformat(),
        "profile": profile_dict
    }

@router.post("/remove")
async def remove_favorite(
    favorite_id: str = Body(..., embed=True),
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    """Remove a user from favorites."""
    # Verify ownership before deletion
    favorite = await db.fetchrow(
        "SELECT * FROM user_favorites WHERE favorite_id = $1",
        favorite_id
    )
    
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")
    
    if favorite["user_id"] != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to remove this favorite")
    
    # Remove the favorite
    await db.execute(
        "DELETE FROM user_favorites WHERE favorite_id = $1",
        favorite_id
    )
    
    return {"success": True, "message": "Favorite removed successfully"}

@router.get("")
async def get_favorites(
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    """Get the list of user's favorites with profile information."""
    favorites = await db.fetch(
        """
        SELECT f.favorite_id, f.user_id, f.favorite_user_id, f.created_at, p.*
        FROM user_favorites f
        LEFT JOIN profiles p ON f.favorite_user_id = p.user_id
        WHERE f.user_id = $1
        """,
        current_user
    )
    
    result = []
    for row in favorites:
        # Extract favorite info and profile
        favorite_info = {
            "id": row["favorite_id"],
            "user_id": row["user_id"],
            "favorite_user_id": row["favorite_user_id"],
            "created_at": row["created_at"].isoformat()
        }
        
        # Extract profile info
        profile = {
            "user_id": row["user_id"],
            "username": row["username"],
            "name": row["name"],
            "avatar": row["avatar"],
            "birthday": row["birthday"].isoformat() if row["birthday"] else None,
            "hometown": row["hometown"],
            "description": row["description"]
        }
        
        # Parse interests JSON if present
        if row.get("interests") and isinstance(row["interests"], str):
            try:
                profile["interests"] = json.loads(row["interests"])
            except:
                profile["interests"] = []
        else:
            profile["interests"] = row.get("interests", [])
        
        favorite_info["profile"] = profile
        result.append(favorite_info)
    
    return result

@router.get("/check/{user_id}")
async def check_if_favorited(
    user_id: str,
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    """Check if a user is in the current user's favorites."""
    favorite = await db.fetchrow(
        """
        SELECT favorite_id FROM user_favorites 
        WHERE user_id = $1 AND favorite_user_id = $2
        """,
        current_user, user_id
    )
    
    if favorite:
        return {
            "is_favorited": True,
            "favorite_id": favorite["favorite_id"]
        }
    else:
        return {
            "is_favorited": False,
            "favorite_id": None
        }