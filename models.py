from pydantic import BaseModel
from typing import Any, Optional, Generic, TypeVar
from pydantic.generics import GenericModel

DataT = TypeVar("DataT")

class APIResponseModel(GenericModel, Generic[DataT]):
    status: str
    message: Optional[str] = ""
    data: Optional[DataT] = None

# For endpoints that don't return any data, you can define an EmptyData model.
class EmptyData(BaseModel):
    pass