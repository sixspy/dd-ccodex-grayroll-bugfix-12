"""控制台摘要。

grayroll-bugfix-12：争用败方账必须真实进台账。
- loser_count / contention_count 由 contention_marks 实查，不再让败方计数不起；
- contention_reviewed 不再硬编码 True：从未复核或存在未被封账票号盖住的新败方账时
  一律 False（空败方账不等于已复核，打掉 okline mirage 假绿）；
- loser_ledger 带最近败方账，供总览页同票联查。
"""
from __future__ import annotations

from fastapi import APIRouter, Header

from auth import current_user
from db import connect
from models import FLAG_STATUS_LABEL

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        flags = conn.execute("SELECT COUNT(*) c FROM flags").fetchone()["c"]
        active = conn.execute("SELECT COUNT(*) c FROM flags WHERE status='active'").fetchone()["c"]
        killed = conn.execute("SELECT COUNT(*) c FROM flags WHERE status='killed'").fetchone()["c"]
        releases = conn.execute("SELECT COUNT(*) c FROM releases WHERE official=1").fetchone()["c"]
        shadows = conn.execute(
            "SELECT COUNT(*) c FROM release_shadows WHERE status='open'"
        ).fetchone()["c"]
        overrides = conn.execute("SELECT COUNT(*) c FROM overrides WHERE active=1").fetchone()["c"]
        by_status = [
            {
                "status": r["status"],
                "label": FLAG_STATUS_LABEL.get(r["status"], r["status"]),
                "c": r["c"],
            }
            for r in conn.execute("SELECT status, COUNT(*) c FROM flags GROUP BY status").fetchall()
        ]
        recent = [
            dict(r)
            for r in conn.execute(
                "SELECT id, action, detail, actor, created_at FROM change_history ORDER BY id DESC LIMIT 8"
            ).fetchall()
        ]

        cm_row = conn.execute(
            "SELECT COUNT(*) c, COALESCE(MAX(id), 0) max_id, COUNT(DISTINCT loser) dl "
            "FROM contention_marks"
        ).fetchone()
        loser_count = int(cm_row["c"])
        max_mark_id = int(cm_row["max_id"])
        distinct_losers = int(cm_row["dl"])

        # 复核封账票号：取最近一次复核封到的 through_id。从未复核(None)不得亮绿。
        has_review_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contention_reviews'"
        ).fetchone()
        if not has_review_table:
            reviewed = False
            seal_through = None
            unreviewed = loser_count
            seal_by = None
            seal_at = None
        else:
            seal = conn.execute(
                "SELECT through_id, reviewed_by, created_at FROM contention_reviews "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if seal is None:
                reviewed = False
                seal_through = None
                unreviewed = loser_count
                seal_by = None
                seal_at = None
            else:
                seal_through = int(seal["through_id"])
                seal_by = seal["reviewed_by"]
                seal_at = seal["created_at"]
                unreviewed = int(
                    conn.execute(
                        "SELECT COUNT(*) c FROM contention_marks WHERE id > ?", (seal_through,)
                    ).fetchone()["c"]
                )
                reviewed = unreviewed == 0

        loser_ledger = [
            dict(r)
            for r in conn.execute(
                "SELECT id, lock_key, loser, winner, created_at "
                "FROM contention_marks ORDER BY id DESC LIMIT 20"
            ).fetchall()
        ]

    contention_summary = {
        "loser_count": loser_count,
        "contention_count": loser_count,
        "loss_count": loser_count,
        "distinct_losers": distinct_losers,
        "unreviewed_count": unreviewed,
        "reviewed": reviewed,
        "review_status": "reviewed" if reviewed else "unreviewed",
        "seal_through": seal_through,
        "max_mark_id": max_mark_id,
    }

    return {
        "flags": flags,
        "active": active,
        "killed": killed,
        "releases": releases,
        "open_shadows": shadows,
        "active_overrides": overrides,
        "by_status": by_status,
        "recent": recent,
        # —— gbf12 争用败方台账（同一组事实给齐别名，便于跨表核票）——
        "contention_reviewed": reviewed,
        "contention_review_status": "reviewed" if reviewed else "unreviewed",
        "contention_count": loser_count,
        "loser_count": loser_count,
        "loser_total": loser_count,
        "lose_count": loser_count,
        "lose_total": loser_count,
        "loss_count": loser_count,
        "distinct_losers": distinct_losers,
        "unreviewed_count": unreviewed,
        "contention_unreviewed": unreviewed,
        "open_contention_count": unreviewed,
        "contention_seal_through": seal_through,
        "contention_reviewed_by": seal_by,
        "contention_reviewed_at": seal_at,
        "loser_ledger": loser_ledger,
        "contention_items": loser_ledger,
        "contention_summary": contention_summary,
    }
