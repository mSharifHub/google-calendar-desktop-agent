import time
import logging
from typing import Optional, TypeVar, Callable

logger = logging.getLogger(__name__)

# Default retry settings
RETRIES = 3
RETRY_DELAY = 1.0  # seconds; doubles each attempt

T = TypeVar("T")


def with_retry(
        fn: Callable[..., T],
        *args,
        retries: int = RETRIES,
        delay: float = RETRY_DELAY,
        label: str = "",
        **kwargs,
) -> T:
    """
    Call fn(*args, **kwargs) up to `retries` times with exponential backoff.
    This is highly recommended for API calls to handle rate limits and transient network errors.
    """
    last_exc: Optional[Exception] = None
    prefix = f"{label} " if label else ""

    # Ensure at least 1 attempt is made, even if retries is somehow passed as 0
    max_attempts = max(1, retries)

    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < max_attempts:
                # Exponential backoff: 1s, 2s, 4s, etc.
                wait = delay * (2 ** (attempt - 1))
                logger.warning(
                    f"{prefix}Attempt {attempt}/{max_attempts} failed, retrying in {wait:.1f}s: {e}"
                )
                time.sleep(wait)

    # If all attempts fail, raise the last exception caught
    if last_exc:
        raise last_exc
    else:
        # Fallback if something goes wrong and no exception was caught but loop ended
        raise RuntimeError(f"{prefix}Function failed with no exceptions caught.")