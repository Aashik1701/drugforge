"""
Asynchronous Supabase database service for persisting prediction results.

Inserts a record into the 'predictions' table after every successful
ML prediction.  Uses the Supabase REST API via httpx for non-blocking
async operations.

Environment Variables Required:
    SUPABASE_URL: Project URL  (e.g. https://xyz.supabase.co)
    SUPABASE_KEY: Anon / service-role key
"""

import os
import logging
from typing import Optional, List

import httpx
from dotenv import load_dotenv

from schemas.prediction import PredictionCreate, PredictionRecord

load_dotenv()

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION  (read once at import time, refreshed by reload_config)
# ============================================================================

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
PREDICTIONS_TABLE: str = "predictions"


def reload_config() -> None:
    """Re-read env vars (useful after a dotenv reload)."""
    global SUPABASE_URL, SUPABASE_KEY
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def _headers() -> dict:
    """
    Build Supabase REST API headers.

    Returns:
        Dict of HTTP headers with API key and auth bearer.

    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_KEY is not configured.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY must be set in .env. "
            "Database features are disabled."
        )
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _table_url() -> str:
    """Full REST URL for the predictions table."""
    return f"{SUPABASE_URL}/rest/v1/{PREDICTIONS_TABLE}"


# ============================================================================
# WRITE
# ============================================================================


async def save_prediction(prediction: PredictionCreate) -> Optional[PredictionRecord]:
    """
    Insert a prediction record into the Supabase 'predictions' table.

    Called after every successful ML prediction.  Failures are logged
    but **never** propagated — the prediction response is still returned
    to the user.

    Args:
        prediction: Fully-populated PredictionCreate schema.

    Returns:
        PredictionRecord on success, None on failure.
    """
    try:
        payload = prediction.model_dump(exclude_none=True)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _table_url(),
                json=payload,
                headers=_headers(),
            )

        if resp.status_code in (200, 201):
            rows = resp.json()
            if isinstance(rows, list) and rows:
                logger.info(
                    "✅ Prediction saved: model=%s smiles=%s...",
                    prediction.model_type,
                    prediction.smiles[:20],
                )
                return PredictionRecord(**rows[0])
            logger.warning("Unexpected Supabase response format: %s", rows)
            return None

        logger.error(
            "❌ Supabase insert failed: status=%s body=%s",
            resp.status_code,
            resp.text,
        )
        return None

    except ValueError as exc:
        logger.warning("⚠️ Database not configured: %s", exc)
        return None
    except httpx.TimeoutException:
        logger.error("❌ Supabase request timed out")
        return None
    except Exception as exc:
        logger.error("❌ Unexpected DB error: %s", exc)
        return None


# ============================================================================
# READ
# ============================================================================


async def get_predictions_by_user(user_id: str) -> List[PredictionRecord]:
    """
    Fetch all predictions for a given user, most recent first.

    Args:
        user_id: Authenticated user's UUID.

    Returns:
        List of PredictionRecord (empty list on failure).
    """
    try:
        params = {
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc",
            "limit": "100",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _table_url(),
                headers=_headers(),
                params=params,
            )

        if resp.status_code == 200:
            return [PredictionRecord(**r) for r in resp.json()]

        logger.error("❌ Fetch predictions failed: %s", resp.status_code)
        return []

    except Exception as exc:
        logger.error("❌ Error fetching predictions: %s", exc)
        return []


async def get_prediction_by_id(
    prediction_id: str, user_id: Optional[str] = None
) -> Optional[PredictionRecord]:
    """
    Retrieve a single prediction by its UUID.

    Args:
        prediction_id: Row UUID.
        user_id: Optional ownership filter.

    Returns:
        PredictionRecord if found, else None.
    """
    try:
        params: dict = {"id": f"eq.{prediction_id}"}
        if user_id:
            params["user_id"] = f"eq.{user_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _table_url(),
                headers=_headers(),
                params=params,
            )

        if resp.status_code == 200:
            rows = resp.json()
            return PredictionRecord(**rows[0]) if rows else None
        return None

    except Exception as exc:
        logger.error("❌ Error fetching prediction %s: %s", prediction_id, exc)
        return None


# ============================================================================
# DELETE
# ============================================================================


async def delete_prediction(prediction_id: str, user_id: str) -> bool:
    """
    Delete a prediction (ownership check via user_id).

    Args:
        prediction_id: Row UUID.
        user_id: Must match row's user_id.

    Returns:
        True if deleted, False otherwise.
    """
    try:
        params = {
            "id": f"eq.{prediction_id}",
            "user_id": f"eq.{user_id}",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                _table_url(),
                headers=_headers(),
                params=params,
            )

        if resp.status_code in (200, 204):
            logger.info("✅ Prediction %s deleted", prediction_id)
            return True

        logger.error("❌ Delete failed: status=%s", resp.status_code)
        return False

    except Exception as exc:
        logger.error("❌ Error deleting prediction %s: %s", prediction_id, exc)
        return False


# ============================================================================
# HEALTH CHECK
# ============================================================================


async def check_database_connection() -> bool:
    """
    Verify Supabase connectivity by issuing a lightweight query.

    Returns:
        True if the predictions table is reachable.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                _table_url(),
                headers=_headers(),
                params={"limit": "1"},
            )
        return resp.status_code == 200

    except ValueError:
        logger.warning("⚠️ Supabase not configured — DB features disabled")
        return False
    except Exception as exc:
        logger.error("❌ DB health check failed: %s", exc)
        return False
