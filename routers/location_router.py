# routers/location_router.py
from fastapi import APIRouter, HTTPException, Depends
from geopy.distance import geodesic
import asyncpg
from typing import Dict, Any, List

# Import from modules
from dependencies import get_db, verify_api_key, verify_rocketchat_auth
from encryption import encrypt_location, decrypt_location
from models.location_models import (
    UserLocation, 
    NearestUsersRequest,
    NearestByCoordinatesRequest
)

# Create an APIRouter instance
router = APIRouter()

@router.post("/update_location")
async def update_location(
    location: UserLocation,
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    """Update a user's location with encryption."""
    encrypted_data = encrypt_location(location.latitude, location.longitude)
    
    await db.execute('''
        INSERT INTO user_locations (user_id, encrypted_data, visibility, timestamp)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) 
        DO UPDATE SET encrypted_data = $2, visibility = $3, timestamp = CURRENT_TIMESTAMP
    ''', location.user_id, encrypted_data, location.visibility)
    
    return {
        "status": "success",
        "message": "Location updated",
        "data": {}
    }

@router.post("/nearby_by_coordinates")
async def find_nearest_users_by_coords(
    req: NearestByCoordinatesRequest,
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    """Find nearest users based on provided coordinates."""
    if req.limit < 1 or req.limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
    
    other_locations = await db.fetch('''
        SELECT user_id, encrypted_data, visibility FROM user_locations 
        WHERE visibility != 'private'
          AND timestamp > NOW() - INTERVAL '48 hours'
    ''')
    
    reference_point = (req.latitude, req.longitude)
    nearest_users = []
    
    for loc in other_locations:
        try:
            lat, lon = decrypt_location(loc['encrypted_data'])
            distance = geodesic(reference_point, (lat, lon)).kilometers
            
            if req.max_distance_km and distance > req.max_distance_km:
                continue
                
            nearest_users.append({
                "user_id": loc['user_id'],
                "distance_km": round(distance, 2),
                "visibility": loc['visibility']
            })
        except Exception as e:
            print(f"Error decrypting location for user {loc['user_id']}: {e}")
            continue
            
    nearest_users.sort(key=lambda x: x['distance_km'])
    
    return {
        "status": "success",
        "data": {
            "user_id": None,
            "nearest_users": nearest_users[:req.limit],
            "total_found": len(nearest_users)
        }
    }

@router.post("/nearby")
async def find_nearest_users(
    req: NearestUsersRequest,
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    """Find nearest users to a specified user."""
    if req.limit < 1 or req.limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
    
    # Get user location with 48-hour recency
    user_location = await db.fetchrow('''
        SELECT encrypted_data FROM user_locations 
        WHERE user_id = $1
          AND timestamp > NOW() - INTERVAL '48 hours'
    ''', req.user_id)
    
    # If no recent location, try with 7-day recency
    time_window = "48 hours"
    if not user_location:
        user_location = await db.fetchrow('''
            SELECT encrypted_data FROM user_locations 
            WHERE user_id = $1
              AND timestamp > NOW() - INTERVAL '7 days'
        ''', req.user_id)
        if not user_location:
            raise HTTPException(status_code=404, detail="User location not found or is older than 7 days")
        time_window = "7 days"
    
    other_locations = await db.fetch('''
        SELECT user_id, encrypted_data, visibility FROM user_locations 
        WHERE user_id != $1 
            AND visibility != 'private'
            AND timestamp > NOW() - INTERVAL '48 hours'
    ''', req.user_id)
    
    # If no recent locations, try with 7-day recency
    if not other_locations:
        other_locations = await db.fetch('''
            SELECT user_id, encrypted_data, visibility FROM user_locations 
            WHERE user_id != $1 
                AND visibility != 'private'
                AND timestamp > NOW() - INTERVAL '7 days'
        ''', req.user_id)
    
    # Decrypt and calculate distances
    user_lat, user_lon = decrypt_location(user_location['encrypted_data'])
    user_point = (user_lat, user_lon)
    
    nearest_users = []
    for loc in other_locations:
        lat, lon = decrypt_location(loc['encrypted_data'])
        distance = geodesic(user_point, (lat, lon)).kilometers
        
        if req.max_distance_km and distance > req.max_distance_km:
            continue
            
        nearest_users.append({
            "user_id": loc['user_id'],
            "distance_km": round(distance, 2),
            "visibility": loc['visibility']
        })
    
    nearest_users.sort(key=lambda x: x['distance_km'])
    
    return {
        "status": "success",
        "message": f"Using locations from the last {time_window}",
        "data": {
            "user_id": req.user_id,
            "nearest_users": nearest_users[:req.limit],
            "total_found": len(nearest_users),
            "time_window": time_window
        }
    }