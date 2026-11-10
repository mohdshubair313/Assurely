"""Release inventory is truthful configuration readiness, never manufactured approval."""

from typing import Any

from app.core.config import Settings


def release_status(settings: Settings) -> dict[str, Any]:
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
    }
