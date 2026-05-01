import asyncio
import subprocess
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional

import requests as http_requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

OLLAMA_BASE = "http://localhost:11434"


def _ollama_model_exists(model_name: str) -> bool:
    """Return True if the model is already pulled in Ollama."""
    try:
        res = http_requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        models = res.json().get("models", [])
        local_names = {m["name"] for m in models}

        # 1. Exact match
        if model_name in local_names:
            return True
        # 2. Normalise: add :latest if the user omitted the tag
        needle = model_name if ":" in model_name else f"{model_name}:latest"
        if needle in local_names:
            return True
        # 3. Base-name match: "llama3.1" matches "llama3.1:8b-instruct-q4_K_M"
        base = model_name.split(":")[0]
        return any(n.split(":")[0] == base for n in local_names)
    except Exception:
        return False


class Backend(str, Enum):
    local = "local"
    claude = "claude"
    openai = "openai"
    gemini = "gemini"


# Session store: session_id -> {\"agent\": ..., \"config\": ..., \"model_info\": ...}
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


class PullRequest(BaseModel):
    model: str


# ---------- Calendar provider request models ----------

class OutlookSetupRequest(BaseModel):
    client_id: str
    client_secret: str
    tenant_id: Optional[str] = "common"


class AppleConnectRequest(BaseModel):
    username: str
    app_password: str


class CalendlyConnectRequest(BaseModel):
    token: str


# Cache user info so we don't call Google on every request
_user_info: dict = {}


# ---------- Existing endpoints ----------

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


# ---------- Calendar provider endpoints ----------

@app.get("/calendars/status")
def calendars_status():
    """Return which calendar providers are currently connected."""
    try:
        from auth.google_auth import is_connected as google_ok
        google = google_ok()
    except Exception:
        google = False
    try:
        from auth.microsoft_auth import is_connected as outlook_ok
        outlook = outlook_ok()
    except Exception:
        outlook = False
    try:
        from auth.apple_auth import is_connected as apple_ok
        apple = apple_ok()
    except Exception:
        apple = False
    try:
        from auth.calendly_auth import is_connected as calendly_ok
        calendly = calendly_ok()
    except Exception:
        calendly = False

    return {
        "google": google,
        "outlook": outlook,
        "apple": apple,
        "calendly": calendly,
    }


# --- Google Calendar ---

@app.post("/auth/google/connect")
async def google_connect():
    """
    Trigger the Google OAuth2 flow. Opens a browser on the local machine.
    Blocks until the user completes sign-in; returns once token.json is saved.
    """
    def do_connect():
        from auth.google_auth import connect
        connect()

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, do_connect)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok"}


@app.post("/auth/google/disconnect")
def google_disconnect():
    from auth.google_auth import disconnect
    disconnect()
    return {"status": "ok"}


# --- Outlook ---

@app.post("/auth/outlook/setup")
def outlook_setup(req: OutlookSetupRequest):
    """
    Store Azure app credentials and return the OAuth2 authorization URL.
    The frontend should open this URL so the user can grant calendar access.
    """
    try:
        from auth.microsoft_auth import save_app_credentials, get_auth_url
        save_app_credentials(req.client_id, req.client_secret, req.tenant_id or "common")
        auth_url = get_auth_url()
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/auth/outlook/callback")
def outlook_callback(code: Optional[str] = Query(default=None), error: Optional[str] = Query(default=None)):
    """
    Microsoft redirects here after the user grants (or denies) consent.
    Exchanges the authorization code for tokens and returns a close-tab page.
    """
    if error:
        html = f"""
        <html><body style="font-family:sans-serif;text-align:center;padding:60px">
          <h2 style="color:#dc2626">Authentication Failed</h2>
          <p>{error}</p>
          <p>You can close this tab.</p>
        </body></html>
        """
        return HTMLResponse(content=html, status_code=400)

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received.")

    try:
        from auth.microsoft_auth import exchange_code
        exchange_code(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    html = """
    <html><body style="font-family:sans-serif;text-align:center;padding:60px">
      <h2 style="color:#16a34a">&#10003; Outlook Connected!</h2>
      <p>Your Microsoft Calendar has been linked successfully.</p>
      <p style="color:#6b7280">You can close this tab and return to the app.</p>
      <script>
        setTimeout(() => window.close(), 2000);
      </script>
    </body></html>
    """
    return HTMLResponse(content=html)


@app.post("/auth/outlook/disconnect")
def outlook_disconnect():
    from auth.microsoft_auth import disconnect
    disconnect()
    return {"status": "ok"}


# --- Apple Calendar ---

@app.post("/auth/apple/connect")
def apple_connect(req: AppleConnectRequest):
    """
    Store Apple ID and app-specific password, then verify the CalDAV connection.
    Generate an app-specific password at appleid.apple.com → Security → App-Specific Passwords.
    """
    from auth.apple_auth import save_credentials, connect_and_verify, disconnect
    save_credentials(req.username, req.app_password)
    try:
        connect_and_verify()
    except ValueError as e:
        disconnect()  # Remove invalid credentials
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        disconnect()
        raise HTTPException(status_code=400, detail=f"Unexpected error: {e}")
    return {"status": "ok"}


@app.post("/auth/apple/disconnect")
def apple_disconnect():
    from auth.apple_auth import disconnect
    disconnect()
    return {"status": "ok"}


# --- Calendly ---

@app.post("/auth/calendly/connect")
def calendly_connect(req: CalendlyConnectRequest):
    """
    Store a Calendly Personal Access Token and verify it.
    Generate one at: Calendly → Integrations → API & Webhooks → Personal Access Tokens.
    """
    try:
        from auth.calendly_auth import save_token, is_connected
        save_token(req.token)
        if not is_connected():
            from auth.calendly_auth import disconnect
            disconnect()
            raise HTTPException(status_code=400, detail="Token verification failed. Check your Calendly Personal Access Token.")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/calendly/disconnect")
def calendly_disconnect():
    from auth.calendly_auth import disconnect
    disconnect()
    return {"status": "ok"}


# --- Unified calendar actions ---

@app.get("/calendars/sync")
def calendars_sync(days_ahead: int = Query(default=7)):
    """Return a merged list of events from all connected providers."""
    try:
        from tools.unified_calendar import get_all_events
        events = get_all_events(days_ahead)
        return {
            "days_ahead": days_ahead,
            "count": len(events),
            "events": [
                {
                    "id": e.id,
                    "title": e.title,
                    "start": e.start.isoformat(),
                    "end": e.end.isoformat(),
                    "provider": e.provider,
                    "location": e.location,
                    "description": e.description,
                }
                for e in events
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendars/conflicts")
def calendars_conflicts(days_ahead: int = Query(default=7)):
    """Return overlapping events across all connected providers."""
    try:
        from tools.unified_calendar import get_all_events, find_conflicts
        events = get_all_events(days_ahead)
        conflicts = find_conflicts(events)
        return {
            "days_ahead": days_ahead,
            "conflict_count": len(conflicts),
            "conflicts": [
                {
                    "event_a": {"id": a.id, "title": a.title, "start": a.start.isoformat(), "end": a.end.isoformat(), "provider": a.provider},
                    "event_b": {"id": b.id, "title": b.title, "start": b.start.isoformat(), "end": b.end.isoformat(), "provider": b.provider},
                }
                for a, b in conflicts
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
