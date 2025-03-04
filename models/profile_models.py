from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import date
import json

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

    @validator('interests', pre=True)
    def parse_interests(cls, v):
        # If interests is a string that looks like a JSON array, parse it.
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                # If parsing fails, let it error out.
                print("Error Parsing Interests")
                return
        return v

class CoreProfile(BaseModel):
    user_id: str
    username: str
    name: str
    avatar: Optional[str] = None

class CombinedProfile(BaseModel):
    coreProfile: CoreProfile
    extendedProfile: ExtendedProfile