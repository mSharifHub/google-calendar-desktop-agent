from fastapi import APIRouter, HTTPException
import logging

# Fixed import path to align with the rest of the application
from auth.google_auth import get_user_info

logger = logging.getLogger(__name__)

router = APIRouter()

_user_info: dict | None = None


@router.get("/user")
def user():
    """
    Fetches the user's Google profile information.
    Caches the user info after the first successful fetch.
    """
    global _user_info
    if _user_info is None:
        try:
            from auth.google_auth import is_connected
            if not is_connected():
                return {"name": "", "given_name": "", "email": "", "picture": ""}
            _user_info = get_user_info()
        except Exception as e:
            logger.error(f"Could not fetch user info: {e}", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail="Could not fetch user information from the provider.",
            )

    return {
        "name":       _user_info.get("name", ""),
        "given_name": _user_info.get("given_name", ""),
        "email":      _user_info.get("email", ""),
        "picture":    _user_info.get("picture", ""),
    }