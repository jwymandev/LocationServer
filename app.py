# app.py
import os
import asyncpg
import ssl
from fastapi import FastAPI
from routers.location_router import router as location_router
from routers.profile_router import router as profile_router
from routers.interest_router import router as interest_router
from routers.album_router import router as album_router
from routers.blocked_router import router as blocked_router
from routers.friend_router import router as friend_router
from config import get_db_config, get_ssl_context

app = FastAPI()

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
            interests JSONB
        );
        ''')
        
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
app.include_router(profile_router, prefix="/api/profile")
app.include_router(interest_router, prefix="/api/interests")
app.include_router(album_router, prefix="/api/albums")
app.include_router(blocked_router, prefix="/api/blocked")
app.include_router(friend_router, prefix="/api/friends")