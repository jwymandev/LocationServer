from pydantic import BaseModel

class InterestConfig(BaseModel):
    category: str
    interest: str
    active: bool