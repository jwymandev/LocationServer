from enum import Enum
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from geopy.distance import geodesic
from cryptography.fernet import Fernet
import os
from base64 import b64encode, b64decode
import json
from typing import Optional, List
from datetime import datetime
import asyncpg

class VisibilityState(str, Enum):
    PUBLIC = "public"      # Show distance and allow UI to display
    NOT_PUBLIC = "hidden"  # Return distance but UI won't display
    PRIVATE = "private"    # Don't return user in results

class UserLocation(BaseModel):
    user_id: str
    latitude: float
    longitude: float
    visibility: VisibilityState = VisibilityState.PUBLIC

class NearestUsersRequest(BaseModel):
    user_id: str
    limit: int = 10
    max_distance_km: Optional[float] = None

class NearestUserResponse(BaseModel):
    user_id: str
    distance_km: float
    visibility: VisibilityState

app = FastAPI()

# Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY').encode()
fernet = Fernet(ENCRYPTION_KEY)

def encrypt_location(latitude: float, longitude: float) -> str:
    data = f"{latitude},{longitude}".encode()
    return b64encode(fernet.encrypt(data)).decode()

def decrypt_location(encrypted_data: str) -> tuple:
    try:
        decrypted = fernet.decrypt(b64decode(encrypted_data))
        lat, lon = decrypted.decode().split(',')
        return float(lat), float(lon)
    except Exception:
        raise HTTPException(status_code=500, detail="Decryption failed")

async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)

async def init_db():
    conn = await get_db_connection()
    try:
        # Add visibility column if it doesn't exist
        await conn.execute('''
            ALTER TABLE user_locations 
            ADD COLUMN IF NOT EXISTS visibility TEXT 
            DEFAULT 'public' 
            CHECK (visibility IN ('public', 'hidden', 'private'));
        ''')
    finally:
        await conn.close()

@app.post("/api/update_location")
async def update_location(location: UserLocation):
    conn = await get_db_connection()
    try:
        encrypted_data = encrypt_location(location.latitude, location.longitude)
        
        await conn.execute('''
            INSERT INTO user_locations 
            (user_id, encrypted_data, visibility, timestamp)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                encrypted_data = $2,
                visibility = $3,
                timestamp = CURRENT_TIMESTAMP
        ''', location.user_id, encrypted_data, location.visibility)
        
        return {
            "status": "success",
            "message": "Location updated",
            "visibility": location.visibility
        }
    finally:
        await conn.close()

@app.post("/api/find_nearest")
async def find_nearest_users(request: NearestUsersRequest):
    if request.limit < 1 or request.limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
    
    conn = await get_db_connection()
    try:
        # Get requesting user's location
        user_location = await conn.fetchrow('''
            SELECT encrypted_data, timestamp 
            FROM user_locations 
            WHERE user_id = $1
        ''', request.user_id)
        
        if not user_location:
            raise HTTPException(status_code=404, detail="User location not found")
        
        # Get other users' locations (excluding private)
        other_locations = await conn.fetch('''
            SELECT user_id, encrypted_data, visibility 
            FROM user_locations 
            WHERE user_id != $1 
            AND visibility != 'private'
            AND timestamp > CURRENT_TIMESTAMP - INTERVAL '1 hour'
        ''', request.user_id)
        
        # Calculate distances
        user_lat, user_lon = decrypt_location(user_location['encrypted_data'])
        user_point = (user_lat, user_lon)
        
        nearest_users = []
        for loc in other_locations:
            lat, lon = decrypt_location(loc['encrypted_data'])
            distance = geodesic(user_point, (lat, lon)).kilometers
            
            if request.max_distance_km and distance > request.max_distance_km:
                continue
                
            nearest_users.append({
                "user_id": loc['user_id'],
                "distance_km": round(distance, 2),
                "visibility": loc['visibility']
            })
        
        # Sort and limit results
        nearest_users.sort(key=lambda x: x['distance_km'])
        nearest_users = nearest_users[:request.limit]
        
        return {
            "user_id": request.user_id,
            "nearest_users": nearest_users,
            "total_found": len(nearest_users)
        }
    finally:
        await conn.close()

# Required for DigitalOcean Functions
async def main(args):
    # Initialize database if needed
    await init_db()
    
    method = args.get('http-method', '').upper()
    path = args.get('http-path', '')
    
    if method == 'POST' and path == '/update_location':
        body = json.loads(args.get('http-body', '{}'))
        location = UserLocation(**body)
        return await update_location(location)
        
    elif method == 'POST' and path == '/find_nearest':
        body = json.loads(args.get('http-body', '{}'))
        request = NearestUsersRequest(**body)
        return await find_nearest_users(request)
        
    else:
        return {
            "statusCode": 404,
            "body": "Not found"
        }