# app.py
import os
import asyncpg
import ssl
from fastapi import FastAPI
from routers.location_router import router as location_router
from routers.profile_router import router as profile_router
from routers.interest_router import router as interest_router
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
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            visibility TEXT NOT NULL,
            last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
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
                images JSONB,
                public BOOLEAN NOT NULL DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES profiles(user_id) ON DELETE CASCADE
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