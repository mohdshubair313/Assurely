"""Pydantic request/response schemas for the API layer.

Defines the data contracts between the frontend and backend:
  - MessageRequest / MessageResponse (POST /v1/message)
  - ConsentRequest / ConsentResponse (POST /v1/consent)
  - SessionResponse (GET /v1/session/{id})
  - Citation schema (source, url, last_verified)
  - Error response schema

These schemas enforce the structured response format the UI expects
(see design.md § 14 "API-facing UI contracts").
"""
