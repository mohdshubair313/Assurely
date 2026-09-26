"""Authentication and RBAC role checks.

Implements:
  - Token/session-based authentication (strategy TBD in Phase 1).
  - Role extraction from the ``users.role`` column (customer | advisor | admin).
  - FastAPI dependency callables for route-level access control:
      * ``require_role("customer")``
      * ``require_role("advisor")``
      * ``require_role("admin")``
  - A customer sees only their own sessions.
  - An advisor sees only cases assigned via ``escalations.assigned_advisor``.
  - An admin has full access.

Per LLD § 7.4: auth/RBAC is worth having from the first version of the API,
not retrofitted after the advisor console exists.
"""
