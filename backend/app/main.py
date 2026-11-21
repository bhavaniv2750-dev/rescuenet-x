from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.core.config import settings
from app.db.init_db import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and ensure seeded data
    try:
        init_db()
    except Exception as e:
        print(f"[Startup] Warning during init_db: {e}")
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "AI-Powered Autonomous Disaster Intelligence & Emergency Response System. "
        "Predict -> Visualize -> Respond. Built with real datasets from IndoFloods & RescueNet SOS."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS: Allow local Vite dev servers on port 5173, 5174, etc.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):(517[0-9]|3000)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": "2.0.0",
        "status": "operational",
        "docs_url": "/docs",
        "api_v1": settings.API_V1_STR,
    }
