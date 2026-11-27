"""变更历史。

grayroll-bugfix-12：历史台账除 change_history 外，把 contention_marks 败方争用痕
以同票行投影进来（entry_type=contention / action=lock_lost），让败方账在台账可见、
可与返回句票号联查。这里只是读模型投影，败方唯一写入仍发生在 locks.acquire 的同事务。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Header

from auth import current_user
from db import connect

router = APIRouter(prefix="/api/history", tags=["history"])

_KEY_RE = re.compile(r"^[a-z\-]+:(\d+):(\d+)$")


def _parse_key(lock_key: str):
    m = _KEY_RE.match(lock_key or "")
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


@router.get("")
def list_history(
    authorization: str | None = Header(default=None),
    limit: int = 100,
    include_contention: bool = True,
):
    current_user(authorization)
    with connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT h.*, f.key AS flag_key, e.code AS env_code
                FROM change_history h
                LEFT JOIN flags f ON f.id=h.flag_id
                LEFT JOIN environments e ON e.id=h.env_id
                ORDER BY h.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]

        contention_rows = []
        raw_marks = []
        if include_contention:
            raw_marks = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM contention_marks ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]
            flag_cache: dict[int, str | None] = {}
            env_cache: dict[int, str | None] = {}
            for m in raw_marks:
                tid = int(m["id"])
                fid, eid = _parse_key(m["lock_key"])
                flag_key = None
                env_code = None
                if fid is not None:
                    if fid not in flag_cache:
                        fr = conn.execute("SELECT key FROM flags WHERE id=?", (fid,)).fetchone()
                        flag_cache[fid] = fr["key"] if fr else None
                    flag_key = flag_cache[fid]
                if eid is not None:
                    if eid not in env_cache:
                        er = conn.execute("SELECT code FROM environments WHERE id=?", (eid,)).fetchone()
                        env_cache[eid] = er["code"] if er else None
                    env_code = env_cache[eid]
                contention_rows.append(
                    {
                        # 正偏移虚拟 id，避免与 change_history 正 id 在同表 :key 相撞；
                        # 真实票号以 mark_id / ticket 为准，可跨表联查。
                        "id": 10_000_000 + tid,
                        "mark_id": tid,
                        "ticket": f"lose-{tid}",
                        "entry_type": "contention",
                        "kind": "contention",
                        "action": "lock_lost",
                        "lock_key": m["lock_key"],
                        "loser": m["loser"],
                        "winner": m["winner"],
                        "flag_id": fid,
                        "env_id": eid,
                        "flag_key": flag_key,
                        "env_code": env_code,
                        "actor": m["loser"],
                        "detail": (
                            f"抢锁失败：{m['loser']} 抢 {m['lock_key']} 败于持锁人 "
                            f"{m['winner']}；已同事务记败方账 #{tid}，正式零增。"
                        ),
                        "created_at": m["created_at"],
                    }
                )

    items = rows + contention_rows
    items.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    items = items[:limit]
    # contention_items 给原始败方账行（id 即票号），items 给合并台账投影。
    return {"items": items, "contention_items": raw_marks}
