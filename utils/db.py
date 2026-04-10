"""
db.py — SQLite 数据库统一管理

表结构：
  users              — 用户账号（主表）
  capabilities       — 用户能力画像（每项技能的当前得分）
  training_sessions  — 训练会话记录
  session_scores     — 每次训练各维度得分（session 的从表）
  custom_scenarios   — 自定义场景（JSON 整体存储）

首次启动时自动建表，并从 data/users.json 和 data/custom_scenarios.json
做一次性数据迁移，迁移完成后 JSON 文件保留但不再使用。
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH   = Path(__file__).parent.parent / "data" / "aihr.db"
DATA_DIR  = Path(__file__).parent.parent / "data"
USERS_JSON    = DATA_DIR / "users.json"
SCENARIOS_JSON = DATA_DIR / "custom_scenarios.json"

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    username   TEXT PRIMARY KEY,
    password   TEXT NOT NULL,
    name       TEXT NOT NULL,
    department TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'learner',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS capabilities (
    username   TEXT NOT NULL,
    skill      TEXT NOT NULL,
    score      REAL NOT NULL DEFAULT 5.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (username, skill),
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS training_sessions (
    id           TEXT PRIMARY KEY,
    username     TEXT NOT NULL,
    scenario_id  TEXT NOT NULL,
    scenario_name TEXT NOT NULL,
    date         TEXT NOT NULL,
    overall_score REAL NOT NULL DEFAULT 0,
    round_count  INTEGER NOT NULL DEFAULT 0,
    report_md    TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_scores (
    session_id TEXT NOT NULL,
    skill      TEXT NOT NULL,
    score      REAL NOT NULL,
    PRIMARY KEY (session_id, skill),
    FOREIGN KEY (session_id) REFERENCES training_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS custom_scenarios (
    id         TEXT PRIMARY KEY,
    data_json  TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


# ── 连接上下文管理器 ──────────────────────────────────────────────
@contextmanager
def get_conn():
    """获取 SQLite 连接，自动提交/回滚，row_factory=Row 支持字典访问。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── 初始化 & 迁移 ─────────────────────────────────────────────────
def init_db():
    """建表 + 从 JSON 迁移（只执行一次）。"""
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
    _migrate_from_json()


