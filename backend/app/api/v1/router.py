"""V1 API router — aggregates all v1 endpoint modules.

Includes:
  - ``message.py``   →  POST /v1/message
  - ``consent.py``   →  POST /v1/consent
  - ``sessions.py``  →  GET  /v1/session/{id}
  - ``webhooks.py``  →  POST /v1/webhook/whatsapp  (deferred to Phase 4+)

Per LLD § 7.5, the API surface is intentionally small.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.advisor_reviews import router as advisor_reviews_router
from app.api.v1.consent import router as consent_router
from app.api.v1.human_review import router as human_review_router
from app.api.v1.human_review_queue import router as human_review_queue_router
from app.api.v1.identity import router as identity_router
from app.api.v1.message import router as message_router
from app.api.v1.policy_publications import router as policy_publications_router
from app.api.v1.policy_reviews import router as policy_reviews_router
from app.api.v1.report_release import router as report_release_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.vaani import router as vaani_router
from app.api.v1.voice import router as voice_router
from app.api.v1.voice_activity import router as voice_activity_router
from app.api.v1.voice_development import router as voice_development_router
from app.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(message_router, tags=["message"])
api_v1_router.include_router(identity_router, tags=["identity"])
api_v1_router.include_router(consent_router, tags=["consent"])
api_v1_router.include_router(sessions_router, tags=["sessions"])
api_v1_router.include_router(voice_router, tags=["voice"])
api_v1_router.include_router(voice_development_router, tags=["voice-development"])
api_v1_router.include_router(voice_activity_router, tags=["voice-development"])
api_v1_router.include_router(vaani_router, tags=["voice-provider"])
api_v1_router.include_router(webhooks_router, tags=["webhooks"])
api_v1_router.include_router(policy_reviews_router, tags=["policy-reviews"])
api_v1_router.include_router(policy_publications_router, tags=["policy-publications"])
api_v1_router.include_router(advisor_reviews_router, tags=["advisor-reviews"])
api_v1_router.include_router(report_release_router, tags=["report-release"])
api_v1_router.include_router(human_review_router, tags=["human-review"])
api_v1_router.include_router(human_review_queue_router, tags=["human-review-queue"])
