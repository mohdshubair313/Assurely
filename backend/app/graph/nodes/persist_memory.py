"""persist_memory — saves session data and decision traces at session end.

Trigger: session end + consent == True for profile persistence.
Reads:   full state.
Writes:  User Profile Memory row (pgvector), decision_trace row (Postgres).
Calls:   Postgres/pgvector write.

Important distinction (from LLD § 7.3 step 10):
  - ``decision_trace`` is written REGARDLESS of consent, since it's
    operational/compliance data rather than personal preference data.
  - User Profile Memory (for returning-user features) is consent-gated
    and deletable on request per DPDP Act 2023.
  - Confirm that split with your DPDP advisor.
"""
