import os
import json
import base64
import ssl
import requests
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Header, Depends, status, Request
from pydantic import BaseModel
from geopy.distance import geodesic
import asyncpg
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from os import urandom
from enum import Enum

# Shared configuration: assume these are defined in a central config or imported from one.
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}
ca_cert = os.getenv('DB_CA_CERT')
if not ca_cert:
    raise Exception("Missing required environment variable: DB_CA_CERT")
ssl_context = ssl.create_default_context(cadata=ca_cert)
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise Exception("Missing required environment variable: API_KEY")

# Encryption key setup.
key = os.getenv('ENCRYPTION_KEY')
if not key:
    raise Exception("Missing required environment variable: ENCRYPTION_KEY")
ENCRYPTION_KEY = key.encode()

# Create an APIRouter instance.
router = APIRouter()

# --- Dependencies ---
# This dependency obtains a DB connection from the pool in app.state.db_pool.
async def get_db(request: Request) -> asyncpg.Connection:
    pool = request.app.state.db_pool
    async with pool.acquire() as connection:
        yield connection

def verify_api_key(api_key: str = Header(...)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized API access")
    return api_key

# --- Models ---
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

# --- Encryption Setup ---
def derive_key(secret: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"static_salt",  # Consider making this configurable
        iterations=100000
    )
    return kdf.derive(secret)

AES_KEY = derive_key(ENCRYPTION_KEY)

def encrypt_location(latitude: float, longitude: float) -> str:
    iv = urandom(12)
    cipher = Cipher(algorithms.AES(AES_KEY), modes.GCM(iv))
    encryptor = cipher.encryptor()
    data = json.dumps({"lat": latitude, "lon": longitude}).encode()
    ciphertext = encryptor.update(data) + encryptor.finalize()
    return base64.b64encode(iv + encryptor.tag + ciphertext).decode()

def decrypt_location(encrypted_data: str) -> tuple:
    try:
        raw_data = base64.b64decode(encrypted_data)
        iv, tag, ciphertext = raw_data[:12], raw_data[12:28], raw_data[28:]
        cipher = Cipher(algorithms.AES(AES_KEY), modes.GCM(iv, tag))
        decryptor = cipher.decryptor()
        decrypted_json = decryptor.update(ciphertext) + decryptor.finalize()
        location = json.loads(decrypted_json.decode())
        return location["lat"], location["lon"]
    except Exception:
        raise HTTPException(status_code=500, detail="Decryption failed")

# --- Rocket.Chat Auth ---
ROCKETCHAT_BASE_URL = os.getenv("ROCKETCHAT_BASE_URL")
if not ROCKETCHAT_BASE_URL:
    raise Exception("Missing required environment variable: ROCKETCHAT_BASE_URL")
ME_ENDPOINT = "/api/v1/me"

async def verify_rocketchat_auth(request: Request):
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

# --- Endpoints using async dependency ---
@router.post("/update_location")
async def update_location(
    location: UserLocation,
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
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
        "user_id": None,
        "nearest_users": nearest_users[:req.limit],
        "total_found": len(nearest_users)
    }

@router.post("/nearby")
async def find_nearest_users(
    req: NearestUsersRequest,
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    if req.limit < 1 or req.limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
    
    user_location = await db.fetchrow('''
        SELECT encrypted_data FROM user_locations 
        WHERE user_id = $1
          AND timestamp > NOW() - INTERVAL '48 hours'
    ''', req.user_id)
    
    if not user_location:
        user_location = await db.fetchrow('''
            SELECT encrypted_data FROM user_locations 
            WHERE user_id = $1
              AND timestamp > NOW() - INTERVAL '7 days'
        ''', req.user_id)
        if not user_location:
            raise HTTPException(status_code=404, detail="User location not found or is older than 7 days")
    
    other_locations = await db.fetch('''
        SELECT user_id, encrypted_data, visibility FROM user_locations 
        WHERE user_id != $1 
            AND visibility != 'private'
            AND timestamp > NOW() - INTERVAL '48 hours'
    ''', req.user_id)
    
    if not other_locations:
        other_locations = await db.fetch('''
            SELECT user_id, encrypted_data, visibility FROM user_locations 
            WHERE user_id != $1 
                AND visibility != 'private'
                AND timestamp > NOW() - INTERVAL '7 days'
        ''', req.user_id)
    
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
    time_window = "7 days" if not await db.fetchrow('''
        SELECT 1 FROM user_locations 
        WHERE user_id = $1
          AND timestamp > NOW() - INTERVAL '48 hours'
    ''', req.user_id) else "48 hours"
    
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