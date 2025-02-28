# main.py
import os
import asyncpg
import ssl
from fastapi import FastAPI
from location_router import router as location_router
from profile_router import router as profile_router

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

# Set up SSL context if needed
ca_cert_content = os.getenv('DB_CA_CERT')
if not ca_cert_content:
    raise Exception("Missing required environment variable: DB_CA_CERT")
ssl_context = ssl.create_default_context(cadata=ca_cert_content)
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

app = FastAPI()

@app.on_event("startup")
async def startup():
    # Create a connection pool and store it in app.state
    app.state.db_pool = await asyncpg.create_pool(**DB_CONFIG, ssl=ssl_context)


@app.on_event("shutdown")
async def shutdown():
    await app.state.db_pool.close()

# Include routers with the desired prefixes.
# In this example, location endpoints will be available under /api and profile endpoints under /api/profile.
app.include_router(location_router, prefix="/api")
app.include_router(profile_router, prefix="/api/profile")