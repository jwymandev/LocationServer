from pydantic import BaseModel
from typing import Generic, Optional, TypeVar

T = TypeVar('T')

class APIResponse(BaseModel, Generic[T]):
    status: str
    data: Optional[T]
    message: Optional[str]