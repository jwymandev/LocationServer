from pydantic import BaseModel, validator
from typing import Optional, Dict, Any, List
from datetime import date

class ExtendedProfile(BaseModel):
    birthday: Optional[date] = None
    hometown: Optional[str] = None
    description: Optional[str] = None
    interests: Optional[List[str]] = None
    
    @validator('birthday', pre=True)
    def parse_birthday(cls, v):
        if isinstance(v, date):
            return v.isoformat()
        return v

class CoreProfile(BaseModel):
    user_id: str
    username: str
    name: str
    avatar: Optional[str] = None

class CombinedProfile(BaseModel):
    coreProfile: CoreProfile
    extendedProfile: ExtendedProfile