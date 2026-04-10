"""
mock_data.py — 高拟真 B 端测试数据（pandas DataFrame）

所有数据使用固定随机种子生成，保证每次启动结果一致。
供四个视图函数调用，不依赖任何其他业务模块。
"""

import random
from datetime import datetime, timedelta

import pandas as pd

# 固定种子，保证数据稳定
_R = random.Random(2026)

# ── 常量定义 ──────────────────────────────────────────────────────
DEPARTMENTS = ["HR部门", "销售部门", "技术部门", "客服部门", "财务部门", "运营部门"]

DEPT_SKILLS = {
    "HR部门":   ["沟通共情", "问题处理", "政策掌握"],
    "销售部门": ["需求挖掘", "方案匹配", "价值传递"],
    "技术部门": ["问题定位", "逻辑排查", "解决方案"],
    "客服部门": ["情绪安抚", "问题解决", "服务规范"],
    "财务部门": ["数据分析", "合规意识", "报告能力"],
    "运营部门": ["数据驱动", "用户理解", "执行效率"],
}

DEPT_SKILL_WEIGHTS = {
    "HR部门":   [40, 30, 30],
    "销售部门": [35, 35, 30],
    "技术部门": [40, 30, 30],
    "客服部门": [40, 30, 30],
    "财务部门": [35, 35, 30],
    "运营部门": [33, 34, 33],
}

SCENARIO_NAMES = [
    "候选人薪酬谈判模拟",
    "客户价格谈判实战",
    "MySQL 性能故障排查",
    "VIP 客户危机处理",
    "Redis 缓存雪崩排查",
    "大客户续约攻防战",
    "核心员工离职挽留",
    "跨部门资源冲突调解",
]

_USERS = {
    dept: [
        f"{dept[:2]}_{chr(65+i)}"
        for i in range(_R.randint(7, 14))
    ]
    for dept in DEPARTMENTS
}


# ── 全局统计 ──────────────────────────────────────────────────────
def get_global_stats() -> dict:
    """首屏四格 metric 数据。"""
    total_users   = sum(len(v) for v in _USERS.values())
    today_active  = int(total_users * _R.uniform(0.15, 0.35))
    total_sessions = _R.randint(340, 520)
    avg_score     = round(_R.uniform(6.8, 7.6), 1)
    return {
        "total_users":    total_users,
        "today_active":   today_active,
        "total_sessions": total_sessions,
        "avg_score":      avg_score,
    }


# ── 部门概览表 ────────────────────────────────────────────────────
def get_dept_overview() -> pd.DataFrame:
    """各部门训练完成率、平均得分等。"""
    _r = random.Random(2026)
    rows = []
    for dept in DEPARTMENTS:
        total     = len(_USERS[dept])
        completed = _r.randint(int(total * 0.45), total)
        avg       = round(_r.uniform(6.2, 8.4), 1)
        sessions  = _r.randint(completed, completed * 3)
        last_day  = (datetime.now() - timedelta(days=_r.randint(0, 5))).strftime("%Y-%m-%d")
        rows.append({
            "部门":       dept,
            "总人数":     total,
            "已参训":     completed,
            "完成率":     f"{int(completed / total * 100)}%",
            "总场次":     sessions,
            "平均得分":   avg,
            "最近活跃":   last_day,
        })
    return pd.DataFrame(rows)


def get_dept_stats(dept: str) -> dict:
    """单部门 metric 数据。"""
    df = get_dept_overview()
    row = df[df["部门"] == dept]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {
        "total":      int(r["总人数"]),
        "completed":  int(r["已参训"]),
        "rate":       r["完成率"],
        "sessions":   int(r["总场次"]),
        "avg_score":  float(r["平均得分"]),
    }


# ── 部门能力短板 ──────────────────────────────────────────────────
def get_dept_capability_gap(dept: str) -> pd.DataFrame:
    """部门内各能力维度的平均得分与全公司均值对比。"""
    _r = random.Random(hash(dept) % 10000)
    skills = DEPT_SKILLS.get(dept, [])
    rows = []
    for skill in skills:
        dept_avg    = round(_r.uniform(5.5, 8.0), 1)
        company_avg = round(_r.uniform(6.0, 7.5), 1)
        gap         = round(dept_avg - company_avg, 1)
        rows.append({
            "能力维度":   skill,
            "部门均分":   dept_avg,
            "全司均分":   company_avg,
            "差距":       f"+{gap}" if gap >= 0 else str(gap),
            "状态":       "领先" if gap >= 0 else "落后",
        })
    return pd.DataFrame(rows)


