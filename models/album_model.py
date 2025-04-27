from pydantic import BaseModel, validator
from typing import List, Optional, Dict, Any

class PhotoItem(BaseModel):
    photo_id: str                   # Unique ID for the photo
    url: str                         # URL or base64 string of the image
    is_nsfw: bool = False            # Flag for Not Safe For Work content
    caption: Optional[str] = None    # Optional caption for the photo
    timestamp: Optional[str] = None  # When the photo was added

class Album(BaseModel):
    album_id: Optional[str] = None   # Generated on creation
    user_id: str                     # Owner of the album
    title: str
    description: Optional[str] = None
    is_profile_album: bool = False   # Whether this is the user's profile album
    photos: List[PhotoItem] = []     # List of photos in the album
    permission: str = "private"      # e.g. "public", "private", or "restricted"
    allowed_users: Optional[List[str]] = None  # Only used when permission == "restricted"

    # Validation to ensure permission is one of the expected values
    @validator('permission')
    def validate_permission(cls, v: str) -> str:
        allowed = {"public", "private", "restricted"}
        if v not in allowed:
            raise ValueError(f"permission must be one of {allowed}")
        return v