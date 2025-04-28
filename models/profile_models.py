from pydantic import BaseModel, validator, Field
from typing import Optional, List, Dict, Any, Union
from datetime import date, datetime
import json
from enum import Enum

class ProfileSource(str, Enum):
    ROCKET_CHAT = "rocket_chat"
    CUSTOM = "custom"
    COMBINED = "combined"

class ExtendedProfile(BaseModel):
    birthday: Optional[str] = None  # ISO format date string
    hometown: Optional[str] = None
    description: Optional[str] = None
    interests: Optional[List[str]] = []
    # Physical stats
    height: Optional[int] = None
    weight: Optional[int] = None
    position: Optional[str] = None
    # Visibility settings
    showAge: Optional[bool] = True
    showHeight: Optional[bool] = True
    showWeight: Optional[bool] = True
    showPosition: Optional[bool] = True
    
    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat()
        }
    
    @validator('birthday', pre=True)
    def parse_birthday(cls, v):
        if v is None:
            return None
            
        if isinstance(v, (date, datetime)):
            return v.isoformat()
            
        # Handle string date formats
        if isinstance(v, str):
            # Already in ISO format, return as is
            return v
            
        return v
    
    @validator('interests', pre=True)
    def parse_interests(cls, v):
        # If None, return empty list
        if v is None:
            return []
            
        # If interests is a string that looks like a JSON array, parse it
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
                else:
                    return []
            except json.JSONDecodeError:
                # Log the error and return empty list
                print(f"Error parsing interests: {v}")
                return []
                
        # If it's already a list, return it
        if isinstance(v, list):
            return v
            
        # Default case, return empty list
        return []

class CoreProfile(BaseModel):
    user_id: str
    username: str
    name: str
    avatar: Optional[str] = None
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("user_id must be a non-empty string")
        return v

class ProfileResponseBase(BaseModel):
    success: bool = True
    message: Optional[str] = None
    source: ProfileSource = ProfileSource.CUSTOM
    error_code: Optional[int] = None

class CombinedProfile(BaseModel):
    coreProfile: CoreProfile
    extendedProfile: Optional[ExtendedProfile] = Field(default_factory=ExtendedProfile)
    profileAlbumId: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "coreProfile": {
                    "user_id": "user123",
                    "username": "johndoe",
                    "name": "John Doe",
                    "avatar": "https://example.com/avatar.jpg"
                },
                "extendedProfile": {
                    "birthday": "1990-01-01",
                    "hometown": "New York",
                    "description": "Software engineer and outdoor enthusiast",
                    "interests": ["hiking", "coding", "photography"],
                    "height": 180,
                    "weight": 75,
                    "position": "Versatile"
                },
                "profileAlbumId": "album123"
            }
        }

class ProfileResponse(ProfileResponseBase):
    profile: Optional[Union[CoreProfile, ExtendedProfile, CombinedProfile]] = None

class ProfileListResponse(ProfileResponseBase):
    profiles: List[CombinedProfile] = []
    total: int = 0
    page: int = 1
    per_page: int = 20