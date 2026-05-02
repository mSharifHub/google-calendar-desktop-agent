"""
FastAPI entry point.

All route logic lives in the routers package:
  - routers/models.py    → /configure, /chat, /sessions, /backends, /ollama
  - routers/calendars.py → /calendars/*, /auth/*/connect|callback|disconnect
  - routers/user.py      → /user
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.calendars import router as calendars_router
from routers.models import router as models_router
from routers.user import router as user_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


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
