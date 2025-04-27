import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from models.album_model import Album
from dependencies import get_db, get_current_user_id, verify_rocketchat_auth  # Added verify_rocketchat_auth
import asyncpg

router = APIRouter()

@router.post("/", response_model=Album)
async def create_album(
    album: Album,
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)  # Verifies Rocket.Chat login
):
    # Ensure the album is being created by the current user.
    if album.user_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot create album for another user")
    
    # Validate permission if needed (assuming your Album model has a validate_permission method)
    album.permission = Album.validate_permission(album.permission)
    
    # Generate a unique album ID.
    album_id = str(uuid.uuid4())
    album.album_id = album_id

    try:
        row = await db.fetchrow(
            """
            INSERT INTO albums (album_id, user_id, title, description, images, permission, allowed_users)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb)
            RETURNING *
            """,
            album.album_id,
            album.user_id,
            album.title,
            album.description,
            json.dumps(album.images),
            album.permission,
            json.dumps(album.allowed_users) if album.allowed_users else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    
    if row is None:
        raise HTTPException(status_code=500, detail="Album creation failed")
    
    return Album(**dict(row))


@router.put("/{album_id}", response_model=Album)
async def update_album(
    album_id: str,
    album: Album,
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)  # Verify Rocket.Chat login
):
    # Fetch the existing album.
    existing = await db.fetchrow("SELECT * FROM albums WHERE album_id=$1", album_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Only the owner can update the album.
    if existing["user_id"] != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to update this album")
    
    try:
        row = await db.fetchrow(
            """
            UPDATE albums
            SET title=$1, description=$2, images=$3::jsonb, permission=$4, allowed_users=$5::jsonb
            WHERE album_id=$6
            RETURNING *
            """,
            album.title,
            album.description,
            json.dumps(album.images),
            album.permission,
            json.dumps(album.allowed_users) if album.allowed_users else None,
            album_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    
    if row is None:
        raise HTTPException(status_code=500, detail="Album update failed")
    
    return Album(**dict(row))


@router.get("/{album_id}", response_model=Album)
async def get_album(
    album_id: str,
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)  # Verify Rocket.Chat login
):
    album = await db.fetchrow("SELECT * FROM albums WHERE album_id=$1", album_id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    album_dict = dict(album)
    
    # Check permission:
    # If the album is public, allow.
    # If private, only allow the owner.
    # If restricted, allow if current_user is the owner or is in allowed_users.
    permission = album_dict.get("permission")
    owner = album_dict.get("user_id")
    allowed_users_json = album_dict.get("allowed_users")
    
    allowed_users: List[str] = []
    if allowed_users_json is not None:
        if isinstance(allowed_users_json, str):
            allowed_users = json.loads(allowed_users_json)
        elif isinstance(allowed_users_json, list):
            allowed_users = allowed_users_json
    
    if permission == "private" and current_user != owner:
        raise HTTPException(status_code=403, detail="Not authorized to view this album")
    if permission == "restricted" and current_user != owner and current_user not in allowed_users:
        raise HTTPException(status_code=403, detail="Not authorized to view this album")
    
    return Album(**album_dict)


@router.get("/", response_model=List[Album])
async def list_albums(
    db: asyncpg.Connection = Depends(get_db),
    auth_verified: bool = Depends(verify_rocketchat_auth)  # Optionally verify auth
):
    # Return only public albums for now.
    rows = await db.fetch("SELECT * FROM albums WHERE permission = 'public'")
    return [Album(**dict(row)) for row in rows]


@router.get("/myalbums", response_model=List[Album])
async def list_myalbums(
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    # Return albums visible to the current user:
    rows = await db.fetch("""
        SELECT * FROM albums
        WHERE permission = 'public'
           OR user_id = $1
           OR (permission = 'restricted' AND $1 = ANY(allowed_users))
    """, current_user)
    return [Album(**dict(row)) for row in rows]

@router.post("/{album_id}/request-access", response_model=dict)
async def request_album_access(
    album_id: str,
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    # Check if album exists
    album = await db.fetchrow("SELECT * FROM albums WHERE album_id=$1", album_id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Check if album is restricted
    album_dict = dict(album)
    if album_dict.get("permission") != "restricted":
        raise HTTPException(status_code=400, detail="Access request is only applicable for restricted albums")
    
    # Option 1: Insert a record into an access_requests table (preferred for tracking)
    # Option 2: Or update the album record to mark that a request has been made.
    # For demonstration, we assume Option 1.
    try:
        await db.execute(
            """
            INSERT INTO album_access_requests (request_id, album_id, requester_id, status)
            VALUES ($1, $2, $3, $4)
            """,
            str(uuid.uuid4()),
            album_id,
            current_user,
            "pending"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating access request: {e}")
    
    return {"status": "success", "message": "Access request submitted"}