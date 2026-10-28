"""Scheduled prong. Scrapes store sources, parses/cleans with an LLM,
normalizes unit prices and writes products + embeddings to Postgres.

Batch process — no HTTP surface. Postgres is the only interface to `api`.
"""
