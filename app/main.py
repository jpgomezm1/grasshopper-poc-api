"""FastAPI application entry point."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.database import engine, Base
from app.api.v1 import sessions, profile, journal, routes, snapshots, advisor, auth, transcription, english_test, vocational_tests, ofertas, lead_profile, schools

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="Grasshopper POC API",
    description="Backend API for the Grasshopper journey experience",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(journal.router, prefix="/api/v1")
app.include_router(routes.router, prefix="/api/v1")
app.include_router(snapshots.router, prefix="/api/v1")
app.include_router(advisor.router, prefix="/api/v1")
app.include_router(transcription.router, prefix="/api/v1")
app.include_router(english_test.router, prefix="/api/v1")
app.include_router(vocational_tests.router, prefix="/api/v1")
app.include_router(ofertas.router, prefix="/api/v1")
app.include_router(lead_profile.router, prefix="/api/v1")
app.include_router(schools.router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info("Starting Grasshopper POC API...")
    logger.info(f"Environment: {settings.environment}")

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.environment,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Grasshopper POC API",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
