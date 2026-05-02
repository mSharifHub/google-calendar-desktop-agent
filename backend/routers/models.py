import asyncio
import subprocess
import uuid
from enum import Enum
from typing import Optional

import requests as http_requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel

from agent.agent import build_agent


class Backend(str, Enum):
    local = "local"
    claude = "claude"
    openai = "openai"
    gemini = "gemini"


OLLAMA_BASE = "http://localhost:11434"

_DEFAULT_MODEL_NAMES = {
    Backend.local: "llama3.1:latest",
    Backend.claude: "claude-sonnet-4-6",
    Backend.openai: "gpt-4o",
    Backend.gemini: "gemini-2.0-flash",
}

_sessions: dict[str, dict] = {}


# ---------- Request models ----------

class ConfigureRequest(BaseModel):
    backend: Backend
    api_key: Optional[str] = ""
    model_name: Optional[str] = ""

class ChatRequest(BaseModel):
    message: str
    session_id: str

class PullRequest(BaseModel):
    model: str


# ---------- Helpers ----------

def _ollama_model_exists(model_name: str) -> bool:
    try:
        res = http_requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        res.raise_for_status()
        local_names = {m["name"] for m in res.json().get("models", [])}
        if model_name in local_names:
            return True
        needle = model_name if ":" in model_name else f"{model_name}:latest"
        if needle in local_names:
            return True
        base = model_name.split(":")[0]
        return any(n.split(":")[0] == base for n in local_names)
    except http_requests.exceptions.RequestException:
        return False


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


# ---------- Router ----------

router = APIRouter()


@router.get("/backends")
def backends():
    return {"backends": [b.value for b in Backend]}


@router.get("/sessions")
def list_sessions():
    return {"sessions": {sid: s["model_info"] for sid, s in _sessions.items()}}


@router.delete("/sessions/{session_id}")
def close_session(session_id: str):
    if session_id in _sessions:
        del _sessions[session_id]
        return {"status": "ok", "message": "Session closed."}
    raise HTTPException(status_code=404, detail="Session not found.")


@router.get("/sessions/{session_id}/status")
def status(session_id: str):
    session = _sessions.get(session_id)
    return {
        "configured": session is not None,
        "model_info": session["model_info"] if session else {},
    }


@router.post("/configure")
def configure(req: ConfigureRequest):
    try:
        model = _build_model(req.backend, req.api_key or "", req.model_name or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # FIXED: Corrected import path. It's just `agent`, not `agent.agent`.

    agent, config = build_agent(model)

    model_info = {
        "backend": req.backend.value,
        "model_name": req.model_name or _DEFAULT_MODEL_NAMES[req.backend],
    }
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"agent": agent, "config": config, "model_info": model_info}

    return {"status": "ok", "session_id": session_id, "model_info": model_info}


@router.post("/chat")
async def chat(req: ChatRequest):
    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=400, detail="Session not found. Call /configure first.")

    agent = session["agent"]
    config = session["config"]

    def run_stream():
        previous_content = ""
        last_message_id = None

        for chunk in agent.stream(
                {"messages": [HumanMessage(content=req.message)]},
                config=config,
                stream_mode="values",
        ):
            last = chunk["messages"][-1]
            if isinstance(last, AIMessage) and last.content:
                if last.id != last_message_id:
                    previous_content = ""
                    last_message_id = last.id

                new_content = last.content[len(previous_content):]
                if new_content:
                    yield new_content
                    previous_content = last.content

    return StreamingResponse(run_stream(), media_type="text/plain")


@router.post("/ollama/pull")
async def ollama_pull(req: PullRequest):
    def do_pull():
        result = subprocess.run(
            ["ollama", "pull", req.model],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or f"Failed to pull {req.model}")

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, do_pull)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok", "model": req.model}