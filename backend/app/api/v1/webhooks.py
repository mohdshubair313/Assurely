"""POST /v1/webhook/whatsapp — inbound WhatsApp channel bridge.

DEFERRED: WhatsApp is explicitly out of scope for Phase 1 (deferred to Phase 4+).
This file exists for architectural completeness per PROJECT_STRUCTURE.md.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/webhook/whatsapp")
async def whatsapp_webhook() -> dict[str, str]:
    """Inbound WhatsApp webhook (deferred to Phase 4+)."""
    return {"status": "deferred", "message": "WhatsApp integration scheduled for Phase 4"}
