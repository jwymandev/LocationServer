from fastapi import APIRouter
from typing import List
from models.interest_model import InterestConfig

router = APIRouter()

@router.get("/", response_model=List[InterestConfig])
async def get_interests():
    # For now, we use hardcoded data. Later, you can load from the database or another source.
    interests = [
        InterestConfig(category="kinks", interest="Bondage", active=False),
        InterestConfig(category="kinks", interest="Domination", active=False),
        InterestConfig(category="kinks", interest="Submission", active=False),
        InterestConfig(category="interests", interest="Music", active=True),
        InterestConfig(category="interests", interest="Travel", active=True),
        InterestConfig(category="lifestyle", interest="Adventurous", active=True),
        InterestConfig(category="lifestyle", interest="Open-minded", active=True)
    ]
    return interests