def get_company_capability_gap() -> pd.DataFrame:
    """全公司各部门各维度能力热力数据（宽表）。"""
    _r = random.Random(999)
    all_skills = []
    for skills in DEPT_SKILLS.values():
        all_skills.extend(skills)
    all_skills = list(dict.fromkeys(all_skills))

    rows = []
    for dept in DEPARTMENTS:
        row = {"部门": dept}
        dept_skills = DEPT_SKILLS[dept]
        for skill in all_skills:
            if skill in dept_skills:
                row[skill] = round(_r.uniform(5.5, 8.5), 1)
            else:
                row[skill] = "—"
        rows.append(row)
    return pd.DataFrame(rows)


# ── 热门场景排行 ──────────────────────────────────────────────────
def get_top_scenarios(n: int = 5) -> pd.DataFrame:
    _r = random.Random(77)
    rows = []
    for name in SCENARIO_NAMES[:n]:
        rows.append({
            "场景名称":  name,
            "实训次数":  _r.randint(28, 120),
            "平均得分":  round(_r.uniform(6.5, 8.2), 1),
            "覆盖部门数": _r.randint(1, 4),
            "本周新增":  _r.randint(3, 18),
        })
    rows.sort(key=lambda x: x["实训次数"], reverse=True)
    return pd.DataFrame(rows)


# ── 部门用户实训明细 ──────────────────────────────────────────────
def get_dept_user_detail(dept: str) -> pd.DataFrame:
    """部门内所有用户的实训进度明细。"""
    _r = random.Random(hash(dept) % 9999)
    users = _USERS.get(dept, [])
    rows = []
    names = ["张伟", "李娜", "王芳", "刘洋", "陈静", "赵磊", "孙丽",
             "周强", "吴敏", "郑超", "王鑫", "李欢", "张楠", "刘畅"]
    for i, uid in enumerate(users):
        completed  = _r.randint(0, 12)
        avg_score  = round(_r.uniform(5.5, 8.8), 1) if completed > 0 else None
        last_train = (datetime.now() - timedelta(days=_r.randint(0, 30))).strftime("%Y-%m-%d") if completed else "—"
        rows.append({
            "用户ID":    uid,
            "姓名":      names[i % len(names)],
            "已完成场次": completed,
            "平均得分":  avg_score if avg_score else "—",
            "最近实训":  last_train,
            "状态":      "活跃" if completed > 3 else ("入门" if completed > 0 else "未开始"),
        })
    return pd.DataFrame(rows)


# ── 全局用户实训总表 ──────────────────────────────────────────────
def get_global_user_table() -> pd.DataFrame:
    """跨部门所有用户实训数据，供 HR 全局查询。"""
    _r = random.Random(555)
    names = ["张伟", "李娜", "王芳", "刘洋", "陈静", "赵磊", "孙丽",
             "周强", "吴敏", "郑超", "王鑫", "李欢", "张楠", "刘畅",
             "黄宇", "林峰", "马明", "杨晓", "胡丽", "朱强"]
    rows = []
    name_idx = 0
    for dept in DEPARTMENTS:
        for uid in _USERS[dept]:
            completed = _r.randint(0, 15)
            avg_score = round(_r.uniform(5.5, 9.0), 1) if completed > 0 else None
            last_train = (datetime.now() - timedelta(days=_r.randint(0, 60))).strftime("%Y-%m-%d") if completed else "—"
            rows.append({
                "部门":      dept,
                "姓名":      names[name_idx % len(names)],
                "完成场次":  completed,
                "平均得分":  avg_score if avg_score else "—",
                "最近实训":  last_train,
                "梯队标签":  (
                    "高潜人才" if (avg_score or 0) >= 8.0 and completed >= 8 else
                    "稳健成长" if (avg_score or 0) >= 7.0 and completed >= 4 else
                    "需重点关注" if completed == 0 else "成长中"
                ),
            })
            name_idx += 1
    return pd.DataFrame(rows)


