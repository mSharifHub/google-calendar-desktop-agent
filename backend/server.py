import asyncio
import subprocess
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional

import requests as http_requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

OLLAMA_BASE = "http://localhost:11434"


def _ollama_model_exists(model_name: str) -> bool:
    """Return True if the model is already pulled in Ollama."""
    try:
        res = http_requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        models = res.json().get("models", [])
        local_names = {m["name"] for m in models}
        # Ollama stores names as "name:tag"; normalise by adding :latest if no tag
        needle = model_name if ":" in model_name else f"{model_name}:latest"
        return needle in local_names
    except Exception:
        return False


class Backend(str, Enum):
    local = "local"
    claude = "claude"
    openai = "openai"
    gemini = "gemini"

# Session store: session_id -> {"agent": ..., "config": ..., "model_info": ...}
_sessions: dict[str, dict] = {}


def _build_model(backend: Backend, api_key: str = "", model_name: str = ""):
    if backend != Backend.local and not api_key:
        raise ValueError(f"An API key is required for the '{backend.value}' backend.")

    if backend == Backend.local:
        if not model_name:
            raise ValueError("A model name is required for the local backend.")
        if not _ollama_model_exists(model_name):
            raise ValueError(f"MODEL_NOT_FOUND:{model_name}")
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model_name, temperature=0)
    elif backend == Backend.claude:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_name or "claude-sonnet-4-6", api_key=api_key, temperature=0)
    elif backend == Backend.openai:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name or "gpt-4o", api_key=api_key, temperature=0)
    elif backend == Backend.gemini:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_name or "gemini-2.0-flash", google_api_key=api_key, temperature=0)


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


# ---------- Request models ----------

class ConfigureRequest(BaseModel):
    backend: Backend
    api_key: Optional[str] = ""
    model_name: Optional[str] = ""


class ChatRequest(BaseModel):
    message: str
    session_id: str


# Cache user info so we don't call Google on every request
_user_info: dict = {}


# ---------- Endpoints ----------

@app.get("/user")
def user():
    global _user_info
    if not _user_info:
        try:
            from auth.google_auth import get_user_info
            _user_info = get_user_info()
        except Exception as e:
            print(f"[/user] Could not fetch user info: {e}")
            return {"name": "", "given_name": "", "email": "", "picture": ""}
    return {
        "name":       _user_info.get("name", ""),
        "given_name": _user_info.get("given_name", ""),
        "email":      _user_info.get("email", ""),
        "picture":    _user_info.get("picture", ""),
    }


class PullRequest(BaseModel):
    model: str


@app.post("/ollama/pull")
async def ollama_pull(req: PullRequest):
    """Pull an Ollama model. Blocks until the download completes."""
    def do_pull():
        result = subprocess.run(
            ["ollama", "pull", req.model],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or f"Failed to pull {req.model}")

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, do_pull)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok", "model": req.model}


@app.get("/sessions")
def list_sessions():
    return {
        "sessions": {
            sid: s["model_info"] for sid, s in _sessions.items()
        }
    }


@app.get("/status")
def status(session_id: Optional[str] = Query(default=None)):
    if session_id:
        session = _sessions.get(session_id)
        return {
            "configured": session is not None,
            "model_info": session["model_info"] if session else {},
        }
    return {"configured": len(_sessions) > 0, "model_info": {}}


@app.post("/configure")
def configure(req: ConfigureRequest):
    try:
        model = _build_model(req.backend, req.api_key or "", req.model_name or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    from agent.agent import build_agent
    agent, config = build_agent(model)

    defaults = {
        Backend.local: "llama3.1:latest",
        Backend.claude: "claude-sonnet-4-6",
        Backend.openai: "gpt-4o",
        Backend.gemini: "gemini-2.0-flash",
    }
    model_info = {
        "backend": req.backend.value,
        "model_name": req.model_name or defaults[req.backend],
    }

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"agent": agent, "config": config, "model_info": model_info}

    return {"status": "ok", "session_id": session_id, "model_info": model_info}


@app.post("/chat")
async def chat(req: ChatRequest):
    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=400, detail="Session not found. Call /configure first.")

    agent = session["agent"]
    config = session["config"]

    async def generate():
        loop = asyncio.get_event_loop()

        def run_stream():
            result = ""
            for chunk in agent.stream(
                {"messages": [HumanMessage(content=req.message)]},
                config=config,
                stream_mode="values",
            ):
                last = chunk["messages"][-1]
                if last.content and isinstance(last, AIMessage):
                    result = last.content
            return result

        response = await loop.run_in_executor(None, run_stream)
        yield response

    return StreamingResponse(generate(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
