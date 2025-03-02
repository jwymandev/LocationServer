from pydantic import BaseModel, validator
from typing import Optional, Dict, Any, List
from datetime import date

class APIResponse(BaseModel):
    status: str
    data: Optional[Any] = None
    message: Optional[str] = None