"""Release inventory is truthful configuration readiness, never manufactured approval."""

import uuid
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from app.core.config import Settings


def release_status(settings: Settings) -> dict[str, Any]:
    # Configuration is observable here; database/worker/provider acceptance is not.
    try:
        uuid.UUID(settings.vaani_agent_id)
        agent_uuid = True
    except ValueError:
        agent_uuid = False
    try:
        origin = urlsplit(settings.vaani_staging_base_url)
        secure_origin = bool(
            origin.scheme == "https"
            and origin.hostname
            and not origin.username
            and not origin.password
            and origin.path in ("", "/")
            and not origin.query
            and not origin.fragment
            and origin.port != 0
            and not any(
                c.isspace() or ord(c) < 32 or c == "\\" for c in settings.vaani_staging_base_url
            )
        )
    except ValueError:
        secure_origin = False
    try:
        Fernet(settings.voice_token_encryption_key.get_secret_value().encode())
        encryption = True
    except (ValueError, TypeError):
        encryption = False
    checks = {
        "staging_environment": settings.environment == "staging",
        "clerk_issuer_configured": settings.auth_provider == "clerk"
        and bool(settings.auth_issuer.strip()),
        "agent_identifier_uuid_shape": agent_uuid,
        "api_key_present": bool(settings.vaani_api_key.get_secret_value().strip()),
        "https_origin_shape": secure_origin,
        "byol_credential_minimum_length": len(settings.vaani_byol_token.get_secret_value()) >= 32,
        "webhook_secret_minimum_length": len(settings.vaani_webhook_secret.get_secret_value())
        >= 32,
        "private_token_encryption_key_shape": encryption,
        "test_subject_allowlist_configured": bool(settings.voice_test_subjects),
        "agent_review_configuration_flag": settings.vaani_dev_agent_reviewed,
        "byol_configuration_flag": settings.vaani_byol_enabled,
        "signed_ingress_configuration_flag": settings.vaani_ingress_enabled,
        "dispatch_configuration_flag": settings.vaani_dispatch_enabled,
    }
    return {
        "customer_calls_enabled": False,
        "paid_billing_enabled": False,
        "synthetic_development_enabled": settings.voice_development_enabled,
        "required_external_acceptance": [
            "owned_agent_no_fallback_and_vendor_retention",
            "authorized_byol_handshake_and_signed_vendor_terminal_event",
            "real_audio_reconnect_hard_termination_and_usage_measurement",
            "qualified_policy_calculator_and_human_review_approval",
            "merchant_plan_tax_cancellation_and_vendor_privacy_approval",
            "device_language_accessibility_and_operational_rollout_review",
        ],
        "disconnect_settles_usage": False,
        "synthetic_tests_are_live_acceptance": False,
        "readiness_scope": "configuration_inventory_only",
        "development_readiness": (
            "disabled"
            if not settings.voice_development_enabled
            else "awaiting_external_acceptance"
            if all(checks.values())
            else "configuration_incomplete"
        ),
        "configuration_checks": checks,
        "runtime_observations": {
            "application_schema": "not_checked",
            "api_recovery_loop": "not_checked",
            "independent_recovery_worker": "not_checked",
            "current_provider_authentication": "not_checked",
            "genuine_audio_delivery": "not_verified",
        },
        "implementation_inventory": {
            "durable_sessions_and_reservations": "implemented_locally",
            "signed_events_and_usage_reconciliation": "implemented_locally",
            "livekit_development_controls": "implemented_locally",
            "reviewed_report_speech": "implemented_locally_gated",
            "session_activity_recap": "implemented_locally_gated",
            "saved_report_excerpts": "implemented_locally_gated",
            "natural_speech_followups": "not_implemented",
            "conversation_summary": "not_implemented",
            "reviewed_claim_expense_simulator": "not_implemented",
            "commercial_cancellation_and_refunds": "not_implemented",
        },
    }
