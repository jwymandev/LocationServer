# app.py
import os
import asyncpg
import ssl
from fastapi import FastAPI
from routers.location_router import router as location_router
from routers.profile_router import router as profile_router
from config import get_db_config, get_ssl_context

app = FastAPI()

@app.on_event("startup")
async def startup():
    # Create a connection pool and store it in app.state
    db_config = get_db_config()
    ssl_context = get_ssl_context()
    app.state.db_pool = await asyncpg.create_pool(**db_config, ssl=ssl_context)

@app.on_event("shutdown")
async def shutdown():
    await app.state.db_pool.close()

# Include routers with the desired prefixes
app.include_router(location_router, prefix="/api")
app.include_router(profile_router, prefix="/api/profile")