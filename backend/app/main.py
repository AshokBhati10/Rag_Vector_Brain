from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db.init_db import init_db
from app.db.session import engine
from app.routers import chat as chat_router
from app.routers import upload
from app.routers import documents as documents_router
from app.routers import notebooks as notebooks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run init_db on startup to ensure schema exists."""
    init_db()
    yield


app = FastAPI(title="Vector Brain API", lifespan=lifespan)

# CORS — allow Vite dev server on both common ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(upload.router, prefix="/api")
app.include_router(chat_router.router, prefix="/api")
app.include_router(documents_router.router, prefix="/api")
app.include_router(notebooks_router.router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    """Run SELECT 1 to verify the database connection is alive."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"database": "connected"}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"database": str(e)})
