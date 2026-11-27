"""行锁与争用痕（嵌进发布/熔断主写路径）。

grayroll-bugfix-12 口径（甲路径，当班封死）：
- check-and-set 在进程内互斥段完成并立即提交，杜绝两路并发同时判空「双成」；
- 抢败必须在同一事务内写 contention_marks（败方账/争用痕），提交后抛 409；
- 败方只记争用痕，不写正式区、不写影子草案（争用不进取舍段）；
- 败方票号 (= contention_marks.id) 同时进异常属性 / 响应头 / 返回句体，
  供「返回句 ↔ 败方账 ↔ 总览/历史台账」同票跨表联查。
"""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from auth import current_user, require_writer
from db import connect

router = APIRouter(prefix="/api/locks", tags=["locks"])
TTL = 20.0

# 进程级 check-and-set 互斥段：TestClient/uvicorn 单 worker 下兜住并发双请。
# 数据库侧行锁判定仍以 row_locks 已提交行为准，跨连接可见。
_acquire_guard = threading.Lock()

# 与初始骨架参考实现保持逐字一致的抢败句，禁止改回成功句。
LOCK_LOST_DETAIL = "发布锁争用，请稍后重试"


class LockContention(HTTPException):
    """抢锁失败：已落败方账，票号与 contention_marks.id 同票。"""

    def __init__(self, *, mark_id: int, lock_key: str, loser: str, winner: str):
        self.mark_id = mark_id
        self.ticket = f"lose-{mark_id}"
        self.lock_key = lock_key
        self.loser = loser
        self.winner = winner
        headers = {
            "X-Contention-Id": str(mark_id),
            "X-Lose-Ticket": self.ticket,
        }
        super().__init__(status_code=409, detail=LOCK_LOST_DETAIL, headers=headers)

    def body(self) -> dict:
        """富返回句：detail 仍为参考实现逐字抢败句，另带同票字段。"""
        return {
            "ok": False,
            "success": False,
            "won": False,
            "mode": "lock_lost",
            "code": "lock_contention",
            "detail": LOCK_LOST_DETAIL,
            "message": (
                f"抢锁失败：{self.loser} 抢 {self.lock_key} 败于持锁人 {self.winner}；"
                f"已同事务记败方账 #{self.mark_id}（票 {self.ticket}），正式账零增。"
            ),
            "sentence": LOCK_LOST_DETAIL,
            "ticket": self.ticket,
            "mark_id": self.mark_id,
            "contention_id": self.mark_id,
            "lose_ticket": self.ticket,
            "lock_key": self.lock_key,
            "loser": self.loser,
            "winner": self.winner,
        }

    def to_response(self):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content=self.body(), headers=self.headers)


# 命名别名，便于不同测试/调用方按习惯捕获。
LockLost = LockContention
ContentionError = LockContention


def acquire(conn, key: str, holder: str) -> None:
    """尝试获取行锁；抢败则同事务写败方账并抛 :class:`LockContention` (409)。

    成功时把持锁行立即提交，保证并发后来者在互斥段内 SELECT 即可见已持锁，
    check-and-set 不再有 TOCTOU 双成窗口。
    """
    now = time.time()
    with _acquire_guard:
        row = conn.execute("SELECT * FROM row_locks WHERE lock_key=?", (key,)).fetchone()
        if row and row["expires_at"] > now and row["holder"] != holder:
            cur = conn.execute(
                "INSERT INTO contention_marks(lock_key, loser, winner, created_at) "
                "VALUES(?,?,?,?)",
                (key, holder, row["holder"], now),
            )
            mark_id = int(cur.lastrowid)
            # 败方账与抢败判定同事务封口：先提交账，再把同票异常抛给返回句。
            conn.commit()
            raise LockContention(mark_id=mark_id, lock_key=key, loser=holder, winner=row["holder"])
        conn.execute(
            "INSERT INTO row_locks(lock_key, holder, expires_at) VALUES(?,?,?) "
            "ON CONFLICT(lock_key) DO UPDATE SET holder=excluded.holder, expires_at=excluded.expires_at",
            (key, holder, now + TTL),
        )
        # 立即公开持锁事实，消除并发 SELECT-then-UPSERT 的双成窗口。
        conn.commit()


def release(conn, key: str, holder: str) -> None:
    conn.execute("DELETE FROM row_locks WHERE lock_key=? AND holder=?", (key, holder))


class ReviewIn(BaseModel):
    note: str = ""


@router.get("/contention")
def list_contention(authorization: str | None = Header(default=None), limit: int = 40):
    current_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM contention_marks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/contention/review")
def review_contention(body: ReviewIn, authorization: str | None = Header(default=None)):
    """显式复核封账：through_id 盖住当前最新败方账后，总览才允许翻真绿。"""
    user = current_user(authorization)
    require_writer(user)
    note = (body.note or "").strip()[:200]
    with connect() as conn:
        latest = conn.execute("SELECT COALESCE(MAX(id), 0) m FROM contention_marks").fetchone()["m"]
        total = conn.execute("SELECT COUNT(*) c FROM contention_marks").fetchone()["c"]
        conn.execute(
            "INSERT INTO contention_reviews(through_id, marks_at_review, note, reviewed_by, created_at) "
            "VALUES(?,?,?,?,?)",
            (int(latest), int(total), note, user["username"], time.time()),
        )
        conn.commit()
    return {
        "ok": True,
        "reviewed_through": int(latest),
        "through_id": int(latest),
        "marks_at_review": int(total),
        "reviewed_by": user["username"],
    }