def _migrate_from_json():
    """把旧 JSON 数据一次性写入 SQLite，DB 已有数据则跳过。"""
    with get_conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return   # 已迁移，跳过

        # ── 迁移用户 ────────────────────────────────────────────
        if USERS_JSON.exists():
            with open(USERS_JSON, encoding="utf-8") as f:
                users = json.load(f)

            for uname, u in users.items():
                conn.execute(
                    "INSERT OR IGNORE INTO users (username,password,name,department,role) VALUES (?,?,?,?,?)",
                    (uname, u.get("password","123456"),
                     u.get("name", uname), u.get("department",""), u.get("role","learner")),
                )
                for skill, score in u.get("capabilities", {}).items():
                    conn.execute(
                        "INSERT OR IGNORE INTO capabilities (username,skill,score) VALUES (?,?,?)",
                        (uname, skill, float(score)),
                    )
                for s in u.get("training_sessions", []):
                    conn.execute(
                        """INSERT OR IGNORE INTO training_sessions
                           (id,username,scenario_id,scenario_name,date,overall_score,round_count,report_md)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (s["id"], uname, s.get("scenario_id",""), s.get("scenario_name",""),
                         s.get("date",""), float(s.get("overall_score",0)),
                         int(s.get("round_count",0)), s.get("report_md","")),
                    )
                    for skill, score in s.get("scores", {}).items():
                        conn.execute(
                            "INSERT OR IGNORE INTO session_scores (session_id,skill,score) VALUES (?,?,?)",
                            (s["id"], skill, float(score)),
                        )

        # ── 迁移自定义场景 ───────────────────────────────────────
        if SCENARIOS_JSON.exists():
            with open(SCENARIOS_JSON, encoding="utf-8") as f:
                scenarios = json.load(f)
            for sc in scenarios:
                conn.execute(
                    "INSERT OR IGNORE INTO custom_scenarios (id,data_json) VALUES (?,?)",
                    (sc["id"], json.dumps(sc, ensure_ascii=False)),
                )


# ══════════════════════════════════════════════════════════════════
# 用户 CRUD
# ══════════════════════════════════════════════════════════════════

def db_get_all_users() -> list:
    """返回所有用户的基本信息列表（不含密码和训练数据）。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT username,name,department,role,created_at FROM users ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def db_authenticate(username: str, password: str) -> dict:
    """验证账号密码，成功返回完整 profile dict，失败返回 None。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?", (username, password)
        ).fetchone()
        if row:
            return _build_profile(conn, dict(row))
    return None


def db_get_user(username: str) -> dict:
    """按用户名获取完整 profile（含能力画像和训练历史）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        if row:
            return _build_profile(conn, dict(row))
    return None


def db_create_user(username: str, password: str, name: str,
                   department: str, role: str = "learner") -> None:
    """新建用户（username 已存在则抛出 IntegrityError）。"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username,password,name,department,role) VALUES (?,?,?,?,?)",
            (username, password, name, department, role),
        )


def db_update_user(username: str, name: str, department: str,
                   role: str, password: str = None) -> None:
    """更新用户信息，password 为 None 时不修改密码。"""
    with get_conn() as conn:
        if password:
            conn.execute(
                """UPDATE users SET name=?,department=?,role=?,password=?,
                   updated_at=datetime('now','localtime') WHERE username=?""",
                (name, department, role, password, username),
            )
        else:
            conn.execute(
                """UPDATE users SET name=?,department=?,role=?,
                   updated_at=datetime('now','localtime') WHERE username=?""",
                (name, department, role, username),
            )


def db_delete_user(username: str) -> None:
    """删除用户及其所有关联数据（CASCADE）。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE username=?", (username,))


# ══════════════════════════════════════════════════════════════════
# 训练数据写入
# ══════════════════════════════════════════════════════════════════

def db_save_training_result(username: str, result: dict) -> None:
    """
    保存训练结果：
      1. 写入 training_sessions + session_scores
      2. 用加权移动平均更新 capabilities（新 0.3 / 旧 0.7）
    """
    with get_conn() as conn:
        # 写 session
        conn.execute(
            """INSERT OR IGNORE INTO training_sessions
               (id,username,scenario_id,scenario_name,date,overall_score,round_count,report_md)
               VALUES (?,?,?,?,?,?,?,?)""",
            (result["session_id"], username,
             result["scenario_id"], result["scenario_name"],
             result["date"], float(result["overall"]),
             int(result["round_count"]), result.get("report_md","")),
        )
        for skill, score in result["scores"].items():
            conn.execute(
                "INSERT OR IGNORE INTO session_scores (session_id,skill,score) VALUES (?,?,?)",
                (result["session_id"], skill, float(score)),
            )

        # 更新能力画像（加权移动平均）
        for skill, new_score in result["scores"].items():
            row = conn.execute(
                "SELECT score FROM capabilities WHERE username=? AND skill=?",
                (username, skill),
            ).fetchone()
            if row is None:
                updated = float(new_score)
            else:
                updated = round(float(row["score"]) * 0.7 + float(new_score) * 0.3, 1)
            conn.execute(
                """INSERT INTO capabilities (username,skill,score) VALUES (?,?,?)
                   ON CONFLICT(username,skill) DO UPDATE SET score=excluded.score,
                   updated_at=datetime('now','localtime')""",
                (username, skill, updated),
            )


# ══════════════════════════════════════════════════════════════════
# 自定义场景 CRUD
# ══════════════════════════════════════════════════════════════════

def db_load_custom_scenarios() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT data_json FROM custom_scenarios ORDER BY created_at"
        ).fetchall()
        return [json.loads(r["data_json"]) for r in rows]


def db_save_custom_scenario(scenario: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO custom_scenarios (id,data_json) VALUES (?,?)
               ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json""",
            (scenario["id"], json.dumps(scenario, ensure_ascii=False)),
        )


def db_delete_custom_scenario(scenario_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM custom_scenarios WHERE id=?", (scenario_id,))


# ── 内部：把 users 行拼装成完整 profile dict ──────────────────────
def _build_profile(conn, row: dict) -> dict:
    uname = row["username"]
    caps = {
        r["skill"]: r["score"]
        for r in conn.execute(
            "SELECT skill,score FROM capabilities WHERE username=?", (uname,)
        ).fetchall()
    }
    sessions = []
    for s in conn.execute(
        "SELECT * FROM training_sessions WHERE username=? ORDER BY created_at", (uname,)
    ).fetchall():
        scores = {
            r["skill"]: r["score"]
            for r in conn.execute(
                "SELECT skill,score FROM session_scores WHERE session_id=?", (s["id"],)
            ).fetchall()
        }
        sessions.append({
            "id":            s["id"],
            "scenario_id":   s["scenario_id"],
            "scenario_name": s["scenario_name"],
            "date":          s["date"],
            "overall_score": s["overall_score"],
            "round_count":   s["round_count"],
            "report_md":     s["report_md"],
            "scores":        scores,
        })
    return {
        "username":         uname,
        "name":             row["name"],
        "department":       row["department"],
        "role":             row["role"],
        "capabilities":     caps,
        "training_sessions": sessions,
    }
