"""Application schema required by the current runtime."""

APPLICATION_SCHEMA_REVISION = "017_voice_byol_turns"


def compatible_schema(revision: str | None, settings: object) -> bool:
    """Older schemas remain usable only with their additive features disabled."""
    if revision == APPLICATION_SCHEMA_REVISION:
        return True
    if getattr(settings, "voice_byol_evidence_enabled", False):
        return False
    if revision == "016_voice_case_binding":
        return True
    if getattr(settings, "voice_case_binding_enabled", False):
        return False
    if revision == "015_human_review_requests":
        return True
    if getattr(settings, "human_review_requests_enabled", False):
        return False
    if revision == "014_voice_managed":
        return True
    return revision == "013_vaani_backend" and not any(
        getattr(settings, name, False)
        for name in (
            "voice_development_enabled",
            "voice_tools_enabled",
            "voice_billing_test_enabled",
            "voice_funded_test_enabled",
        )
    )