# ── Token / API 监控数据 ──────────────────────────────────────────
def get_token_stats() -> dict:
    """本月 Token 消耗摘要。"""
    _r = random.Random(123)
    total_tokens  = _r.randint(1_800_000, 3_200_000)
    today_tokens  = _r.randint(8_000, 25_000)
    avg_per_sess  = _r.randint(2_400, 4_200)
    cost_cny      = round(total_tokens / 1_000_000 * 12.0, 2)  # 假设 12元/M tokens
    return {
        "total_tokens":  total_tokens,
        "today_tokens":  today_tokens,
        "avg_per_session": avg_per_sess,
        "cost_cny":      cost_cny,
    }


def get_dept_token_usage() -> pd.DataFrame:
    """各部门算力资源占用。"""
    _r = random.Random(456)
    rows = []
    totals = [_r.randint(120_000, 680_000) for _ in DEPARTMENTS]
    grand  = sum(totals)
    for i, dept in enumerate(DEPARTMENTS):
        rows.append({
            "部门":      dept,
            "消耗 Token": f"{totals[i]:,}",
            "占比":       f"{totals[i]/grand*100:.1f}%",
            "实训场次":   _r.randint(20, 90),
            "人均 Token": f"{totals[i]//len(_USERS[dept]):,}",
        })
    rows.sort(key=lambda x: -int(x["消耗 Token"].replace(",", "")))
    return pd.DataFrame(rows)


def get_api_health() -> pd.DataFrame:
    """API 接口健康度。"""
    _r = random.Random(789)
    apis = [
        ("角色 Agent（对话）",    _r.uniform(98.5, 99.9), _r.randint(320, 680)),
        ("教练 Agent（反馈）",    _r.uniform(97.8, 99.5), _r.randint(280, 560)),
        ("追踪 Agent（报告）",    _r.uniform(97.0, 99.2), _r.randint(800, 1800)),
        ("场景生成 Agent",         _r.uniform(96.5, 99.0), _r.randint(1200, 2800)),
        ("能力画像更新接口",       _r.uniform(99.0, 99.9), _r.randint(50, 120)),
    ]
    rows = []
    for name, avail, latency in apis:
        rows.append({
            "接口名称":    name,
            "可用率":      f"{avail:.2f}%",
            "P99 延迟(ms)": latency,
            "状态":        "正常" if avail >= 98.0 else "观察中",
            "今日调用次数": _r.randint(80, 450),
        })
    return pd.DataFrame(rows)


# ── 组织架构：部门主管分配 ───────────────────────────────────────
def get_dept_manager_table() -> pd.DataFrame:
    """部门与主管账号的映射关系。"""
    return pd.DataFrame([
        {"部门": "HR部门",   "主管账号": "alice",  "姓名": "Alice Wang",  "成员数": len(_USERS["HR部门"])},
        {"部门": "销售部门", "主管账号": "—",      "姓名": "（未分配）",   "成员数": len(_USERS["销售部门"])},
        {"部门": "技术部门", "主管账号": "carol",  "姓名": "Carol Li",    "成员数": len(_USERS["技术部门"])},
        {"部门": "客服部门", "主管账号": "—",      "姓名": "（未分配）",   "成员数": len(_USERS["客服部门"])},
        {"部门": "财务部门", "主管账号": "—",      "姓名": "（未分配）",   "成员数": len(_USERS["财务部门"])},
        {"部门": "运营部门", "主管账号": "—",      "姓名": "（未分配）",   "成员数": len(_USERS["运营部门"])},
    ])


# ── 能力模型配置数据 ──────────────────────────────────────────────
def get_skill_model_config() -> pd.DataFrame:
    """各部门能力维度及权重（可被 st.data_editor 编辑）。"""
    rows = []
    for dept in DEPARTMENTS:
        skills  = DEPT_SKILLS[dept]
        weights = DEPT_SKILL_WEIGHTS[dept]
        for skill, weight in zip(skills, weights):
            rows.append({
                "部门":     dept,
                "能力维度": skill,
                "权重(%)":  weight,
                "状态":     "启用",
            })
    return pd.DataFrame(rows)
