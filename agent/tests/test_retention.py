"""Session retention purge — exercised against a fake connection so the SQL
contract (which tables, keyed how) is pinned without a live Postgres."""

import asyncio

from agent import retention


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows


class FakeConnection:
    def __init__(self, stale_thread_ids):
        # Pool connections use dict_row (agent/db.py) — rows are dicts.
        self.stale = [{"thread_id": tid} for tid in stale_thread_ids]
        self.statements: list[tuple[str, tuple]] = []

    async def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if sql.lstrip().upper().startswith("SELECT"):
            return FakeCursor(self.stale)
        return FakeCursor([])


def test_purge_deletes_all_checkpoint_tables_for_stale_threads() -> None:
    conn = FakeConnection(["old-1", "old-2"])
    purged = asyncio.run(retention.purge_stale_sessions(conn, ttl_days=30))

    assert purged == 2
    deletes = [sql for sql, _ in conn.statements if sql.startswith("DELETE")]
    for table in retention.CHECKPOINT_TABLES:
        assert any(table in sql for sql in deletes), table
    assert any("app.sessions" in sql for sql in deletes)
    # every delete targets exactly the stale ids
    for sql, params in conn.statements:
        if sql.startswith("DELETE"):
            assert params == (["old-1", "old-2"],)


def test_purge_noop_when_nothing_stale() -> None:
    conn = FakeConnection([])
    purged = asyncio.run(retention.purge_stale_sessions(conn, ttl_days=30))
    assert purged == 0
    assert not [sql for sql, _ in conn.statements if sql.startswith("DELETE")]


def test_touch_session_upserts_last_seen() -> None:
    conn = FakeConnection([])
    asyncio.run(retention.touch_session(conn, "thread-9"))
    sql, params = conn.statements[0]
    assert "ON CONFLICT (thread_id) DO UPDATE" in sql
    assert params == ("thread-9",)


def test_ttl_configurable_via_env(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_TTL_DAYS", "7")
    assert retention.session_ttl_days() == 7
    monkeypatch.delenv("SESSION_TTL_DAYS")
    assert retention.session_ttl_days() == 30  # default
