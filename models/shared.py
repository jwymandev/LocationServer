from pydantic import BaseModel, Field
from typing import Generic, Optional, TypeVar, Dict, Any, List, Union
from datetime import datetime

T = TypeVar('T')

class APIResponse(BaseModel, Generic[T]):
    """Legacy response format for backward compatibility"""
    status: str
    data: Optional[T] = None
    message: Optional[str] = None

class StandardResponse(BaseModel, Generic[T]):
    """Standard response format with consistent fields"""
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None
    error_code: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    meta: Optional[Dict[str, Any]] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class PaginatedResponse(StandardResponse, Generic[T]):
    """Response format for paginated results"""
    items: List[T] = []
    total: int = 0
    page: int = 1
    per_page: int = 20
    total_pages: int = 0

class ErrorDetail(BaseModel):
    """Detailed error information for validation errors"""
    loc: List[Union[str, int]]
    msg: str
    type: str

class ErrorResponse(StandardResponse):
    """Standard error response format"""
    success: bool = False
    detail: Optional[Union[str, List[ErrorDetail]]] = None
    error_type: Optional[str] = None