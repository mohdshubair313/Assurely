"""Short synchronous transactions run in FastAPI's dependency thread pool.

No provider API call, email matching or user-supplied local UUID is involved.
"""

import uuid
from functools import lru_cache
from typing import cast

from fastapi import HTTPException
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.connection_urls import checkpoint_conninfo
from app.models.db.auth_identity import AuthEvent, AuthIdentity
from app.models.db.user import User


@lru_cache(maxsize=2)
def _engine(url: str) -> Engine:
    parsed = make_url(checkpoint_conninfo(url)).set(drivername="postgresql+psycopg")
    return create_engine(parsed, pool_pre_ping=True, pool_size=5, max_overflow=5,
                         pool_timeout=5, hide_parameters=True,
                         connect_args={"connect_timeout": 5,
                                       "options": "-c statement_timeout=5000 -c lock_timeout=5000"})


def resolve_identity(issuer: str, subject: str) -> uuid.UUID:
    try:
        with _engine(get_settings().database_url).begin() as db:
            # Serialize first-use creation, including concurrent first requests.
            db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                       {"key": f"clerk:{issuer}:{subject}"})
            row = db.execute(select(AuthIdentity.user_id, AuthIdentity.disabled).where(
                AuthIdentity.provider == "clerk", AuthIdentity.issuer == issuer,
                AuthIdentity.subject == subject,
            )).first()
            if row is not None:
                if row.disabled:
                    raise HTTPException(403, "This account is disabled.")
                return cast(uuid.UUID, row.user_id)
            local_id = uuid.uuid4()
            db.execute(insert(User).values(id=local_id, role="customer"))
            db.execute(insert(AuthIdentity).values(id=uuid.uuid4(), provider="clerk",
                       issuer=issuer, subject=subject, user_id=local_id))
            db.execute(insert(AuthEvent).values(id=uuid.uuid4(), user_id=local_id,
                       action="identity_created", details={"provider": "clerk", "issuer": issuer}))
            return local_id
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Identity storage is unavailable.") from exc
