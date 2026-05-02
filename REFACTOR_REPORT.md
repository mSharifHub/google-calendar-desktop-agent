# Backend Refactoring Report

## Summary

Complete refactor of the backend focusing on: eliminating dead/duplicate code, fixing a
silent auth bug, extracting repeated logic into shared helpers, and stripping verbose
print-tracing from auth modules.

---

## Changes by File

### `backend/server.py`  — 478 lines → 38 lines

**Before:** Contained ALL endpoints inline — model config, chat, user profile, every
calendar auth route, and the unified calendar endpoints.  The `routers/` package existed
but was never imported; every route was duplicated between `server.py` and the routers.

**After:** Pure entry point. Creates the FastAPI app, attaches CORS middleware, and mounts
the three routers. No business logic lives here.

```
app.include_router(calendars_router)
app.include_router(models_router)
app.include_router(user_router)
```

**Lines removed:** ~440
**Why it matters:** The routers package was dead code. Now `server.py` is the single source
of truth for app wiring, and each router owns its domain.

---

### `backend/tools/unified_calendar.py`  — 740 lines → ~540 lines

#### Added `_resolve_provider()` helper and `_PROVIDER_DISPLAY_NAMES` dict

**Before:** The provider-name fuzzy-matching `if/elif` chain was copy-pasted in three places:
- `get_all_events()`
- `sync_todays_events()` (header *and* empty-message blocks)
- `sync_all_calendars()` (header *and* empty-message blocks)

That was ~50 lines of nearly-identical `if "google" in p_low: ... elif "apple" in p_low or "icloud" in p_low: ...` blocks.

**After:** Single source of truth:

```python
_PROVIDER_DISPLAY_NAMES = {
    "google": "Google Calendar",
    "apple": "Apple Calendar",
    "outlook": "Outlook Calendar",
    "calendly": "Calendly",
}

def _resolve_provider(name: str) -> Optional[str]:
    p = name.lower().strip()
    if "google" in p:        return "google"
    if "apple" in p or "icloud" in p: return "apple"
    if "outlook" in p or "microsoft" in p: return "outlook"
    if "calendly" in p:      return "calendly"
    return None
```

`get_all_events()`, `sync_todays_events()`, and `sync_all_calendars()` all call
`_resolve_provider()` instead of inline if/elif.

#### Added `_PROVIDER_FETCHERS` dict

```python
_PROVIDER_FETCHERS = {
    "google": _fetch_google,
    "outlook": _fetch_outlook,
    "apple": _fetch_apple,
    "calendly": _fetch_calendly,
}
```

`get_all_events()` iterates this dict instead of calling each fetcher by name. Adding a new
provider requires adding one entry here rather than modifying multiple functions.

#### Simplified `_fetch_apple()`

- Removed the inner try/except block that imported `caldav` just to log the calendar display
  name (unnecessary complexity with no runtime value).
- Removed the dangling `else: pass` at the end of the time-filter block.
- Preserved the date_search → cal.events() fallback logic and its explaining comment, since
  it works around a real iCloud CalDAV limitation.

#### Simplified `sync_todays_events()` and `sync_all_calendars()`

Each shrank from ~30 lines of repeated if/elif to ~10 lines using `_resolve_provider()`.

#### `edit_calendar_event()` / `delete_calendar_event()`

- Replaced `elif event.provider == ...` chains with bare `if` statements (no else-if needed;
  each branch returns early), reducing indentation depth.

---

### `backend/routers/calendars.py`  — Bug fix

**Before:** `apple_connect()` called `get_apple_client()` to verify the connection.
`get_apple_client()` catches all exceptions and returns `None`; it never raises. So a bad
Apple ID / password would silently save the credentials, return `None`, and report success.

**After:** Calls `connect_and_verify()` directly, which raises `ValueError` on failure.
Invalid credentials are now caught, the credentials file is removed, and a 400 error is
returned to the caller.

```python
# Before (silent failure)
get_apple_client()           # returns None on error → no exception raised

# After (correct)
apple_connect_and_verify()   # raises ValueError on error → caught → 400 returned
```

---

### `backend/auth/apple_auth.py`  — 86 lines → 67 lines

- Removed entry/exit `print()` calls (`called`, `→ result`, etc.) from every function.
- Kept the single error print in `get_apple_client()`.
- Added module-level docstring explaining the credential requirement.

---

### `backend/auth/calendly_auth.py`  — 46 lines → 36 lines

- Removed all verbose `print()` calls (entry, result, file-not-found).
- Function bodies are now pure data operations with no side-effect logging.
- Added module-level docstring.

---

### `backend/auth/microsoft_auth.py`  — 150 lines → 107 lines

- Removed entry/exit `print()` calls throughout.
- Kept the single error print for a failed token refresh (useful for diagnosing auth issues
  silently after the user is already logged in).
- Added module-level docstring.
- Removed the `GRAPH_BASE` constant that was only used in the tools, not this file.

---

### `backend/auth/google_auth.py`  — 105 lines → 87 lines

- Removed entry/exit `print()` calls throughout.
- Simplified `get_service()` to a one-liner (`return build(...)`).
- Added module-level docstring.

---

## Architectural Rules Enforced

| Rule | Where enforced |
|------|---------------|
| Check only connected providers | Each `_fetch_*` function calls `is_connected()` before any API request. `get_all_events()` skips providers that return `[]`. |
| "Check my calendar" → all connected | `sync_todays_events(provider=None)` / `sync_all_calendars(provider=None)` iterate all fetchers via `_PROVIDER_FETCHERS`. |
| "Check my Apple calendar" → one provider | `_resolve_provider("apple")` → `"apple"` → only `_fetch_apple()` is called. |
| Provider-specific tools only load when connected | `agent/agent.py` checks `is_connected()` before importing each provider's tool set. |

---

## Files Not Changed

| File | Reason |
|------|--------|
| `routers/models.py` | Already clean; has improved delta streaming vs old server.py version. |
| `routers/user.py` | Already clean; uses proper `logging` module. |
| `tools/calendar_tools.py` | Clean; minimal, no duplication. |
| `tools/outlook_tools.py` | Clean; good use of `_headers()` helper. |
| `tools/calendly_tools.py` | Clean; minimal, no duplication. |
| `tools/apple_tools.py` | Clean; CalDAV iteration logic is necessarily verbose due to API limitations. |
| `agent/agent.py` | Clean; conditional tool loading pattern is correct. |

---

## Line Count Delta

| File | Before | After | Change |
|------|--------|-------|--------|
| server.py | 478 | 38 | -440 |
| unified_calendar.py | 740 | ~540 | -200 |
| apple_auth.py | 86 | 67 | -19 |
| calendly_auth.py | 46 | 36 | -10 |
| microsoft_auth.py | 150 | 107 | -43 |
| google_auth.py | 105 | 87 | -18 |
| **Total** | **1605** | **~875** | **-730** |
