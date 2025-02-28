# models/profile_models.py
from pydantic import BaseModel
from typing import List, Optional

class CoreProfile(BaseModel):
    user_id: str
    username: str
    name: str
    avatar: Optional[str] = None   # Base64 or text representation

class ExtendedProfile(BaseModel):
    birthday: str                 # Format "yyyy-mm-dd"
    hometown: Optional[str] = None
    description: Optional[str] = None
    interests: Optional[List[str]] = None

class CombinedProfile(BaseModel):
    coreProfile: CoreProfile
    extendedProfile: ExtendedProfile