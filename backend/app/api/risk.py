"""Risk configuration API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.dependencies import get_supabase
from app.models.schemas import RiskConfig

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/config")
async def get_risk_config():
    """Get current risk configuration."""
    supabase = get_supabase()
    resp = supabase.table("risk_config").select("*").limit(1).execute()
    if not resp.data:
        return RiskConfig().model_dump()
    return resp.data[0]


@router.put("/config")
async def update_risk_config(config: RiskConfig):
    """Update risk configuration."""
    supabase = get_supabase()

    # Get existing config ID
    existing = supabase.table("risk_config").select("id").limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Risk config not found")

    update_data = config.model_dump(exclude={"id"})
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    resp = (
        supabase.table("risk_config")
        .update(update_data)
        .eq("id", existing.data[0]["id"])
        .execute()
    )
    return resp.data[0] if resp.data else update_data
