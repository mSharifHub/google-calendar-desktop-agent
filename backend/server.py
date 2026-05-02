"""
FastAPI entry point.

All route logic lives in the routers package:
  - routers/models.py    → /configure, /chat, /sessions, /backends, /ollama
  - routers/calendars.py → /calendars/*, /auth/*/connect|callback|disconnect
  - routers/user.py      → /user
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Logging configuration ──────────────────────────────────────────────────────
# Set level=logging.DEBUG during development; switch to INFO for production.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient.discovery").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

from routers.calendars import router as calendars_router
from routers.models import router as models_router
from routers.user import router as user_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Server starting up")
    yield
    logger.info("Server shutting down")


app = FastAPI(title="Calendar Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calendars_router)
app.include_router(models_router)
app.include_router(user_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
