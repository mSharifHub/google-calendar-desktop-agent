

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Directory Structure](#2-directory-structure)
3. [Request Lifecycle](#3-request-lifecycle)
4. [Data Model — UnifiedEvent](#4-data-model--unifiedevent)
5. [Authentication Layer (`auth/`)](#5-authentication-layer-auth)
6. [Provider Tool Layer (`tools/`)](#6-provider-tool-layer-tools)
7. [Unified Calendar Tool (`tools/unified_calendar_tool.py`)](#7-unified-calendar-tool-toolsunified_calendar_toolpy)
8. [Agent (`agent/agent.py`)](#8-agent-agentagentpy)
9. [REST API Routers (`routers/`)](#9-rest-api-routers-routers)
10. [Server Entry Point (`server.py`)](#10-server-entry-point-serverpy)
11. [Utilities (`utils/`)](#11-utilities-utils)
12. [Adding a New Calendar Provider](#12-adding-a-new-calendar-provider)
13. [Adding a New LLM Backend](#13-adding-a-new-llm-backend)
14. [Timezone Rules](#14-timezone-rules)
15. [Error Handling Contract](#15-error-handling-contract)
16. [Credential Files Reference](#16-credential-files-reference)

---

## 1. Architecture Overview

```
User message
     │
     ▼
POST /chat  (routers/models.py)
     │
     ▼
LangGraph Agent  (agent/agent.py)
     │  Sees 7 unified tools only
     ▼
unified_calendar_tool.py   ◄── single interface for the LLM
     │
     ├── google_calendar_tools.py   → Google Calendar API v3
     ├── outlook_tools.py           → Microsoft Graph API v1.0
     ├── apple_calendar_tools.py    → iCloud CalDAV
     └── calendly_tools.py          → Calendly REST API
          │
          ▼
     auth/ modules  (credentials + token management)
```

**Key design principle:** The LLM agent never calls provider-specific tools directly.
It calls 7 abstract tools in `unified_calendar_tool.py`, which route to the correct provider.

The REST API (`/calendars/sync`, `/calendars/conflicts`) calls `unified_calendar_tool.get_all_events()` and `find_conflicts()` directly — bypassing the agent — for structured JSON responses.

---

## 2. Directory Structure

```
backend/
├── server.py                        Entry point; mounts routers
├── agent/
│   └── agent.py                     LangGraph agent builder + system prompt
├── auth/
│   ├── google_auth.py               Google OAuth2 token management
│   ├── apple_auth.py                Apple CalDAV credential management
│   ├── microsoft_auth.py            Microsoft OAuth2 token management
│   └── calendly_auth.py             Calendly PAT management
├── tools/
│   ├── unified_event.py             UnifiedEvent dataclass (shared data model)
│   ├── unified_calendar_tool.py     LangChain tools + aggregation logic
│   ├── google_calendar_tools.py     Google fetch/create/edit/delete
│   ├── apple_calendar_tools.py      Apple fetch/create/edit/delete (CalDAV)
│   ├── outlook_tools.py             Outlook fetch/create/edit/delete (Graph API)
│   └── calendly_tools.py            Calendly fetch (read-only)
├── routers/
│   ├── calendars.py                 Auth + calendar REST endpoints
│   ├── models.py                    Session, configure, chat, Ollama endpoints
│   └── user.py                      Google user profile endpoint
└── utils/
    └── retry.py                     Exponential backoff wrapper
```

---

## 3. Request Lifecycle

### Chat Request

```
POST /chat  { message, session_id }
    │
    │  routers/models.py  →  run_stream()
    │  streams AIMessage delta chunks as text/plain
    │
    ▼
agent.stream({ messages: [HumanMessage(message)] })
    │
    │  LangGraph ReAct loop:
    │    1. LLM chooses a tool from the 7 unified tools
    │    2. Tool executes, returns JSON string
    │    3. LLM reads JSON, may call more tools
    │    4. LLM produces final AIMessage
    │
    ▼
unified_calendar_tool.py  (one or more tool calls)
    │
    ▼
provider tool  (fetch / create / edit / delete)
    │
    ▼
provider API  (Google / Outlook / Apple / Calendly)
```

### Configure / Session

```
POST /configure  { backend, api_key, model_name }
    │
    ├── _build_model()  → creates LangChain chat model
    ├── build_agent(model)  → creates LangGraph agent + MemorySaver
    └── returns session_id  (UUID, in-memory)

Sessions are in-memory only — lost on server restart.
```

---

## 4. Data Model — `UnifiedEvent`

**File:** `tools/unified_event.py`

```python
@dataclass
class UnifiedEvent:
    id:          str            # Provider-native event ID / CalDAV UID
    title:       str            # Event summary / subject
    start:       datetime       # Always UTC-aware
    end:         datetime       # Always UTC-aware
    provider:    str            # "google" | "outlook" | "apple" | "calendly"
    location:    str = ""
    description: str = ""
    is_all_day:  bool = False
```

**`to_dict()` output** (used by all tools to return JSON to the LLM):
```json
{
  "id": "abc123",
  "title": "Team Standup",
  "start": "2026-05-02 09:00 AM PDT",
  "end":   "2026-05-02 09:30 AM PDT",
  "provider": "google",
  "location": "Zoom",
  "description": "Daily sync",
  "is_all_day": false
}
```

> `start` and `end` are formatted to `America/Los_Angeles` in `to_dict()`.
> Internally all datetimes are stored as UTC.

**Helper functions** (also in `unified_event.py`):

| Function | Purpose |
|----------|---------|
| `_to_utc(dt)` | Converts any datetime to UTC; treats naive datetimes as UTC |
| `_parse_dt(raw)` | Parses ISO 8601 strings including `Z`-suffix and bare format |

---

## 5. Authentication Layer (`auth/`)

Each provider has its own auth module. All modules expose the same interface:

| Function | Description |
|----------|-------------|
| `is_connected() → bool` | Checks if credential file exists |
| `disconnect()` | Removes credential files |

### 5.1 Google — `auth/google_auth.py`

**Method:** OAuth2 via `google-auth-oauthlib`
**Token file:** `token.json`
**Credential file:** `credentials.json` (downloaded from Google Cloud Console)

**Scopes:**
- `https://www.googleapis.com/auth/calendar`
- `https://mail.google.com/`
- `https://www.googleapis.com/auth/userinfo.profile`
- `https://www.googleapis.com/auth/userinfo.email`
- `openid`

**Key functions:**

```python
connect()             # Opens browser OAuth flow, saves token.json
get_google_creds()    # Returns valid Credentials, auto-refreshes if expired
get_service(api, version)  # Returns authenticated Google API service
get_user_info()       # Returns { name, given_name, email, picture }
```

**Token refresh:** `get_google_creds()` calls `creds.refresh(Request())` automatically if `creds.expired and creds.refresh_token`.

### 5.2 Apple — `auth/apple_auth.py`

**Method:** CalDAV with Apple ID + App-Specific Password
**Credential file:** `apple_credentials.json`
**CalDAV URL:** `https://caldav.icloud.com`

> Users must generate an App-Specific Password at appleid.apple.com → Security → App-Specific Passwords. **Do not use the regular Apple ID password.**

**Key functions:**

```python
save_credentials(username, app_password)  # Writes apple_credentials.json
connect_and_verify()     # Connects to iCloud CalDAV, raises ValueError on failure
get_apple_client()       # Returns authenticated DAVClient or None
```

### 5.3 Microsoft / Outlook — `auth/microsoft_auth.py`

**Method:** OAuth2 Authorization Code Flow
**Files:** `outlook_credentials.json` (app registration), `outlook_token.json` (token)
**Redirect URI:** `http://localhost:8000/auth/outlook/callback`
**Scopes:** `Calendars.ReadWrite User.Read offline_access`

**OAuth flow:**
1. `POST /auth/outlook/setup` → `save_app_credentials()` + `get_auth_url()` → returns auth URL
2. User visits auth URL in browser, grants permission
3. Microsoft redirects to `GET /auth/outlook/callback?code=...`
4. `exchange_code(code)` → POSTs to Microsoft token endpoint → saves `outlook_token.json`

**Token refresh:** `get_access_token()` checks `expires_at` with a 60-second buffer. If expired, POSTs with `grant_type=refresh_token` automatically.

### 5.4 Calendly — `auth/calendly_auth.py`

**Method:** Personal Access Token (PAT)
**Token file:** `calendly_token.json`

Generate a PAT at: Calendly → Integrations → API & Webhooks → Personal Access Tokens.

```python
save_token(pat)        # Writes calendly_token.json
get_calendly_token()   # Returns token string or None
```

---

## 6. Provider Tool Layer (`tools/`)

Each provider module exposes pure Python functions (not `@tool` decorated). These functions are called by `unified_calendar_tool.py`.

### 6.1 Google — `tools/google_calendar_tools.py`

**API:** Google Calendar API v3
**Auth:** `auth/google_auth.get_service('calendar', 'v3')`

| Function | Description |
|----------|-------------|
| `fetch_google_events(days)` | Lists events from `primary` calendar for next N days |
| `create_google_event(summary, start_time, end_time, description, location)` | Creates event; times treated as `America/Los_Angeles` |
| `delete_google_event(event_id)` | Deletes by event ID |
| `edit_google_event(event_id, ...)` | Patches event; **preserves original duration when only start_time changes** |

**Duration preservation in edit:**
```python
# When new_start_time is set but new_end_time is not:
duration  = old_end - old_start
body['end']['dateTime'] = (new_start_dt + duration).isoformat()
```
This prevents the `timeRangeEmpty` 400 error from Google API.

### 6.2 Apple — `tools/apple_calendar_tools.py`

**Protocol:** CalDAV via `caldav` Python library
**Auth:** `auth/apple_auth.get_apple_client()`

| Function | Description |
|----------|-------------|
| `fetch_apple_events(days)` | Searches all calendars; uses `expand=False` to avoid iCloud empty-list bug |
| `create_apple_event(...)` | Builds iCalendar object; writes to "Home" calendar (or first available) |
| `delete_apple_event(event_uid)` | Scans broad date range to find event by UID, then deletes |
| `edit_apple_event(event_uid, ...)` | Finds event by UID, modifies VEVENT fields, deletes old event, saves updated iCal |

**Critical iCloud CalDAV quirks:**

| Quirk | Workaround |
|-------|-----------|
| `date_search(expand=True)` returns empty list | Use `expand=False` in all searches |
| No UID-based REPORT queries | Scan a ±365/730 day window and match UID manually |
| Edit requires delete + re-save | `ev.delete()` then `cal.save_event(ical.to_ical().decode())` |
| No reliable writable calendar detection | Try "Home" calendar first, fall back to index 0 |

**Timezone handling:**
All naive datetime strings passed to create/edit are treated as `America/Los_Angeles`, not UTC.
```python
if start_dt.tzinfo is None:
    start_dt = start_dt.replace(tzinfo=LOCAL_TZ)  # LOCAL_TZ = ZoneInfo("America/Los_Angeles")
```

### 6.3 Outlook — `tools/outlook_tools.py`

**API:** Microsoft Graph API v1.0
**Auth:** `auth/microsoft_auth.get_access_token()`
**Base URL:** `https://graph.microsoft.com/v1.0`

| Function | Description |
|----------|-------------|
| `fetch_outlook_events(days)` | GET `/me/calendarView` with `startDateTime`/`endDateTime` |
| `create_outlook_event(...)` | POST `/me/events`; times are `America/Los_Angeles` |
| `delete_outlook_event(event_id)` | DELETE `/me/events/{id}` |
| `edit_outlook_event(event_id, ...)` | PATCH `/me/events/{id}` with only changed fields |

All HTTP calls go through `_retry()` (3 attempts, exponential backoff).

### 6.4 Calendly — `tools/calendly_tools.py`

**API:** Calendly REST API
**Auth:** Bearer token from `auth/calendly_auth.get_calendly_token()`
**Base URL:** `https://api.calendly.com`

| Function | Description |
|----------|-------------|
| `fetch_calendly_events(days)` | GET `/users/me` → get user URI → GET `/scheduled_events?status=active` |

> Calendly is **read-only** in this system. Create/edit/delete are not supported — Calendly manages its own scheduling pages.

---

## 7. Unified Calendar Tool (`tools/unified_calendar_tool.py`)

This is the **single interface** between the LLM agent and all providers.

### 7.1 Pure Functions (used by REST API)

```python
get_all_events(days_ahead=7) → List[UnifiedEvent]
    # Calls all 4 provider fetch functions, merges, sorts by start time

find_conflicts(events) → List[Tuple[UnifiedEvent, UnifiedEvent]]
    # O(n²) pairwise check: events[i].start < events[j].end and events[j].start < events[i].end
```

### 7.2 Internal Helper

```python
_find_event(name_or_id, events) → UnifiedEvent
    # Matches by exact ID first, then case-insensitive title substring
    # Raises ValueError if 0 or >1 matches
```

### 7.3 LangChain Tools (exposed to the agent)

All tools return JSON strings. The LLM reads the JSON and formulates the response.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `sync_todays_events` | `date: str = None` | Today's events (omit date) or any specific date (`YYYY-MM-DD`) |
| `sync_all_calendars` | `days_ahead: int = 7` | All events for next N days |
| `find_calendar_conflicts` | `days_ahead: int = 7` | Returns conflicting pairs as JSON |
| `resolve_calendar_conflicts` | `days_ahead: int = 7`, `strategy: str` | Same as find_conflicts (LLM resolves) |
| `create_calendar_event` | `summary, start_time, end_time, provider, description, location` | Routes to correct provider |
| `edit_calendar_event` | `name_or_id, new_summary, new_start_time, new_end_time, new_description, new_location` | Finds event across all providers, patches it |
| `delete_calendar_event` | `name_or_id` | Finds event across all providers, deletes it |

**`sync_todays_events` date logic:**
```python
# Computes window in local timezone, converts to UTC for filtering
day_start = datetime(target.year, target.month, target.day, 0, 0, 0, tzinfo=DISPLAY_TZ).astimezone(UTC)
day_end   = datetime(target.year, target.month, target.day, 23, 59, 59, tzinfo=DISPLAY_TZ).astimezone(UTC)
days_needed = max((target - today).days + 2, 2)  # fetch enough days to include target
```

**`edit_calendar_event` routing:**
```python
event = _find_event(name_or_id, get_all_events(days_ahead=60))
# Routes to: edit_google_event | edit_outlook_event | edit_apple_event
```

---

## 8. Agent (`agent/agent.py`)

### 8.1 `build_agent(model)`

Accepts any LangChain chat model and returns `(agent, config)`.

```python
tools = [
    sync_todays_events, sync_all_calendars,
    find_calendar_conflicts, resolve_calendar_conflicts,
    delete_calendar_event, edit_calendar_event, create_calendar_event
]
agent = create_agent(model, tools, system_prompt=..., checkpointer=MemorySaver())
config = {"configurable": {"thread_id": "terminal_session_1"}}
```

**Memory:** `MemorySaver` stores conversation history in-memory per `thread_id`. The same thread ID is used for all sessions, which means conversation history is shared across configure calls within the same server process.

### 8.2 System Prompt Routing Rules

The system prompt is formatted at `build_agent` call time with the current date and tomorrow's date:

| User intent | Tool called | Notes |
|------------|-------------|-------|
| "today / what do I have" | `sync_todays_events()` | No args |
| "tomorrow" | `sync_todays_events(date="YYYY-MM-DD")` | Tomorrow's date injected at build time |
| "show [date]" | `sync_todays_events(date="YYYY-MM-DD")` | Agent computes date |
| "next X days / upcoming" | `sync_all_calendars(days_ahead=X)` | |
| "create event" | `create_calendar_event(provider='google')` | Defaults to Google |
| "delete / cancel" | `delete_calendar_event(name_or_id)` | |
| "edit / reschedule" | `edit_calendar_event(name_or_id, ...)` | |
| "conflicts" | `find_calendar_conflicts()` | |

**Critical agent behavior rules (in system prompt):**
- ALWAYS call the tool immediately — never ask "would you like me to?"
- Use the `id` field from prior JSON responses when editing/deleting

### 8.3 Streaming

In `routers/models.py`, the agent is invoked via:
```python
for chunk in agent.stream({"messages": [HumanMessage(content=message)]}, config=config, stream_mode="values"):
    last = chunk["messages"][-1]
    if isinstance(last, AIMessage) and last.content:
        if last.id != last_message_id:          # new message (post tool-call)
            previous_content = ""
            last_message_id = last.id
        new_content = last.content[len(previous_content):]  # delta only
        if new_content:
            yield new_content
            previous_content = last.content
```

This yields only new content per chunk (delta streaming), handling multi-step tool call chains correctly.

---

## 9. REST API Routers (`routers/`)

### 9.1 Calendar Router — `routers/calendars.py`

#### Status

| Method | Path | Description |
|--------|------|-------------|
| GET | `/calendars/status` | Returns `{ google, outlook, apple, calendly }` booleans |

#### Provider Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/google/connect` | Runs OAuth flow (blocks, opens browser) |
| POST | `/auth/outlook/setup` | Saves Azure credentials, returns `{ auth_url }` |
| GET | `/auth/outlook/callback` | Exchanges OAuth code for token; returns HTML close-tab page |
| POST | `/auth/apple/connect` | Saves credentials, verifies CalDAV connection |
| POST | `/auth/calendly/connect` | Saves PAT token, verifies it exists |
| POST | `/auth/{provider}/disconnect` | Removes credential files for the named provider |

**Apple connect** uses `connect_and_verify()` (raises on failure) — credentials are removed if verification fails.

**Outlook callback HTML:** Returns a self-closing HTML page with `setTimeout(() => window.close(), 2000)`.

#### Unified Calendar (REST, not agent)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/calendars/sync?days_ahead=7` | Returns JSON array of all events |
| GET | `/calendars/conflicts?days_ahead=7` | Returns JSON array of conflict pairs |

Response shape for `/calendars/sync`:
```json
{
  "days_ahead": 7,
  "count": 5,
  "events": [
    { "id": "...", "title": "...", "start": "...", "end": "...",
      "provider": "google", "location": "...", "description": "...", "is_all_day": false }
  ]
}
```

### 9.2 Models Router — `routers/models.py`

#### Backend Support

```python
class Backend(str, Enum):
    local = "local"    # Ollama (local)
    claude = "claude"  # Anthropic
    openai = "openai"  # OpenAI
    gemini = "gemini"  # Google Gemini
```

Default model names:
```python
{ local: "llama3.1:latest", claude: "claude-sonnet-4-6", openai: "gpt-4o", gemini: "gemini-2.0-flash" }
```

| Method | Path | Description |
|--------|------|-------------|
| GET | `/backends` | Lists supported backend values |
| GET | `/sessions` | Lists all session IDs with model info |
| DELETE | `/sessions/{session_id}` | Closes and removes a session |
| GET | `/sessions/{session_id}/status` | Returns `{ configured, model_info }` |
| POST | `/configure` | Creates session; returns `{ session_id, model_info }` |
| POST | `/chat` | Streaming chat; returns `text/plain` delta stream |
| POST | `/ollama/pull` | Pulls an Ollama model (blocking) |

#### `_ollama_model_exists(model_name)` logic:
1. Exact match against Ollama's `/api/tags`
2. Adds `:latest` suffix if no tag specified
3. Base-name prefix match (e.g. `llama3.1` matches `llama3.1:8b-instruct-q4_K_M`)

### 9.3 User Router — `routers/user.py`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/user` | Returns Google profile `{ name, given_name, email, picture }` |

Profile is cached in `_user_info` after first successful fetch. Cache is invalidated only on server restart.

---

## 10. Server Entry Point (`server.py`)

```python
app = FastAPI(title="Calendar Assistant", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(calendars_router)
app.include_router(models_router)
app.include_router(user_router)
```

Run:
```bash
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

> CORS is fully open (`allow_origins=["*"]`). Restrict this for production.

---

## 11. Utilities (`utils/`)

### `utils/retry.py` — `with_retry(fn, *args, retries=3, delay=1.0, label="", **kwargs)`

Calls `fn(*args, **kwargs)` up to `retries` times with exponential backoff.

| Attempt | Wait before retry |
|---------|------------------|
| 1 | 1.0s |
| 2 | 2.0s |
| 3 | 4.0s (final, no retry) |

Logs warnings with `label` prefix. Re-raises the last exception if all attempts fail.

**Usage pattern in provider tools:**
```python
_retry = lambda fn, *a, **kw: with_retry(fn, *a, label="[TOOL:google]", **kw)

# Calling a bound method (note: pass the method, not its result)
result = _retry(service.events().list(...).execute)

# Calling a free function with args
resp = _retry(requests.get, url, headers=headers, timeout=15)
```

---

## 12. Adding a New Calendar Provider

Follow these steps to add, e.g., a "Yahoo Calendar" provider:

**Step 1 — Auth module** `auth/yahoo_auth.py`
```python
YAHOO_TOKEN_FILE = "yahoo_token.json"

def save_token(token: str): ...
def get_yahoo_token() -> Optional[str]: ...
def is_connected() -> bool: return os.path.exists(YAHOO_TOKEN_FILE)
def disconnect(): ...
```

**Step 2 — Tool module** `tools/yahoo_calendar_tools.py`
```python
def fetch_yahoo_events(days: int) -> list[UnifiedEvent]: ...
def create_yahoo_event(summary, start_time, end_time, ...) -> str: ...
def edit_yahoo_event(event_id, ...) -> str: ...
def delete_yahoo_event(event_id: str) -> str: ...
```

**Step 3 — Wire into unified tool** `tools/unified_calendar_tool.py`
```python
from tools.yahoo_calendar_tools import fetch_yahoo_events, create_yahoo_event, ...

def get_all_events(days_ahead=7):
    events = (
        fetch_google_events(days_ahead) + fetch_outlook_events(days_ahead) +
        fetch_apple_events(days_ahead) + fetch_calendly_events(days_ahead) +
        fetch_yahoo_events(days_ahead)   # ← add here
    )
    ...

# In create_calendar_event tool:
if p == "yahoo": return json.dumps({"status": create_yahoo_event(...)})
```

**Step 4 — Auth REST endpoint** `routers/calendars.py`
```python
from auth.yahoo_auth import save_token as yahoo_save_token, disconnect as yahoo_disconnect
# Add to _CALENDAR_PROVIDER_MODULES and disconnect_actions dicts
# Add POST /auth/yahoo/connect route
```

**Step 5 — Update system prompt** `agent/agent.py`
```
- "Yahoo calendar" → create_calendar_event(provider='yahoo')
```

---

## 13. Adding a New LLM Backend

Edit `routers/models.py`:

**Step 1 — Add to enum:**
```python
class Backend(str, Enum):
    ...
    mistral = "mistral"
```

**Step 2 — Add default model name:**
```python
_DEFAULT_MODEL_NAMES = {
    ...
    Backend.mistral: "mistral-large",
}
```

**Step 3 — Add to `_build_model()`:**
```python
elif backend == Backend.mistral:
    from langchain_mistralai import ChatMistralAI
    return ChatMistralAI(model=model_name or "mistral-large", api_key=api_key, temperature=0)
```

> The frontend reads `/backends` to populate the dropdown — no frontend changes needed.

---

## 14. Timezone Rules

| Location | Rule |
|----------|------|
| `UnifiedEvent.start` / `.end` | Always UTC internally |
| `UnifiedEvent.to_dict()` | Formatted to `America/Los_Angeles` for LLM display |
| Google create/edit | Sends times with `"timeZone": "America/Los_Angeles"` |
| Outlook create/edit | Sends times with `"timeZone": "America/Los_Angeles"` |
| Apple create/edit | Naive datetimes from agent are `.replace(tzinfo=LOCAL_TZ)` before storing |
| `sync_todays_events` filter | Converts day boundaries to UTC using `DISPLAY_TZ` |
| Agent system prompt | Receives today/tomorrow dates in local time |

**Why Apple needs special handling:**
Google and Outlook accept explicit timezone names in their API payloads. The iCalendar format used by CalDAV uses `TZID` in `DTSTART`/`DTEND`. If a naive datetime is stored, some CalDAV servers treat it as floating time (no timezone) and some treat it as UTC. Explicitly attaching `LOCAL_TZ` ensures Apple Calendar displays the correct local time.

---

## 15. Error Handling Contract

| Layer | Pattern |
|-------|---------|
| Auth modules | Return `None` / raise `ValueError` / raise `RuntimeError` |
| Provider tools | Catch all exceptions; return `"Auth Error: ..."` or `"Error: ..."` string |
| Unified tools | Catch `ValueError` from `_find_event`; return `json.dumps({"error": "..."})` |
| Routers | Raise `HTTPException(status_code=400/500, detail=...)` |
| Agent | LLM reads error JSON and tells user; connection errors → "connect in Settings" |

**Provider tool auth check pattern:**
```python
def create_google_event(...) -> str:
    if not is_connected(): return "Auth Error: Google Calendar not connected."
    ...
```

---

## 16. Credential Files Reference

All files are stored in the **working directory** where the server is launched (typically `backend/`).

| File | Provider | Contents | Created by |
|------|----------|----------|-----------|
| `credentials.json` | Google | OAuth2 client credentials | Downloaded from Google Cloud Console |
| `token.json` | Google | OAuth2 access + refresh token | `connect()` after OAuth flow |
| `apple_credentials.json` | Apple | `{ username, app_password }` | `POST /auth/apple/connect` |
| `outlook_credentials.json` | Outlook | `{ client_id, client_secret, tenant_id }` | `POST /auth/outlook/setup` |
| `outlook_token.json` | Outlook | `{ access_token, refresh_token, expires_at }` | `GET /auth/outlook/callback` |
| `calendly_token.json` | Calendly | `{ token }` | `POST /auth/calendly/connect` |

> **None of these files should be committed to version control.** Add them to `.gitignore`.

**Checking connection status programmatically:**
```python
from auth.google_auth import is_connected as google_ok
from auth.apple_auth import is_connected as apple_ok
from auth.microsoft_auth import is_connected as outlook_ok
from auth.calendly_auth import is_connected as calendly_ok

status = {
    "google": google_ok(), "apple": apple_ok(),
    "outlook": outlook_ok(), "calendly": calendly_ok()
}
```

---

*Last updated: May 2026. Update this document whenever a module's interface or behavior changes.*
