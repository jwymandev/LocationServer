import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from models.album_model import Album
from dependencies import get_db, get_current_user_id  # Your helper dependencies
import asyncpg

router = APIRouter()

@router.post("/", response_model=Album)
async def create_album(
    album: Album,
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id)
):
    # Ensure the album is being created by the current user.
    if album.user_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot create album for another user")
    
    # Validate permission if needed
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
    current_user: str = Depends(get_current_user_id)
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
            SET title=$1, description=$2, images=$3::jsonb, public=$4
            WHERE album_id=$5
            RETURNING *
            """,
            album.title,
            album.description,
            json.dumps(album.images),
            album.public,
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
    current_user: str = Depends(get_current_user_id)
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
            # In case the JSON is stored as a string, decode it.
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
    db: asyncpg.Connection = Depends(get_db)
):
    # Return only public albums for now.
    rows = await db.fetch("SELECT * FROM albums WHERE public = TRUE")
    return [Album(**dict(row)) for row in rows]

@router.get("/myalbums", response_model=List[Album])
async def list_albums(
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id)
):
    # This query can be adjusted. Here, we assume that public albums are visible to everyone,
    # and restricted albums are visible only if the current user is the owner or is in allowed_users.
    rows = await db.fetch("""
        SELECT * FROM albums
        WHERE permission = 'public'
           OR user_id = $1
           OR (permission = 'restricted' AND $1 = ANY(allowed_users))
    """, current_user)
    return [Album(**dict(row)) for row in rows]