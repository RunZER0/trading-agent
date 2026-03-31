"""Supabase client dependency."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Get or create the Supabase client singleton."""
    return create_client(settings.supabase_url, settings.supabase_key)
