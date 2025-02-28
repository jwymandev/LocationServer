# models/location_models.py
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class VisibilityState(str, Enum):
    PUBLIC = "public"  
    HIDDEN = "hidden"  
    PRIVATE = "private"  

class UserLocation(BaseModel):
    user_id: str
    latitude: float
    longitude: float
    visibility: VisibilityState = VisibilityState.PUBLIC

class NearestUsersRequest(BaseModel):
    user_id: str
    limit: int = 10
    max_distance_km: Optional[float] = None

class NearestByCoordinatesRequest(BaseModel):
    latitude: float
    longitude: float
    limit: int = 10
    max_distance_km: Optional[float] = None

class NearestUserResponse(BaseModel):
    user_id: str
    distance_km: float
    visibility: VisibilityState