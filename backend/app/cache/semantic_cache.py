"""Semantic cache — embedding-based response cache.

Per HLD/LLD § 13: semantic caching catches repeated questions asked
in different words ("does this cover critical illness" vs. "is critical
illness included") by comparing embeddings instead of exact text.

Production benchmarks report 40–86% cost reductions depending on
query repetition, with cache hits returning in single-digit milliseconds.

Target nodes: ``needs_intake`` and ``compare_verify`` specifically
(the two handling the most repetitive question types).

Skip the cache for anything touching a specific user's private
profile data — a cached answer from someone else would be wrong.

Uses the existing vector DB (Chroma) to store:
  (query_embedding, response, metadata, TTL)
"""
