from fastapi import FastAPI
from profile_router import router as profile_router
from location_router import router as location_router
from your_db_module import lifespan  # Your lifespan function that sets up the db pool

app = FastAPI(lifespan=lifespan)

# Include routers with prefixes.
app.include_router(profile_router, prefix="/api")
app.include_router(location_router, prefic="/api")