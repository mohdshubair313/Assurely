"""Translate the asyncpg TLS option into libpq's equivalent without weakening it."""

from sqlalchemy.engine import make_url


def checkpoint_conninfo(database_url: str) -> str:
    url = make_url(database_url).set(drivername="postgresql")
    query = dict(url.query)
    ssl = query.pop("ssl", None)
    if ssl is not None:
        if ssl not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
            raise ValueError("Unsupported checkpoint TLS mode.")
        if "sslmode" in query and query["sslmode"] != ssl:
            raise ValueError("Conflicting checkpoint TLS modes.")
        query["sslmode"] = ssl
        if ssl in {"verify-ca", "verify-full"}:
            query.setdefault("sslrootcert", "system")
    return url.set(query=query).render_as_string(hide_password=False)
