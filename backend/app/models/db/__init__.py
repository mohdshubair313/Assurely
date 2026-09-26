"""SQLAlchemy ORM models — one file per table, matching LLD § 7.4.

All models inherit from a shared ``Base`` declarative base defined here.
Import this ``Base`` in alembic/env.py for autogenerate support.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# Import all models so they register with Base.metadata.
# This ensures Alembic autogenerate can see all tables.
from app.models.db.user import User  # noqa: F401, E402
from app.models.db.consent_record import ConsentRecord  # noqa: F401, E402
from app.models.db.session import Session  # noqa: F401, E402
from app.models.db.audit_log import AuditLog  # noqa: F401, E402
from app.models.db.escalation import Escalation  # noqa: F401, E402
from app.models.db.policy_document import PolicyDocument  # noqa: F401, E402
from app.models.db.policy_terms import PolicyTerms  # noqa: F401, E402
from app.models.db.decision_trace import DecisionTrace  # noqa: F401, E402
