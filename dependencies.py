# dependencies.py
import requests
import asyncpg
from fastapi import Request, HTTPException, Header, status
from config import get_api_key, get_rocketchat_base_url

API_KEY = get_api_key()
ROCKETCHAT_BASE_URL = get_rocketchat_base_url()
ME_ENDPOINT = "/api/v1/me"

async def get_db(request: Request) -> asyncpg.Connection:
    """Get database connection from connection pool."""
    pool = request.app.state.db_pool
    async with pool.acquire() as connection:
        yield connection

def verify_api_key(api_key: str = Header(...)):
    """Verify API key from request header."""
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized API access")
    return api_key

async def verify_rocketchat_auth(request: Request):
    """Verify Rocket.Chat authentication."""
    auth_token = request.headers.get("X-Auth-Token")
    auth_id = request.headers.get("X-User-Id")
    
    if not auth_token or not auth_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication headers"
        )
        
    headers = {"X-Auth-Token": auth_token, "X-User-Id": auth_id}
    
    try:
        response = requests.get(f"{ROCKETCHAT_BASE_URL}{ME_ENDPOINT}", headers=headers, timeout=3)
    except requests.RequestException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify credentials at this time"
        )
        
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
        
    return True

async def get_current_user_id(request: Request):
    """Get current user ID from the X-User-Id header."""
    user_id = request.headers.get("X-User-Id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header"
        )
        
    # We can add additional validation here if needed
    
    return user_id

async def get_profile_by_id(user_id: str, pool):
    """Get a user profile by ID."""
    async with pool.acquire() as conn:
        profile = await conn.fetchrow('''
            SELECT * FROM profiles WHERE user_id = $1
        ''', user_id)
        
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile for user {user_id} not found"
            )
        
        return dict(profile)