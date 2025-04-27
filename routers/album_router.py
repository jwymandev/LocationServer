import json
import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Form, File, UploadFile, Body
from typing import List, Optional
from models.album_model import Album, PhotoItem
from dependencies import get_db, verify_rocketchat_auth, verify_api_key
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

async def ensure_profile_album_exists(user_id: str, db: asyncpg.Connection):
    """Ensure that the user has a profile album, creating one if needed."""
    # Check if user already has a profile album
    album = await db.fetchrow(
        "SELECT * FROM albums WHERE user_id = $1 AND is_profile_album = TRUE",
        user_id
    )
    
    if album is None:
        # Create a default profile album
        album_id = str(uuid.uuid4())
        
        try:
            await db.execute(
                """
                INSERT INTO albums 
                (album_id, user_id, title, description, is_profile_album, photos, permission)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                album_id,
                user_id,
                "Profile Album",
                "My profile pictures",
                True,
                json.dumps([]),  # Empty photos array
                "public"  # Profile albums are public by default
            )
            return album_id
        except Exception as e:
            print(f"Error creating profile album: {e}")
            raise HTTPException(status_code=500, detail="Failed to create profile album")
    else:
        return album["album_id"]

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
    
    # Validate permission
    album.permission = album.validate_permission(album.permission)
    
    # Generate a unique album ID.
    album_id = str(uuid.uuid4())
    album.album_id = album_id

    try:
        row = await db.fetchrow(
            """
            INSERT INTO albums (album_id, user_id, title, description, is_profile_album, photos, permission, allowed_users)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8::jsonb)
            RETURNING *
            """,
            album.album_id,
            album.user_id,
            album.title,
            album.description,
            album.is_profile_album,
            json.dumps([photo.dict() for photo in album.photos]) if album.photos else json.dumps([]),
            album.permission,
            json.dumps(album.allowed_users) if album.allowed_users else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    
    if row is None:
        raise HTTPException(status_code=500, detail="Album creation failed")
    
    album_dict = dict(row)
    # Convert the JSON string to a list of PhotoItem objects
    if album_dict.get("photos"):
        if isinstance(album_dict["photos"], str):
            photos_data = json.loads(album_dict["photos"])
        else:
            photos_data = album_dict["photos"]
            
        album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data]
    else:
        album_dict["photos"] = []
    
    return Album(**album_dict)

@router.post("/profile-album", response_model=Album)
async def get_or_create_profile_album(
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    """Get or create the user's profile album."""
    album_id = await ensure_profile_album_exists(current_user, db)
    
    # Fetch the album
    row = await db.fetchrow("SELECT * FROM albums WHERE album_id = $1", album_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Profile album not found")
    
    album_dict = dict(row)
    # Convert the JSON string to a list of PhotoItem objects
    if album_dict.get("photos"):
        if isinstance(album_dict["photos"], str):
            photos_data = json.loads(album_dict["photos"])
        else:
            photos_data = album_dict["photos"]
            
        album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data]
    else:
        album_dict["photos"] = []
    
    return Album(**album_dict)


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
            SET title=$1, description=$2, photos=$3::jsonb, permission=$4, allowed_users=$5::jsonb
            WHERE album_id=$6
            RETURNING *
            """,
            album.title,
            album.description,
            json.dumps([photo.dict() for photo in album.photos]) if album.photos else json.dumps([]),
            album.permission,
            json.dumps(album.allowed_users) if album.allowed_users else None,
            album_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    
    if row is None:
        raise HTTPException(status_code=500, detail="Album update failed")
    
    album_dict = dict(row)
    # Convert the JSON string to a list of PhotoItem objects
    if album_dict.get("photos"):
        if isinstance(album_dict["photos"], str):
            photos_data = json.loads(album_dict["photos"])
        else:
            photos_data = album_dict["photos"]
            
        album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data]
    else:
        album_dict["photos"] = []
    
    return Album(**album_dict)

@router.post("/{album_id}/photos", response_model=Album)
async def add_photo_to_album(
    album_id: str,
    photo_url: str = Body(..., description="URL of the photo"),
    is_nsfw: bool = Body(False, description="Whether the photo is NSFW"),
    caption: Optional[str] = Body(None, description="Optional caption for the photo"),
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    """Add a photo to an album with NSFW flag."""
    # Get the existing album
    existing = await db.fetchrow("SELECT * FROM albums WHERE album_id=$1", album_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Only the owner can add photos to the album
    if existing["user_id"] != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to add photos to this album")
    
    # Create a new photo item
    photo_id = str(uuid.uuid4())
    new_photo = PhotoItem(
        photo_id=photo_id,
        url=photo_url,
        is_nsfw=is_nsfw,
        caption=caption,
        timestamp=datetime.datetime.now().isoformat()
    )
    
    # Get current photos
    current_photos = []
    if existing.get("photos"):
        if isinstance(existing["photos"], str):
            current_photos = json.loads(existing["photos"])
        else:
            current_photos = existing["photos"]
    
    # Add the new photo
    current_photos.append(new_photo.dict())
    
    # Update the album
    try:
        row = await db.fetchrow(
            """
            UPDATE albums
            SET photos=$1::jsonb
            WHERE album_id=$2
            RETURNING *
            """,
            json.dumps(current_photos),
            album_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to add photo to album")
    
    album_dict = dict(row)
    # Convert the JSON string to a list of PhotoItem objects
    if album_dict.get("photos"):
        if isinstance(album_dict["photos"], str):
            photos_data = json.loads(album_dict["photos"])
        else:
            photos_data = album_dict["photos"]
            
        album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data]
    else:
        album_dict["photos"] = []
    
    return Album(**album_dict)


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
    
    # Convert the JSON string to a list of PhotoItem objects
    if album_dict.get("photos"):
        if isinstance(album_dict["photos"], str):
            photos_data = json.loads(album_dict["photos"])
        else:
            photos_data = album_dict["photos"]
            
        album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data]
    else:
        album_dict["photos"] = []
    
    return Album(**album_dict)

@router.delete("/{album_id}/photos/{photo_id}", response_model=Album)
async def delete_photo_from_album(
    album_id: str,
    photo_id: str,
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    """Delete a photo from an album."""
    # Get the existing album
    existing = await db.fetchrow("SELECT * FROM albums WHERE album_id=$1", album_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Only the owner can delete photos
    if existing["user_id"] != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to delete photos from this album")
    
    # Get current photos
    current_photos = []
    if existing.get("photos"):
        if isinstance(existing["photos"], str):
            current_photos = json.loads(existing["photos"])
        else:
            current_photos = existing["photos"]
    
    # Find and remove the photo
    updated_photos = [photo for photo in current_photos if photo.get("photo_id") != photo_id]
    
    if len(updated_photos) == len(current_photos):
        raise HTTPException(status_code=404, detail="Photo not found in album")
    
    # Update the album
    try:
        row = await db.fetchrow(
            """
            UPDATE albums
            SET photos=$1::jsonb
            WHERE album_id=$2
            RETURNING *
            """,
            json.dumps(updated_photos),
            album_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to delete photo from album")
    
    album_dict = dict(row)
    # Convert the JSON string to a list of PhotoItem objects
    if album_dict.get("photos"):
        if isinstance(album_dict["photos"], str):
            photos_data = json.loads(album_dict["photos"])
        else:
            photos_data = album_dict["photos"]
            
        album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data]
    else:
        album_dict["photos"] = []
    
    return Album(**album_dict)

@router.put("/{album_id}/photos/{photo_id}/nsfw", response_model=Album)
async def update_photo_nsfw_status(
    album_id: str,
    photo_id: str,
    is_nsfw: bool = Body(..., description="Whether the photo is NSFW"),
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    """Update the NSFW status of a photo."""
    # Get the existing album
    existing = await db.fetchrow("SELECT * FROM albums WHERE album_id=$1", album_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Only the owner can update photos
    if existing["user_id"] != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to update photos in this album")
    
    # Get current photos
    current_photos = []
    if existing.get("photos"):
        if isinstance(existing["photos"], str):
            current_photos = json.loads(existing["photos"])
        else:
            current_photos = existing["photos"]
    
    # Find and update the photo
    updated = False
    for photo in current_photos:
        if photo.get("photo_id") == photo_id:
            photo["is_nsfw"] = is_nsfw
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=404, detail="Photo not found in album")
    
    # Update the album
    try:
        row = await db.fetchrow(
            """
            UPDATE albums
            SET photos=$1::jsonb
            WHERE album_id=$2
            RETURNING *
            """,
            json.dumps(current_photos),
            album_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to update photo NSFW status")
    
    album_dict = dict(row)
    # Convert the JSON string to a list of PhotoItem objects
    if album_dict.get("photos"):
        if isinstance(album_dict["photos"], str):
            photos_data = json.loads(album_dict["photos"])
        else:
            photos_data = album_dict["photos"]
            
        album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data]
    else:
        album_dict["photos"] = []
    
    return Album(**album_dict)


@router.get("/", response_model=List[Album])
async def list_albums(
    db: asyncpg.Connection = Depends(get_db),
    auth_verified: bool = Depends(verify_rocketchat_auth)  # Optionally verify auth
):
    # Return only public albums for now.
    rows = await db.fetch("SELECT * FROM albums WHERE permission = 'public'")
    
    albums = []
    for row in rows:
        album_dict = dict(row)
        
        # Convert the JSON string to a list of PhotoItem objects
        if album_dict.get("photos"):
            if isinstance(album_dict["photos"], str):
                photos_data = json.loads(album_dict["photos"])
            else:
                photos_data = album_dict["photos"]
                
            album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data]
        else:
            album_dict["photos"] = []
        
        albums.append(Album(**album_dict))
    
    return albums


@router.get("/myalbums", response_model=List[Album])
async def list_myalbums(
    db: asyncpg.Connection = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    # Ensure the user has a profile album
    await ensure_profile_album_exists(current_user, db)
    
    # Return albums visible to the current user:
    rows = await db.fetch("""
        SELECT * FROM albums
        WHERE permission = 'public'
           OR user_id = $1
           OR (permission = 'restricted' AND $1 = ANY(allowed_users))
    """, current_user)
    
    albums = []
    for row in rows:
        album_dict = dict(row)
        
        # Convert the JSON string to a list of PhotoItem objects
        if album_dict.get("photos"):
            if isinstance(album_dict["photos"], str):
                photos_data = json.loads(album_dict["photos"])
            else:
                photos_data = album_dict["photos"]
                
            album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data]
        else:
            album_dict["photos"] = []
        
        albums.append(Album(**album_dict))
    
    return albums


@router.get("/user/{user_id}/profile", response_model=Album)
async def get_user_profile_album(
    user_id: str,
    db: asyncpg.Connection = Depends(get_db),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    """Get a user's profile album."""
    # Get the user's profile album
    album = await db.fetchrow("""
        SELECT * FROM albums 
        WHERE user_id = $1 
        AND is_profile_album = TRUE
        AND permission = 'public'
    """, user_id)
    
    if not album:
        raise HTTPException(status_code=404, detail="User profile album not found or not public")
    
    album_dict = dict(album)
    
    # Convert the JSON string to a list of PhotoItem objects
    if album_dict.get("photos"):
        if isinstance(album_dict["photos"], str):
            photos_data = json.loads(album_dict["photos"])
        else:
            photos_data = album_dict["photos"]
            
        # Filter out NSFW photos from other users' profile albums
        album_dict["photos"] = [PhotoItem(**photo) for photo in photos_data if not photo.get("is_nsfw", False)]
    else:
        album_dict["photos"] = []
    
    return Album(**album_dict)

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