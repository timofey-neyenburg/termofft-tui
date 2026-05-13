"""LRU+TTL кэш поверх таблицы CacheEntry."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from thermofft.storage.db import session_scope
from thermofft.storage.models import CacheEntry


def make_cache_key(input_path: str | Path, config_dict: dict) -> str:
    """SHA256(canonical input fingerprint + config)."""
    p = Path(input_path)
    try:
        stat = p.stat()
        finger = f"{p.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    except FileNotFoundError:
        finger = str(p.resolve())
    canon = finger + "|" + json.dumps(config_dict, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def get_cached(
    db_path: str | Path, cache_key: str, ttl_hours: float = 24.0
) -> dict | None:
    cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
    with session_scope(db_path) as sess:
        entry = sess.execute(
            select(CacheEntry).where(CacheEntry.cache_key == cache_key)
        ).scalar_one_or_none()
        if entry is None or entry.created_at < cutoff:
            return None
        entry.hits += 1
        entry.last_hit_at = datetime.utcnow()
        return json.loads(entry.payload_json)


def put_cached(
    db_path: str | Path,
    cache_key: str,
    payload: dict,
    run_uid: str = "",
    capacity: int = 8,
) -> None:
    with session_scope(db_path) as sess:
        existing = sess.execute(
            select(CacheEntry).where(CacheEntry.cache_key == cache_key)
        ).scalar_one_or_none()
        if existing is not None:
            existing.payload_json = json.dumps(payload, default=str)
            existing.created_at = datetime.utcnow()
            existing.last_hit_at = datetime.utcnow()
            existing.run_uid = run_uid or existing.run_uid
            return

        sess.add(CacheEntry(
            cache_key=cache_key,
            payload_json=json.dumps(payload, default=str),
            run_uid=run_uid,
        ))
        sess.flush()

        all_entries = sess.execute(
            select(CacheEntry).order_by(CacheEntry.last_hit_at.asc())
        ).scalars().all()
        excess = len(all_entries) - capacity
        for stale in all_entries[: max(0, excess)]:
            sess.delete(stale)
