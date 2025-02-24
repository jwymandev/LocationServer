import os
import json
import base64
import ssl
from typing import Optional, List
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Depends, status
import requests
from pydantic import BaseModel
from geopy.distance import geodesic
from contextlib import asynccontextmanager
import asyncpg
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from os import urandom
from enum import Enum

# Load API key and DB config from environment variables
API_KEY = os.getenv("API_KEY")
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 5432)),  # Default PostgreSQL port
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

ca_cert_content = os.getenv('DB_CA_CERT')
if not ca_cert_content:
    raise Exception("Missing required environment variable: DB_CA_CERT_CONTENT")

ssl_context = ssl.create_default_context(cadata=ca_cert_content)
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

key = os.getenv('ENCRYPTION_KEY')
if not key:
    raise Exception("Missing required environment variable: ENCRYPTION_KEY")
ENCRYPTION_KEY = key.encode()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code: for example, initialize your database
    await init_db()
    yield
    
app = FastAPI(lifespan=lifespan)

# API Key verification dependency
def verify_api_key(api_key: str = Header(...)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized API access")
    return api_key

# Visibility Enum and Models
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

class NearestUserResponse(BaseModel):
    user_id: str
    distance_km: float
    visibility: VisibilityState

# Key derivation for AES-GCM
def derive_key(secret: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"static_salt",  # Consider making this configurable
        iterations=100000
    )
    return kdf.derive(secret)

AES_KEY = derive_key(ENCRYPTION_KEY)

# Encryption
def encrypt_location(latitude: float, longitude: float) -> str:
    iv = urandom(12)
    cipher = Cipher(algorithms.AES(AES_KEY), modes.GCM(iv))
    encryptor = cipher.encryptor()
    data = json.dumps({"lat": latitude, "lon": longitude}).encode()
    ciphertext = encryptor.update(data) + encryptor.finalize()
    return base64.b64encode(iv + encryptor.tag + ciphertext).decode()

# Decryption
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

# Database connection functions
async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG, ssl=ssl_context)

async def init_db():
    conn = await get_db_connection()
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_locations (
                user_id TEXT PRIMARY KEY,
                encrypted_data TEXT NOT NULL,
                visibility TEXT NOT NULL CHECK (visibility IN ('public', 'hidden', 'private')),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
    finally:
        await conn.close()

ROCKETCHAT_BASE_URL = "https://chatdev.cuffd.io"
ME_ENDPOINT = "/api/v1/me"

async def verify_rocketchat_auth(request: Request):
    # Extract required headers from the incoming request.
    auth_token = request.headers.get("X-Auth-Token")
    auth_id = request.headers.get("X-User-Id")  # Adjust header name if needed.
    if not auth_token or not auth_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing authentication headers")
    
    # Verify credentials against Rocket.Chat.
    headers = {
        "X-Auth-Token": auth_token,
        "X-User-Id": auth_id
    }
    
    try:
        response = requests.get(f"{ROCKETCHAT_BASE_URL}{ME_ENDPOINT}", headers=headers, timeout=3)
    except requests.RequestException:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Unable to verify credentials at this time")
    
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid authentication credentials")
    
    # Optionally, return some info from Rocket.Chat's response.
    return True

# Endpoints
@app.post("/api/update_location")
async def update_location(
    location: UserLocation,
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    conn = await get_db_connection()
    try:
        encrypted_data = encrypt_location(location.latitude, location.longitude)
        await conn.execute('''
            INSERT INTO user_locations (user_id, encrypted_data, visibility, timestamp)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) 
            DO UPDATE SET encrypted_data = $2, visibility = $3, timestamp = CURRENT_TIMESTAMP
        ''', location.user_id, encrypted_data, location.visibility)
        return {"status": "success", "message": "Location updated", "visibility": location.visibility}
    finally:
        await conn.close()

@app.post("/api/nearby")
async def find_nearest_users(
    location: UserLocation,
    api_key: str = Depends(verify_api_key),
    auth_verified: bool = Depends(verify_rocketchat_auth)
):
    if request.limit < 1 or request.limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")

    conn = await get_db_connection()
    try:
        user_location = await conn.fetchrow('''
            SELECT encrypted_data FROM user_locations 
            WHERE user_id = $1
              AND timestamp > NOW() - INTERVAL '48 hours'  
        ''', request.user_id)
        if not user_location:
            raise HTTPException(status_code=404, detail="User location not found or is older than 48 hours")
        
        if not user_location:
            raise HTTPException(status_code=404, detail="User location not found")

        other_locations = await conn.fetch('''
            SELECT user_id, encrypted_data, visibility FROM user_locations 
            WHERE user_id != $1 
                AND visibility != 'private'
                AND timestamp > NOW() - INTERVAL '48 hours'                           
        ''', request.user_id)

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

        nearest_users.sort(key=lambda x: x['distance_km'])
        return {
            "user_id": request.user_id,
            "nearest_users": nearest_users[:request.limit],
            "total_found": len(nearest_users)
        }
    finally:
        await conn.close()

