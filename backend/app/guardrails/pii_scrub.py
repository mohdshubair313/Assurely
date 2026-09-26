"""PII scrubbing — detects and masks personally identifiable information.

Used by input_validate to sanitize user messages before they enter
the graph, and by explanation_report to ensure no raw PII leaks
into the output.

Handles:
  - Aadhaar numbers
  - PAN numbers
  - Phone numbers
  - Email addresses
  - Bank account / IFSC codes
  - Full names (when detectable)

Masking is applied before any LLM call, especially important for
free-tier providers where prompts may be used for model improvement
(see HLD/LLD § 1 Gemini caveat).
"""
