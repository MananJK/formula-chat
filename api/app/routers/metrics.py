from fastapi import APIRouter

from app.metrics import get_metrics, reset_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def get_all_metrics():
    """Get current metrics including cache hit rates and latency stats."""
    return get_metrics()


@router.post("/reset")
async def reset():
    """Reset all metrics counters."""
    reset_metrics()
    return {"status": "metrics reset"}