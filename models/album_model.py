from pydantic import BaseModel
from typing import List, Optional

class Album(BaseModel):
    album_id: Optional[str] = None   # Generated on creation
    user_id: str                     # Owner of the album
    title: str
    description: Optional[str] = None
    images: List[str]                # List of image URLs or base64 strings
    permission: str = "private"      # e.g. "public", "private", or "restricted"
    allowed_users: Optional[List[str]] = None  # Only used when permission == "restricted"

    # Optionally, add validation to ensure permission is one of the expected values.
    @classmethod
    def validate_permission(cls, v: str) -> str:
        allowed = {"public", "private", "restricted"}
        if v not in allowed:
            raise ValueError(f"permission must be one of {allowed}")
        return v