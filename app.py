# app.py
import os
import asyncpg
import ssl
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routers.location_router import router as location_router
from routers.profile_router import router as profile_router
from routers.interest_router import router as interest_router
from routers.album_router import router as album_router
from routers.blocked_router import router as blocked_router
from routers.friend_router import router as friend_router
from routers.favorite_router import router as favorite_router
from config import get_db_config, get_ssl_context
from pathlib import Path

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory if it doesn't exist
uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True, mode=0o755)

async def init_db(pool):
    """Initialize database tables if they don't exist."""
    async with pool.acquire() as conn:
        # Create profiles table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            name TEXT NOT NULL,
            avatar TEXT,
            birthday DATE,
            hometown TEXT,
            description TEXT,
            interests JSONB,
            height INTEGER,
            weight INTEGER,
            position TEXT,
            showAge BOOLEAN DEFAULT TRUE,
            showHeight BOOLEAN DEFAULT TRUE,
            showWeight BOOLEAN DEFAULT TRUE,
            showPosition BOOLEAN DEFAULT TRUE
        );
        ''')
        
        # Alter table to add new columns if they don't exist
        # This ensures backward compatibility for existing databases
        try:
            # Add physical stats columns
            await conn.execute('ALTER TABLE profiles ADD COLUMN IF NOT EXISTS height INTEGER;')
            await conn.execute('ALTER TABLE profiles ADD COLUMN IF NOT EXISTS weight INTEGER;')
            await conn.execute('ALTER TABLE profiles ADD COLUMN IF NOT EXISTS position TEXT;')
            
            # Add visibility settings columns with default TRUE
            await conn.execute('ALTER TABLE profiles ADD COLUMN IF NOT EXISTS showAge BOOLEAN DEFAULT TRUE;')
            await conn.execute('ALTER TABLE profiles ADD COLUMN IF NOT EXISTS showHeight BOOLEAN DEFAULT TRUE;')
            await conn.execute('ALTER TABLE profiles ADD COLUMN IF NOT EXISTS showWeight BOOLEAN DEFAULT TRUE;')
            await conn.execute('ALTER TABLE profiles ADD COLUMN IF NOT EXISTS showPosition BOOLEAN DEFAULT TRUE;')
            
            print("Successfully added physical stats and visibility columns to profiles table if they didn't exist.")
        except Exception as e:
            print(f"Error adding columns to profiles table: {str(e)}")
        
        # Create locations table
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS user_locations (
            user_id TEXT PRIMARY KEY,
            encrypted_data BYTEA NOT NULL,
            visibility TEXT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES profiles(user_id) ON DELETE CASCADE,
            CONSTRAINT valid_visibility CHECK (visibility IN ('public', 'hidden', 'private'))
        );
        ''')

        #Create Albums table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS albums (
                album_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                is_profile_album BOOLEAN NOT NULL DEFAULT FALSE,
                photos JSONB,
                permission TEXT NOT NULL DEFAULT 'private',
                allowed_users JSONB,
                FOREIGN KEY (user_id) REFERENCES profiles(user_id) ON DELETE CASCADE,
                CONSTRAINT valid_permission CHECK (permission IN ('public', 'private', 'restricted'))
            );
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS album_access_requests (
                request_id TEXT PRIMARY KEY,
                album_id TEXT NOT NULL,
                requester_id TEXT NOT NULL,
                status TEXT NOT NULL,  -- e.g. "pending", "approved", "rejected"
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (album_id) REFERENCES albums(album_id) ON DELETE CASCADE
            );
        ''')
        
        # Ensure albums table has the is_profile_album column
        try:
            await conn.execute('ALTER TABLE albums ADD COLUMN IF NOT EXISTS is_profile_album BOOLEAN DEFAULT FALSE;')
            print("Successfully added is_profile_album column to albums table if it didn't exist.")
        except Exception as e:
            print(f"Error adding is_profile_album column to albums table: {str(e)}")
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS blocked_users (
                blocker_id TEXT NOT NULL,
                blocked_id TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (blocker_id, blocked_id)
            );
        ''')
        
        # Create friendship request table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS friendship_requests (
                request_id TEXT PRIMARY KEY,
                sender_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE,
                FOREIGN KEY (sender_id) REFERENCES profiles(user_id) ON DELETE CASCADE,
                FOREIGN KEY (receiver_id) REFERENCES profiles(user_id) ON DELETE CASCADE,
                CONSTRAINT valid_status CHECK (status IN ('pending', 'accepted', 'rejected'))
            );
        ''')
        
        # Create friendships table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS friendships (
                friendship_id TEXT PRIMARY KEY,
                user1_id TEXT NOT NULL,
                user2_id TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user1_id) REFERENCES profiles(user_id) ON DELETE CASCADE,
                FOREIGN KEY (user2_id) REFERENCES profiles(user_id) ON DELETE CASCADE,
                CONSTRAINT unique_friendship UNIQUE (user1_id, user2_id)
            );
        ''')
        
        # Create favorites table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_favorites (
                favorite_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                favorite_user_id TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES profiles(user_id) ON DELETE CASCADE,
                FOREIGN KEY (favorite_user_id) REFERENCES profiles(user_id) ON DELETE CASCADE,
                CONSTRAINT unique_favorite UNIQUE (user_id, favorite_user_id)
            );
        ''')
        

@app.on_event("startup")
async def startup():
    # Create a connection pool and store it in app.state
    db_config = get_db_config()
    ssl_context = get_ssl_context()
    app.state.db_pool = await asyncpg.create_pool(**db_config, ssl=ssl_context)
    
    # Initialize database tables
    await init_db(app.state.db_pool)

@app.on_event("shutdown")
async def shutdown():
    await app.state.db_pool.close()

# Include routers with the desired prefixes
app.include_router(location_router, prefix="/api")
app.include_router(profile_router)  # Already prefixed with /api/profile in the router
app.include_router(interest_router, prefix="/api/interests")
app.include_router(album_router, prefix="/api/albums")
app.include_router(blocked_router, prefix="/api/blocked")
app.include_router(friend_router, prefix="/api/friends")
app.include_router(favorite_router, prefix="/api/favorites")

# Mount the uploads directory for static file serving
# This must be done after all router registrations
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")