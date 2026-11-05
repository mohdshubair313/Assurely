"""Isolated synthetic browser fixture server. Never run against an application DB."""

# ruff: noqa: E402

import importlib
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import jwt
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy.engine import make_url

if os.environ.get("ASSURELY_SYNTHETIC_BROWSER_TEST") != "1":
    raise RuntimeError("Explicit synthetic browser-test flag is required")
if make_url(os.environ["DATABASE_URL"]).database != "policy_review_test_terms":
    raise RuntimeError("Dedicated disposable test database required")

from app.core.config import Settings

Settings.model_config["env_file"] = None
for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
             "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "ADVISOR_WEBHOOK_URL"):
    os.environ[name] = ""
os.environ.update(ENVIRONMENT="staging", AUTH_ISSUER="https://test.example/",
                 AUTH_AUDIENCE="browser-test", AUTH_JWKS_URL="https://test.example/jwks",
                 ADVISOR_SUBJECTS='["00000000-0000-4000-8000-000000000123"]')
os.environ["BACKEND_GATEWAY_TOKEN"] = "synthetic-browser-gateway-key-only-20261103"

from app.core import security
from app.graph.runtime import durable_graph
from app.main import app, lifespan

os.environ["POLICY_REVIEW_TEST_DATABASE_URL"] = os.environ["DATABASE_URL"]

from tests.integration.test_reviewed_policy_terms import (
    database,
    import_terms,
    stage_and_publish,
)
from tests.unit.test_policy_publication import publication_input

private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
# Disposable local TLS authority for the synthetic OIDC browser fixture only.
subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
    .public_key(private.public_key()).serial_number(x509.random_serial_number())
    .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
    .not_valid_after(datetime.now(UTC) + timedelta(days=1))
    .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .sign(private, hashes.SHA256()))
Path("/artifacts/oidc-fixture-cert.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
Path("/artifacts/oidc-fixture-key.pem").write_bytes(private.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
))
security._jwks_client = lambda _: SimpleNamespace(
    get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key()),
)
module = importlib.import_module("app.graph.build_graph")


async def intake(state):
    return {"missing_fields": [], "user_profile": {"age": 35, "city_tier": "tier_1",
            "dependents": 0, "pre_existing_conditions": []}}


async def intent(state):
    return {"intent": "health"}


async def health(state):
    return {"retrieved_facts": []}


module.needs_intake_node, module.intent_router_node = intake, intent
module.health_domain_agent_node = health


@asynccontextmanager
async def fixture_lifespan(application):
    # Test fixture creates and drops only the explicitly named disposable schema.
    os.environ["POLICY_REVIEW_TEST_DATABASE_URL"] = os.environ["DATABASE_URL"]
    generator = database.__wrapped__()
    _, factory, _ = await anext(generator)
    try:
        digest, _, command = await stage_and_publish(factory, publication_input.__wrapped__())
        await import_terms(factory, digest, command)
        async with durable_graph(setup=True):
            pass
        now = int(time.time())
        tokens = {}
        for role, subject in {"owner": "00000000-0000-4000-8000-000000000456",
                              "advisor": "00000000-0000-4000-8000-000000000123"}.items():
            tokens[role] = jwt.encode({"sub": subject, "iss": "https://test.example/",
                "aud": "browser-test", "iat": now, "exp": now + 3600}, private, algorithm="RS256")
        Path("/artifacts/browser-fixture.json").write_text(json.dumps({
            "tokens": tokens, "publication": digest,
        }))
        # Avoid initializing a real vector store; all clause retrieval is synthetic.
        vector = importlib.import_module("app.rag.vector_store")
        vector.get_vector_store = lambda: None
        async with lifespan(application):
            yield
    finally:
        try:
            await anext(generator)
        except StopAsyncIteration:
            pass
        finally:
            await generator.aclose()


if __name__ == "__main__":
    app.router.lifespan_context = fixture_lifespan
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
