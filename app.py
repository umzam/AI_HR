"""
app.py — AI 虚拟实训平台主入口（Streamlit 前端）

视图路由（侧边栏身份切换）：
  员工虚拟实训端      — view_employee()
  普通部门主管端      — view_dept_manager()
  HR全局培训管理端    — view_hr_admin()
  系统超管端          — view_super_admin()

全页面路由（训练室不嵌入 Tab，保持全页体验）：
  training      — page_training()
  report        — page_report()
  history_report— page_history_report()
"""

import os
import re
import uuid
from datetime import datetime
from dotenv import load_dotenv

import plotly.graph_objects as go
import streamlit as st

load_dotenv()

# 启动时初始化数据库（建表 + JSON 迁移，幂等）
from utils.db import init_db
init_db()

from config import BUILTIN_SCENARIOS, DEPARTMENT_SCENARIO_MAP
from agents.training_session import TrainingSession
from utils.profile_manager import (
    authenticate,
    get_user_profile,
    save_training_result,
    load_custom_scenarios,
    save_custom_scenario,
    delete_custom_scenario,
    build_custom_scenario_config,
)
from utils.db import (
    db_get_all_users,
    db_create_user,
    db_update_user,
    db_delete_user,
)

# ── 全局页面配置 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 虚拟实训平台",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.scenario-card {
    background: linear-gradient(135deg,#1E293B 0%,#0F172A 100%);
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 18px;
    margin-bottom: 10px;
    transition: border-color .2s;
}
.scenario-card:hover { border-color: #4F46E5; }
.page-title   { font-size:1.7em; font-weight:700; margin-bottom:2px; }
.page-subtitle{ color:#94A3B8; margin-bottom:20px; }
</style>
""", unsafe_allow_html=True)


# ── Session State 初始化 ──────────────────────────────────────────
def init_session():
    defaults = {
        "authenticated":          False,
        "user":                   None,
        "page":                   "login",
        "platform_view":          "员工虚拟实训端",
        "training_session":       None,
        "chat_history":           [],
        "coach_feedbacks":        [],
        "current_scenario":       None,
        "training_finished":      False,
        "training_report":        None,
        "input_mode":             "text",
        "viewing_history_report": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


# ── 工具函数 ─────────────────────────────────────────────────────
def get_api_key() -> str:
    return os.getenv("ARK_API_KEY", "")

def get_all_scenarios() -> dict:
    all_s = dict(BUILTIN_SCENARIOS)
    for cs in load_custom_scenarios():
        all_s[cs["id"]] = cs
    return all_s

def get_recommended_scenarios(user: dict) -> list:
    all_s = get_all_scenarios()
    dept = user.get("department", "")
    ids = list(DEPARTMENT_SCENARIO_MAP.get(dept, list(BUILTIN_SCENARIOS.keys())))
    for cs in load_custom_scenarios():
        if cs.get("department") == dept or user.get("role") == "admin":
            if cs["id"] not in ids:
                ids.append(cs["id"])
    return [all_s[sid] for sid in ids if sid in all_s]

def nav_to(page: str, **kwargs):
    st.session_state.page = page
    for k, v in kwargs.items():
        st.session_state[k] = v

def start_training(scenario: dict):
    api_key = get_api_key()
    st.session_state.training_session = TrainingSession(scenario, api_key)
    st.session_state.current_scenario = scenario
    st.session_state.chat_history = []
    st.session_state.coach_feedbacks = []
    st.session_state.training_finished = False
    st.session_state.training_report = None
    st.session_state.input_mode = "code" if scenario.get("supports_code") else "text"
    nav_to("training")

def create_radar_chart(capabilities: dict):
    if not capabilities:
        return None
    categories = list(capabilities.keys())
    values = list(capabilities.values())
    cats = categories + [categories[0]]
    vals = values + [values[0]]
    fig = go.Figure(go.Scatterpolar(
        r=vals, theta=cats, fill="toself",
        fillcolor="rgba(79,70,229,0.2)",
        line=dict(color="#4F46E5", width=2),
        marker=dict(size=6, color="#818CF8"),
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 10], tickfont=dict(size=10), gridcolor="#334155"),
            angularaxis=dict(tickfont=dict(size=11), gridcolor="#334155"),
            bgcolor="#0F172A",
        ),
        paper_bgcolor="#0F172A", plot_bgcolor="#0F172A",
        showlegend=False, margin=dict(l=40,r=40,t=30,b=30), height=340,
    )
    return fig

def clean_report(md: str) -> str:
    """去掉报告末尾的 JSON 代码块，只保留可读部分。"""
    return re.sub(r"```json.*?```", "", md, flags=re.DOTALL).strip()


# ══════════════════════════════════════════════════════════════════
# 侧边栏
# ══════════════════════════════════════════════════════════════════
def render_sidebar():
    if not st.session_state.authenticated:
        return
    user = st.session_state.user
    with st.sidebar:
        # ── 顶部：身份视图切换（核心 RBAC 入口）────────────────
        VIEWS = [
            "员工虚拟实训端",
            "普通部门主管端",
            "HR全局培训管理端",
            "系统超管端",
        ]
        st.selectbox(
            "当前视图",
            VIEWS,
            key="platform_view",
            label_visibility="collapsed",
        )
        st.divider()

        # ── 登录用户信息 ─────────────────────────────────────────
        st.markdown(f"**{user['name']}**")
        st.caption(f"{user['department']}  ·  {user['role'].upper()}")
        st.divider()

        # ── 实训进行中快捷入口 ───────────────────────────────────
        if st.session_state.training_session and not st.session_state.training_finished:
            sc = st.session_state.current_scenario
            if sc:
                st.caption("实训进行中")
                st.write(f"**{sc['name']}**")
                st.write(f"已对话 {st.session_state.training_session.round_count} 轮")
                if st.button("返回实训室", use_container_width=True):
                    nav_to("training")
            st.divider()

        if st.button("退出登录", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            init_session()
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# 页面：登录
# ══════════════════════════════════════════════════════════════════
def page_login():
    _, col_m, _ = st.columns([1, 2, 1])
    with col_m:
        st.markdown("## AI 虚拟实训平台")
        st.markdown("##### 多部门 · 多 Agent · 实时教练")
        st.divider()

        with st.form("login_form"):
            username = st.text_input("用户名", placeholder="alice / bob / carol / admin")
            password = st.text_input("密码", type="password", placeholder="用户名 + 3位数字，如 alice123")
            submitted = st.form_submit_button("登录", use_container_width=True, type="primary")

        if submitted:
            user = authenticate(username.strip(), password.strip())
            if user:
                st.session_state.authenticated = True
                st.session_state.user = user
                nav_to("home")
                st.rerun()
            else:
                st.error("用户名或密码错误")

        st.divider()
        st.caption("**Demo 账号**")
        for acc, desc in {
            "alice / alice123": "HR部门 · 管理者",
            "bob / bob123":     "销售部门 · 学员",
            "carol / carol123": "技术部门 · 学员",
            "admin / admin123": "管理层 · 超级管理员",
        }.items():
            st.caption(f"　`{acc}` — {desc}")

        st.divider()
        if get_api_key():
            model = os.getenv("ARK_MODEL", "未配置")
            st.success(f"火山引擎 API 已就绪 | 模型：{model}")
        else:
            st.info("Mock 演示模式（预设剧本，无需 API Key）")


# ══════════════════════════════════════════════════════════════════
# 页面：首页 Dashboard
# ══════════════════════════════════════════════════════════════════
def page_home():
    user = st.session_state.user
    profile = get_user_profile(user["username"])
    if not profile:
        st.error("用户数据加载失败")
        return

    st.markdown(f'<div class="page-title">欢迎回来，{user["name"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{user["department"]}</div>', unsafe_allow_html=True)

    # 能力画像 + 统计
    col_radar, col_stats = st.columns([3, 2])
    capabilities = profile.get("capabilities", {})
    sessions = profile.get("training_sessions", [])

    with col_radar:
        st.subheader("能力画像")
        if capabilities:
            fig = create_radar_chart(capabilities)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("完成第一次训练后，能力画像将在这里显示")

    with col_stats:
        st.subheader("训练统计")
        total = len(sessions)
        avg = round(sum(s.get("overall_score", 0) for s in sessions) / total, 1) if total else 0
        m1, m2 = st.columns(2)
        m1.metric("累计训练次数", total)
        m2.metric("平均综合得分", f"{avg}/10" if total else "—")
        st.caption(f"最近训练：{sessions[-1]['date'] if sessions else '暂无'}")
        st.divider()
        if capabilities:
            sorted_caps = sorted(capabilities.items(), key=lambda x: x[1], reverse=True)
            best, worst = sorted_caps[0], sorted_caps[-1]
            st.success(f"最强维度：**{best[0]}**  {best[1]}/10")
            st.warning(f"提升空间：**{worst[0]}**  {worst[1]}/10")

    st.divider()

    # 推荐场景卡片
    st.subheader("推荐训练场景")
    scenarios = get_recommended_scenarios(user)
    if not scenarios:
        st.info("暂无推荐场景，请联系管理员添加")
        return

    for i in range(0, len(scenarios), 3):
        cols = st.columns(3)
        for j, sc in enumerate(scenarios[i:i+3]):
            with cols[j]:
                rule_scores = " · ".join(
                    f"{r}: {capabilities.get(r, '—')}"
                    for r in sc["evaluation_rules"]
                )
                st.markdown(f"""
<div class="scenario-card">
    <div style="font-weight:700;font-size:1.05em;margin-bottom:4px">{sc['name']}</div>
    <div style="color:#94A3B8;font-size:0.82em">{sc['department']} · {sc.get('difficulty','中级')} · {sc['estimated_time']}</div>
    <div style="color:#64748B;font-size:0.8em;margin-top:6px">{sc['description'][:60]}...</div>
    <div style="font-size:0.76em;color:#818CF8;margin-top:8px">{rule_scores}</div>
</div>""", unsafe_allow_html=True)
                if st.button("开始训练", key=f"home_start_{sc['id']}", use_container_width=True, type="primary"):
                    start_training(sc)
                    st.rerun()

    # admin 视角：所有场景列表
    if user["role"] == "admin":
        st.divider()
        st.subheader("所有场景（管理员视角）")
        for sid, sc in get_all_scenarios().items():
            ca, cb, cc = st.columns([3, 1, 1])
            ca.write(f"**{sc['name']}** — {sc['department']}")
            cb.caption(sc.get("difficulty", "—"))
            if cc.button("训练", key=f"admin_start_{sid}"):
                start_training(sc)
                st.rerun()


# ══════════════════════════════════════════════════════════════════
# 页面：场景选择（learner 专属）
# ══════════════════════════════════════════════════════════════════
def page_scene_select():
    user = st.session_state.user
    profile = get_user_profile(user["username"])
    capabilities = profile.get("capabilities", {}) if profile else {}

    st.markdown('<div class="page-title">场景选择</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{user["department"]} · 选择一个场景开始本次训练</div>', unsafe_allow_html=True)

    scenarios = get_recommended_scenarios(user)
    if not scenarios:
        st.info("暂无可用场景，请联系管理员创建")
        return

    for sc in scenarios:
        with st.container():
            left, right = st.columns([4, 1])
            with left:
                st.markdown(f"#### {sc['name']}")
                st.caption(f"{sc['department']} · {sc.get('difficulty','中级')} · 预计 {sc['estimated_time']}")
                st.write(sc["description"])

                # 各维度当前分数
                score_cols = st.columns(len(sc["evaluation_rules"]))
                for idx, rule in enumerate(sc["evaluation_rules"]):
                    score = capabilities.get(rule, None)
                    score_cols[idx].metric(rule, f"{score}/10" if score else "未测")

            with right:
                st.write("")
                st.write("")
                if st.button("开始训练", key=f"sel_{sc['id']}", use_container_width=True, type="primary"):
                    start_training(sc)
                    st.rerun()

            st.divider()


# ══════════════════════════════════════════════════════════════════
# 页面：训练室
# ══════════════════════════════════════════════════════════════════
def page_training():
    sc = st.session_state.current_scenario
    session: TrainingSession = st.session_state.training_session

    if not sc or not session:
        st.warning("训练会话未初始化，请从首页选择场景开始")
        if st.button("回到首页"):
            nav_to("home"); st.rerun()
        return

    # 顶部状态栏
    h1, h2, h3, h4 = st.columns([3, 1, 1, 1])
    h1.markdown(f"### {sc['name']}")
    h2.metric("当前轮次", session.round_count)
    h3.metric("难度", sc.get("difficulty", "—"))
    if h4.button("结束训练", type="secondary"):
        _finish_training(); return

    if session.is_mock:
        st.info("Mock 演示模式 — 使用预设剧本展示完整训练流程。配置 ARK_API_KEY 后重启即切换至真实 AI。")

    st.divider()

    # 两栏：聊天 | 教练反馈
    chat_col, coach_col = st.columns([3, 2])

    with chat_col:
        st.markdown(f"**角色：{sc['role_name']}**")

        if not st.session_state.chat_history:
            with st.chat_message("assistant"):
                st.markdown(_get_opening_line(sc))

        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            else:
                with st.chat_message("assistant"):
                    if sc.get("supports_code") and _looks_like_command(msg["content"]):
                        st.code(msg["content"], language="sql")
                    else:
                        st.markdown(msg["content"])

        st.markdown("---")

        if sc.get("supports_code"):
            mode_c, _ = st.columns([1, 3])
            new_mode = mode_c.radio(
                "输入模式", ["text", "code"],
                format_func=lambda x: "文字" if x == "text" else "命令行",
                horizontal=True,
                index=0 if st.session_state.input_mode == "text" else 1,
                label_visibility="collapsed",
            )
            st.session_state.input_mode = new_mode

        if st.session_state.input_mode == "code":
            user_input = st.text_area(
                "输入 SQL / 命令",
                placeholder="SHOW PROCESSLIST;\nEXPLAIN SELECT ...;",
                height=100, key="code_input",
            )
            if st.button("执行", type="primary") and user_input.strip():
                _handle_user_input(user_input.strip())
        else:
            user_input = st.chat_input("输入你的回应...")
            if user_input:
                _handle_user_input(user_input)

    with coach_col:
        st.markdown("**教练实时反馈**")
        # 只显示评估维度名（自定义场景维度可能很长，截断显示）
        rule_display = " / ".join(r[:8] for r in sc["evaluation_rules"])
        st.caption(f"评估维度：{rule_display}")

        if not st.session_state.coach_feedbacks:
            st.info("开始对话后，教练将在这里给出实时点评")
        else:
            feedbacks = st.session_state.coach_feedbacks
            for fb in reversed(feedbacks):
                is_latest = (fb == feedbacks[-1])
                label = f"第 {fb['round']} 轮反馈" + ("  ← 最新" if is_latest else "")
                with st.expander(label, expanded=is_latest):
                    st.markdown(fb["content"])

        st.divider()
        st.caption("每轮对话后教练自动点评")


def _get_opening_line(sc: dict) -> str:
    openings = {
        "hr_salary_negotiation":    "**场景开始**\n\n你是一名 HR，正在接待前来谈薪的候选人李明。请先打个招呼并引导进入话题。",
        "sales_price_negotiation":  "**场景开始**\n\n你是一名销售，张总已经坐在你对面。请开始你的开场白。",
        "tech_mysql_troubleshoot":  "**场景开始**\n\n线上系统告警：订单系统响应时间异常，P0 级故障！请开始你的排查操作。",
    }
    return openings.get(sc["id"], f"**场景开始**\n\n{sc['description']}\n\n请开始与角色互动。")

def _looks_like_command(text: str) -> bool:
    kws = ["SELECT", "SHOW", "EXPLAIN", "DESCRIBE", "SET ", "ALTER", "CREATE", "DROP", "mysql", "ERROR"]
    return any(k in text.upper() for k in kws)

def _handle_user_input(user_input: str):
    session: TrainingSession = st.session_state.training_session
    st.session_state.chat_history.append({
        "role": "user", "content": user_input,
        "time": datetime.now().strftime("%H:%M"),
    })
    with st.spinner("角色正在回应中..."):
        try:
            result = session.process_user_turn(user_input)
        except Exception as e:
            st.error(f"Agent 调用失败: {e}")
            return
    st.session_state.chat_history.append({
        "role": "role", "content": result["role_response"],
        "time": datetime.now().strftime("%H:%M"),
    })
    st.session_state.coach_feedbacks.append({
        "round": result["round"], "content": result["coach_feedback"],
    })
    st.rerun()

def _finish_training():
    session: TrainingSession = st.session_state.training_session
    if session.round_count == 0:
        st.warning("至少完成一轮对话后才能结束训练")
        return
    with st.spinner("能力追踪 Agent 正在生成训练报告..."):
        try:
            report = session.generate_report()
        except Exception as e:
            st.error(f"报告生成失败: {e}")
            return
    user = st.session_state.user
    save_training_result(user["username"], report)
    updated = get_user_profile(user["username"])
    if updated:
        st.session_state.user = {**user, **{k: v for k, v in updated.items() if k != "password"}}
    st.session_state.training_report = report
    st.session_state.training_finished = True
    nav_to("report")
    st.rerun()


# ══════════════════════════════════════════════════════════════════
# 页面：当次训练报告
# ══════════════════════════════════════════════════════════════════
def page_report():
    report = st.session_state.training_report
    if not report:
        st.warning("暂无报告，请先完成一次训练")
        if st.button("回到首页"): nav_to("home"); st.rerun()
        return

    _render_report(report)

    st.divider()
    b1, b2, b3 = st.columns(3)
    sc = st.session_state.current_scenario
    if b1.button("再次训练同一场景", use_container_width=True):
        if sc: start_training(sc); st.rerun()
    if b2.button("回到首页", use_container_width=True, type="primary"):
        nav_to("home"); st.rerun()
    if b3.button("查看训练历史", use_container_width=True):
        nav_to("history"); st.rerun()


# ══════════════════════════════════════════════════════════════════
# 页面：场景管理（manager / admin）
# ══════════════════════════════════════════════════════════════════
def page_scenarios():
    from agents.scenario_architect import generate_scenario, JOBS

    user = st.session_state.user
    if user["role"] not in ("manager", "admin"):
        st.warning("仅部门管理者和管理员可访问此页面")
        return

    st.markdown('<div class="page-title">场景管理</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">创建、管理训练场景 — 手动填写或 AI 一键生成场景方案</div>', unsafe_allow_html=True)

    tab_create, tab_existing = st.tabs(["创建新场景", "已有场景"])

    # ── session_state 中的表单字段 key（保证 AI 填充后 widget 自动更新）
    SK = {
        "dept":  "sc_form_dept",
        "name":  "sc_form_name",
        "desc":  "sc_form_desc",
        "role":  "sc_form_role",
        "rules": "sc_form_rules",
    }
    # 首次进入初始化
    for k, sk in SK.items():
        if sk not in st.session_state:
            st.session_state[sk] = "" if k != "dept" else "HR部门"

    DEPARTMENTS = ["HR部门", "销售部门", "技术部门", "客服部门", "财务部门", "运营部门", "其他"]

    with tab_create:
        # ── 第一行：所属部门 + 岗位 + AI生成按钮 ──────────────────
        col_dept, col_job, col_btn = st.columns([2, 2, 1])

        with col_dept:
            dept_idx = DEPARTMENTS.index(st.session_state[SK["dept"]]) \
                       if st.session_state[SK["dept"]] in DEPARTMENTS else 0
            st.selectbox(
                "所属部门 *",
                DEPARTMENTS,
                index=dept_idx,
                key=SK["dept"],
            )

        with col_job:
            # 岗位选择不存入场景配置，仅作为 AI 生成的输入参数
            if "sc_form_job" not in st.session_state:
                st.session_state["sc_form_job"] = JOBS[0]
            st.selectbox("选择岗位（用于 AI 生成）", JOBS, key="sc_form_job")

        with col_btn:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)  # 对齐
            ai_clicked = st.button("AI 一键生成方案", type="primary", use_container_width=True)

        # ── AI 生成逻辑 ────────────────────────────────────────────
        if ai_clicked:
            job   = st.session_state["sc_form_job"]
            dept  = st.session_state[SK["dept"]]
            with st.spinner(f"Scenario Architect Agent 正在为「{job}」设计场景方案..."):
                result = generate_scenario(job, dept)

            if result.get("error"):
                st.warning(result["error"])

            if result.get("_is_mock"):
                st.info("Mock 演示模式 — 已填入预设示例，配置 ARK_API_KEY 后重启即可使用真实 AI 生成。")

            # 写入 session_state，触发 widget 自动更新
            if result.get("name"):
                st.session_state[SK["name"]]  = result["name"]
            if result.get("description"):
                st.session_state[SK["desc"]]  = result["description"]
            if result.get("role_background"):
                st.session_state[SK["role"]]  = result["role_background"]
            if result.get("eval_rules"):
                st.session_state[SK["rules"]] = result["eval_rules"]

            st.success("AI 已生成场景方案，可在下方直接编辑后保存。")
            st.rerun()

        st.divider()

        # ── 表单字段（绑定 session_state key，AI 填充后自动显示）──
        st.text_input(
            "场景名称 *",
            placeholder="例：客服投诉处理",
            key=SK["name"],
        )
        st.text_area(
            "① 场景描述 *",
            placeholder="描述训练场景的背景和目标（可由 AI 生成后手动修改）",
            height=110,
            key=SK["desc"],
        )
        st.text_area(
            "② 角色背景、需求和性格 *",
            placeholder="描述角色扮演者的设定、核心诉求、性格特征（可由 AI 生成后手动修改）",
            height=160,
            key=SK["role"],
        )
        st.text_input(
            "③ 能力评估维度 *",
            placeholder="用中文逗号分隔，例如：情绪安抚，问题解决，服务规范",
            key=SK["rules"],
        )

        st.markdown("")
        save_clicked = st.button("生成 Agent 配置并保存场景", type="primary", use_container_width=True)

        if save_clicked:
            scene_name      = st.session_state[SK["name"]].strip()
            scene_dept      = st.session_state[SK["dept"]]
            scene_desc      = st.session_state[SK["desc"]].strip()
            role_background = st.session_state[SK["role"]].strip()
            eval_rules      = st.session_state[SK["rules"]].strip()

            if not all([scene_name, scene_desc, role_background, eval_rules]):
                st.error("请填写所有必填字段（场景名称、场景描述、角色背景、评估维度均不能为空）")
            else:
                scene_id = f"custom_{uuid.uuid4().hex[:8]}"
                try:
                    cfg = build_custom_scenario_config(
                        scenario_id=scene_id, name=scene_name,
                        department=scene_dept, description=scene_desc,
                        role_background=role_background,
                        evaluation_rules_str=eval_rules,
                    )
                    save_custom_scenario(cfg)
                    # 清空表单
                    for sk in SK.values():
                        st.session_state[sk] = "" if sk != SK["dept"] else "HR部门"
                    st.success(f"场景「{scene_name}」创建成功，Agent 配置已自动生成。")
                    with st.expander("查看角色 Agent 提示词"):
                        st.code(cfg["role_system_prompt"], language="markdown")
                    with st.expander("查看教练 Agent 提示词"):
                        st.code(cfg["coach_system_prompt"], language="markdown")
                    st.rerun()
                except Exception as e:
                    st.error(f"场景创建失败: {e}")

    with tab_existing:
        st.subheader("内置场景")
        for sid, sc in BUILTIN_SCENARIOS.items():
            with st.expander(f"{sc['name']} — {sc['department']}"):
                st.write(f"**难度：** {sc.get('difficulty','—')}  |  **时长：** {sc['estimated_time']}")
                st.write(f"**描述：** {sc['description']}")
                st.write(f"**评估维度：** {'、'.join(sc['evaluation_rules'])}")
                if st.button("开始训练", key=f"builtin_{sid}"):
                    start_training(sc); st.rerun()

        custom_list = load_custom_scenarios()
        if custom_list:
            st.subheader("自定义场景")
            for cs in custom_list:
                with st.expander(f"{cs['name']} — {cs['department']}"):
                    st.write(f"**描述：** {cs['description']}")
                    st.write(f"**评估维度：** {'、'.join(cs['evaluation_rules'])}")
                    ca, cb = st.columns(2)
                    if ca.button("开始训练", key=f"cust_train_{cs['id']}"):
                        start_training(cs); st.rerun()
                    if cb.button("删除", key=f"cust_del_{cs['id']}", type="secondary"):
                        delete_custom_scenario(cs["id"])
                        st.success("已删除"); st.rerun()
        else:
            st.info("暂无自定义场景，在「创建新场景」标签页中创建第一个。")


# ══════════════════════════════════════════════════════════════════
# 页面：训练历史
# ══════════════════════════════════════════════════════════════════
def page_history():
    user = st.session_state.user
    profile = get_user_profile(user["username"])
    sessions = profile.get("training_sessions", []) if profile else []

    st.markdown('<div class="page-title">训练历史</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">历次训练记录与能力变化</div>', unsafe_allow_html=True)

    if not sessions:
        st.info("暂无训练记录，去首页选择一个场景开始吧。")
        if st.button("去首页"): nav_to("home"); st.rerun()
        return

    # 汇总统计
    col1, col2, col3 = st.columns(3)
    col1.metric("总训练次数", len(sessions))
    col2.metric("平均综合得分",
        f"{round(sum(s.get('overall_score',0) for s in sessions)/len(sessions),1)}/10")
    col3.metric("最近一次", sessions[-1]["date"])

    st.divider()

    # 能力趋势图（训练次数 > 1 时才显示）
    if len(sessions) > 1:
        st.subheader("能力成长趋势")
        all_skills: set = set()
        for s in sessions:
            all_skills.update(s.get("scores", {}).keys())
        if all_skills:
            dates = [s["date"] for s in sessions]
            fig_trend = go.Figure()
            for skill in all_skills:
                vals = [s.get("scores", {}).get(skill) for s in sessions]
                x = [d for d, v in zip(dates, vals) if v is not None]
                y = [v for v in vals if v is not None]
                if x:
                    fig_trend.add_trace(go.Scatter(
                        x=x, y=y, mode="lines+markers", name=skill,
                        line=dict(width=2), marker=dict(size=7),
                    ))
            fig_trend.update_layout(
                xaxis_title="训练日期", yaxis_title="得分",
                yaxis=dict(range=[0, 10]),
                paper_bgcolor="#0F172A", plot_bgcolor="#0F172A",
                height=280,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})
        st.divider()

    # 训练记录列表（最新在前）
    st.subheader("训练记录")
    for s in reversed(sessions):
        scores = s.get("scores", {})
        overall = s.get("overall_score", "—")
        header = f"{s.get('scenario_name','—')}   |   综合得分 {overall}/10   |   {s['date']}"

        with st.expander(header, expanded=False):
            # 各维度分数条
            if scores:
                score_cols = st.columns(len(scores))
                for idx, (skill, score) in enumerate(scores.items()):
                    score_cols[idx].metric(skill, f"{score}/10")
                    score_cols[idx].progress(score / 10)

            st.caption(f"对话轮次：{s.get('round_count', '—')}   |   日期：{s['date']}")

            # 查看完整报告按钮
            report_md = s.get("report_md", "")
            if report_md:
                if st.button("查看完整报告", key=f"view_report_{s['id']}"):
                    st.session_state.viewing_history_report = s
                    nav_to("history_report")
                    st.rerun()
            else:
                st.caption("（旧版训练记录，无完整报告）")


# ══════════════════════════════════════════════════════════════════
# 页面：历史完整报告（从历史页面进入）
# ══════════════════════════════════════════════════════════════════
def page_history_report():
    s = st.session_state.get("viewing_history_report")
    if not s:
        nav_to("history"); st.rerun()
        return

    # 复用报告渲染，但传入伪 report dict
    report = {
        "report_md":    s.get("report_md", ""),
        "scores":       s.get("scores", {}),
        "overall":      s.get("overall_score", 0),
        "scenario_name": s.get("scenario_name", "—"),
        "date":         s.get("date", "—"),
        "round_count":  s.get("round_count", "—"),
        "is_mock":      False,
    }
    _render_report(report)

    st.divider()
    if st.button("返回训练历史", type="primary"):
        nav_to("history"); st.rerun()


# ══════════════════════════════════════════════════════════════════
# 页面：用户管理（admin 专属）
# ══════════════════════════════════════════════════════════════════
def page_user_mgmt():
    user = st.session_state.user
    if user["role"] != "admin":
        st.warning("仅管理员可访问此页面")
        return

    st.markdown('<div class="page-title">用户管理</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">新增、编辑、删除平台用户账号</div>', unsafe_allow_html=True)

    DEPARTMENTS = ["HR部门", "销售部门", "技术部门", "客服部门", "财务部门", "运营部门", "管理层", "其他"]
    ROLES       = ["learner", "manager", "admin"]
    ROLE_LABELS = {"learner": "学员", "manager": "管理者", "admin": "超级管理员"}

    tab_list, tab_create = st.tabs(["用户列表", "新增用户"])

    # ── Tab1: 用户列表 ────────────────────────────────────────────
    with tab_list:
        all_users = db_get_all_users()
        if not all_users:
            st.info("暂无用户数据")
        else:
            # 搜索框
            search = st.text_input("搜索用户名 / 姓名 / 部门", placeholder="输入关键词筛选")
            if search:
                kw = search.lower()
                all_users = [u for u in all_users if
                             kw in u["username"].lower() or
                             kw in u["name"].lower() or
                             kw in u["department"].lower()]

            st.caption(f"共 {len(all_users)} 名用户")
            st.divider()

            for u in all_users:
                is_self = (u["username"] == user["username"])
                col_info, col_edit, col_del = st.columns([5, 1, 1])

                with col_info:
                    st.markdown(
                        f"**{u['name']}** &nbsp; `{u['username']}` &nbsp; "
                        f"{u['department']} &nbsp; "
                        f"*{ROLE_LABELS.get(u['role'], u['role'])}*"
                    )
                    st.caption(f"创建时间：{u['created_at']}")

                # 编辑按钮 → 展开编辑表单
                edit_key  = f"edit_open_{u['username']}"
                if edit_key not in st.session_state:
                    st.session_state[edit_key] = False

                if col_edit.button("编辑", key=f"btn_edit_{u['username']}"):
                    st.session_state[edit_key] = not st.session_state[edit_key]

                # 删除按钮（自己不能删自己）
                if is_self:
                    col_del.button("删除", key=f"btn_del_{u['username']}", disabled=True,
                                   help="不能删除当前登录账号")
                else:
                    if col_del.button("删除", key=f"btn_del_{u['username']}", type="secondary"):
                        db_delete_user(u["username"])
                        st.success(f"已删除用户 {u['name']}（{u['username']}）")
                        st.rerun()

                # 编辑展开区
                if st.session_state[edit_key]:
                    with st.container():
                        st.markdown("---")
                        with st.form(f"edit_form_{u['username']}"):
                            st.markdown(f"**编辑用户：{u['username']}**")
                            ec1, ec2 = st.columns(2)
                            new_name  = ec1.text_input("姓名", value=u["name"])
                            new_dept  = ec2.selectbox(
                                "部门", DEPARTMENTS,
                                index=DEPARTMENTS.index(u["department"]) if u["department"] in DEPARTMENTS else 0,
                            )
                            er1, er2 = st.columns(2)
                            new_role  = er1.selectbox(
                                "角色", ROLES,
                                format_func=lambda x: ROLE_LABELS[x],
                                index=ROLES.index(u["role"]) if u["role"] in ROLES else 0,
                                disabled=is_self,   # 不允许自己降权
                            )
                            new_pwd = er2.text_input(
                                "新密码（留空则不修改）", type="password", placeholder="留空不修改"
                            )
                            save_btn = st.form_submit_button("保存修改", type="primary")

                        if save_btn:
                            if not new_name.strip():
                                st.error("姓名不能为空")
                            else:
                                db_update_user(
                                    username=u["username"],
                                    name=new_name.strip(),
                                    department=new_dept,
                                    role=new_role,
                                    password=new_pwd.strip() if new_pwd.strip() else None,
                                )
                                st.success(f"用户 {u['username']} 信息已更新")
                                st.session_state[edit_key] = False
                                # 如果改的是自己的信息，刷新 session 里的用户对象
                                if is_self:
                                    updated = db_get_all_users()
                                    for uu in updated:
                                        if uu["username"] == user["username"]:
                                            st.session_state.user = {**st.session_state.user,
                                                                      "name": uu["name"],
                                                                      "department": uu["department"],
                                                                      "role": uu["role"]}
                                st.rerun()

                st.divider()

    # ── Tab2: 新增用户 ────────────────────────────────────────────
    with tab_create:
        with st.form("create_user_form", clear_on_submit=True):
            st.markdown("**填写新用户信息**")
            nc1, nc2 = st.columns(2)
            new_username = nc1.text_input("用户名 *", placeholder="仅限字母、数字、下划线")
            new_uname    = nc2.text_input("姓名 *",   placeholder="真实姓名")
            nd1, nd2 = st.columns(2)
            new_dept = nd1.selectbox("部门 *", DEPARTMENTS)
            new_role = nd2.selectbox("角色 *", ROLES, format_func=lambda x: ROLE_LABELS[x])
            np1, np2 = st.columns(2)
            new_pwd  = np1.text_input("密码 *", type="password", placeholder="至少6位")
            new_pwd2 = np2.text_input("确认密码 *", type="password", placeholder="再次输入密码")
            submitted = st.form_submit_button("创建用户", type="primary", use_container_width=True)

        if submitted:
            errs = []
            if not new_username.strip():
                errs.append("用户名不能为空")
            elif not new_username.strip().replace("_", "").isalnum():
                errs.append("用户名只能包含字母、数字和下划线")
            if not new_uname.strip():
                errs.append("姓名不能为空")
            if not new_pwd:
                errs.append("密码不能为空")
            elif len(new_pwd) < 6:
                errs.append("密码至少6位")
            elif new_pwd != new_pwd2:
                errs.append("两次密码输入不一致")

            if errs:
                for e in errs:
                    st.error(e)
            else:
                try:
                    db_create_user(
                        username=new_username.strip(),
                        password=new_pwd,
                        name=new_uname.strip(),
                        department=new_dept,
                        role=new_role,
                    )
                    st.success(f"用户「{new_uname}」（{new_username}）创建成功！")
                except Exception as e:
                    if "UNIQUE constraint" in str(e):
                        st.error(f"用户名 `{new_username}` 已存在，请换一个")
                    else:
                        st.error(f"创建失败：{e}")


# ══════════════════════════════════════════════════════════════════
# 视图一：员工虚拟实训端
# ══════════════════════════════════════════════════════════════════
def view_employee():
    import pandas as pd
    user    = st.session_state.user
    profile = get_user_profile(user["username"])
    caps    = profile.get("capabilities", {}) if profile else {}
    sessions = profile.get("training_sessions", []) if profile else []

    st.markdown('<div class="page-title">个人虚拟实训中心</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{user["name"]}  ·  {user["department"]}</div>', unsafe_allow_html=True)

    tab_hall, tab_profile = st.tabs(["个人实训大厅", "实训能力画像"])

    # ── Tab1: 个人实训大厅 ────────────────────────────────────────
    with tab_hall:
        scenarios = get_recommended_scenarios(user)
        if not scenarios:
            st.info("暂无推荐实训场景，请联系管理员创建。")
        else:
            for i in range(0, len(scenarios), 3):
                cols = st.columns(3)
                for j, sc in enumerate(scenarios[i:i+3]):
                    with cols[j]:
                        rule_scores = "  /  ".join(
                            f"{r}: {caps.get(r, '—')}" for r in sc["evaluation_rules"]
                        )
                        st.markdown(f"""
<div class="scenario-card">
    <div style="font-weight:700;font-size:1.05em;margin-bottom:4px">{sc['name']}</div>
    <div style="color:#94A3B8;font-size:0.82em">{sc['department']}  ·  {sc.get('difficulty','中级')}  ·  {sc['estimated_time']}</div>
    <div style="color:#64748B;font-size:0.78em;margin-top:6px">{sc['description'][:55]}...</div>
    <div style="font-size:0.76em;color:#818CF8;margin-top:8px">{rule_scores}</div>
</div>""", unsafe_allow_html=True)
                        if st.button("进入实训", key=f"emp_start_{sc['id']}", use_container_width=True, type="primary"):
                            start_training(sc)
                            st.rerun()

        # 最近一次复盘摘要
        if sessions:
            st.divider()
            last = sessions[-1]
            st.markdown("**最近一次实训摘要**")
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("场景", last.get("scenario_name", "—"))
            mc2.metric("综合得分", f"{last.get('overall_score','—')}/10")
            mc3.metric("日期", last.get("date", "—"))
            if last.get("report_md") and st.button("查看完整报告", key="emp_last_report"):
                st.session_state.viewing_history_report = last
                nav_to("history_report")
                st.rerun()

    # ── Tab2: 实训能力画像 ────────────────────────────────────────
    with tab_profile:
        if not caps:
            st.info("完成第一次实训后，能力画像将在此显示。")
            return

        col_r, col_s = st.columns([3, 2])
        with col_r:
            st.subheader("能力雷达图")
            fig = create_radar_chart(caps)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        with col_s:
            st.subheader("各维度得分")
            for skill, score in sorted(caps.items(), key=lambda x: -x[1]):
                st.write(f"**{skill}**")
                st.progress(score / 10, text=f"{score}/10")

        if sessions:
            st.divider()
            st.subheader("历史实训记录")
            rows = []
            for s in reversed(sessions):
                rows.append({
                    "日期":     s["date"],
                    "场景":     s.get("scenario_name", "—"),
                    "综合得分": f"{s.get('overall_score','—')}/10",
                    "轮次":     s.get("round_count", "—"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════
# 视图二：普通部门主管端
# ══════════════════════════════════════════════════════════════════
def view_dept_manager():
    from utils.mock_data import (
        get_dept_stats, get_dept_capability_gap,
        get_dept_user_detail, DEPT_SKILLS,
    )
    from agents.scenario_architect import generate_scenario, JOBS

    user = st.session_state.user
    dept = user["department"]

    st.markdown('<div class="page-title">部门主管控制台</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{dept}  ·  仅显示本部门数据</div>', unsafe_allow_html=True)

    tab_board, tab_scene, tab_data = st.tabs(["部门实训看板", "部门专属场景管理", "部门实训数据"])

    # ── Tab1: 部门实训看板 ────────────────────────────────────────
    with tab_board:
        stats = get_dept_stats(dept)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("部门总人数",   stats.get("total", "—"))
        m2.metric("已参训人数",   stats.get("completed", "—"))
        m3.metric("完成率",       stats.get("rate", "—"))
        m4.metric("平均综合得分", stats.get("avg_score", "—"))

        st.divider()
        st.subheader("能力维度分析")
        gap_df = get_dept_capability_gap(dept)
        st.dataframe(gap_df, use_container_width=True, hide_index=True)

        # 标注短板
        weakest = gap_df[gap_df["状态"] == "落后"] if "状态" in gap_df.columns else gap_df.iloc[0:0]
        if not weakest.empty:
            skills_str = "、".join(weakest["能力维度"].tolist())
            st.warning(f"当前落后全司均值的维度：{skills_str}，建议优先配置对应实训场景。")
        else:
            st.success("本部门各能力维度均高于或持平全司均值。")

    # ── Tab2: 部门专属场景管理 ────────────────────────────────────
    with tab_scene:
        SKD = {k: f"dm_sc_{k}" for k in ["dept", "job", "name", "desc", "role", "rules"]}
        for k, sk in SKD.items():
            if sk not in st.session_state:
                st.session_state[sk] = dept if k == "dept" else (JOBS[0] if k == "job" else "")

        DEPARTMENTS_ALL = ["HR部门","销售部门","技术部门","客服部门","财务部门","运营部门","其他"]
        dept_idx = DEPARTMENTS_ALL.index(dept) if dept in DEPARTMENTS_ALL else 0

        # 顶部：岗位选择 + AI 生成按钮
        col_job, col_btn = st.columns([3, 1])
        with col_job:
            st.selectbox("选择岗位（用于 AI 生成方案）", JOBS, key=SKD["job"])
        with col_btn:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("AI 生成场景方案", type="primary", use_container_width=True, key="dm_ai_gen"):
                with st.spinner("Scenario Architect Agent 正在生成..."):
                    result = generate_scenario(st.session_state[SKD["job"]], dept)
                if result.get("_is_mock"):
                    st.info("Mock 演示模式，已填入预设示例。")
                if result.get("error"):
                    st.warning(result["error"])
                for field, key in [("name","name"),("description","desc"),("role_background","role"),("eval_rules","rules")]:
                    if result.get(field):
                        st.session_state[SKD[key]] = result[field]
                st.success("AI 已生成场景方案，可在下方编辑后保存。")
                st.rerun()

        st.divider()
        st.text_input("场景名称 *", placeholder="例：销售客户异议处理", key=SKD["name"])
        st.text_area("场景描述 *", height=100, key=SKD["desc"])
        st.text_area("角色背景、需求和性格 *", height=140, key=SKD["role"])
        st.text_input("能力评估维度 *", placeholder="用中文逗号分隔", key=SKD["rules"])

        if st.button("保存场景", type="primary", use_container_width=True, key="dm_save_scene"):
            name  = st.session_state[SKD["name"]].strip()
            desc  = st.session_state[SKD["desc"]].strip()
            role  = st.session_state[SKD["role"]].strip()
            rules = st.session_state[SKD["rules"]].strip()
            if not all([name, desc, role, rules]):
                st.error("请填写所有必填字段")
            else:
                import uuid as _uuid
                cfg = build_custom_scenario_config(
                    scenario_id=f"custom_{_uuid.uuid4().hex[:8]}",
                    name=name, department=dept, description=desc,
                    role_background=role, evaluation_rules_str=rules,
                )
                save_custom_scenario(cfg)
                for k in SKD.values():
                    st.session_state[k] = ""
                st.success(f"场景「{name}」已保存，仅本部门可见。")
                st.rerun()

        # 本部门已有自定义场景
        dept_custom = [s for s in load_custom_scenarios() if s.get("department") == dept]
        if dept_custom:
            st.divider()
            st.subheader("本部门已有场景")
            for cs in dept_custom:
                with st.expander(f"{cs['name']}"):
                    st.write(cs.get("description", ""))
                    st.caption("评估维度：" + "、".join(cs["evaluation_rules"]))
                    ca, cb = st.columns(2)
                    if ca.button("进入实训", key=f"dm_train_{cs['id']}"):
                        start_training(cs); st.rerun()
                    if cb.button("删除", key=f"dm_del_{cs['id']}", type="secondary"):
                        delete_custom_scenario(cs["id"])
                        st.success("已删除"); st.rerun()

    # ── Tab3: 部门实训数据 ────────────────────────────────────────
    with tab_data:
        st.subheader("部门成员实训进度")
        st.caption("以下数据为平台模拟数据，接入真实用户后自动同步。")
        detail_df = get_dept_user_detail(dept)
        st.dataframe(detail_df, use_container_width=True, hide_index=True)

        # 梯队分布
        if "状态" in detail_df.columns and not detail_df.empty:
            st.divider()
            st.subheader("梯队分布")
            label_counts = detail_df["状态"].value_counts().reset_index()
            label_counts.columns = ["状态", "人数"]
            total = label_counts["人数"].sum()
            label_counts["占比"] = label_counts["人数"].apply(lambda x: f"{x/total*100:.1f}%")
            st.dataframe(label_counts, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════
# 视图三：HR 全局培训管理端
# ══════════════════════════════════════════════════════════════════
def view_hr_admin():
    import pandas as pd
    from utils.mock_data import (
        get_global_stats, get_dept_overview, get_top_scenarios,
        get_company_capability_gap, get_global_user_table,
        get_skill_model_config, DEPT_SKILLS, DEPARTMENTS,
    )
    from agents.scenario_architect import generate_scenario, JOBS

    st.markdown('<div class="page-title">HR 全局培训管理端</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">全平台实训运营数据  ·  场景下发  ·  能力模型配置</div>', unsafe_allow_html=True)

    tab_kpi, tab_scene, tab_model, tab_query = st.tabs([
        "全局运营数据看板", "公共与专属场景管理", "能力模型管理", "全局训练数据查询"
    ])

    # ── Tab1: 全局运营数据看板 ────────────────────────────────────
    with tab_kpi:
        gs = get_global_stats()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("平台注册用户",   gs["total_users"])
        m2.metric("今日活跃实训",   gs["today_active"])
        m3.metric("累计实训场次",   gs["total_sessions"])
        m4.metric("平台平均得分",   f"{gs['avg_score']}/10")

        st.divider()

        c_left, c_right = st.columns([3, 2])
        with c_left:
            st.subheader("各部门完成率对比")
            dept_df = get_dept_overview()
            st.dataframe(dept_df, use_container_width=True, hide_index=True)

        with c_right:
            st.subheader("热门场景 TOP 5")
            top_df = get_top_scenarios(5)
            st.dataframe(top_df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("全公司能力短板跨部门统计")
        gap_df = get_company_capability_gap()
        st.dataframe(gap_df, use_container_width=True, hide_index=True)
        st.caption("'—' 表示该部门未配置此维度  ·  数值越低代表该维度越需重点关注")

    # ── Tab2: 公共与专属场景管理 ──────────────────────────────────
    with tab_scene:
        DEPARTMENTS_ALL = ["HR部门","销售部门","技术部门","客服部门","财务部门","运营部门","其他"]
        SKH = {k: f"hr_sc_{k}" for k in ["scope","dept","job","name","desc","role","rules"]}
        for k, sk in SKH.items():
            if sk not in st.session_state:
                st.session_state[sk] = ("HR专属" if k == "scope" else
                                         "HR部门" if k == "dept" else
                                         JOBS[0]   if k == "job" else "")

        # 场景类型切换
        scope_col, job_col, btn_col = st.columns([2, 2, 1])
        with scope_col:
            st.radio(
                "场景类型",
                ["HR专属", "全员通用"],
                key=SKH["scope"],
                horizontal=True,
                help="全员通用场景对所有部门可见，HR专属场景仅对HR部门可见",
            )
        with job_col:
            st.selectbox("选择岗位（用于 AI 生成）", JOBS, key=SKH["job"])
        with btn_col:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("AI 生成方案", type="primary", use_container_width=True, key="hr_ai_gen"):
                with st.spinner("Scenario Architect Agent 正在生成..."):
                    result = generate_scenario(st.session_state[SKH["job"]], st.session_state[SKH["dept"]])
                if result.get("_is_mock"):
                    st.info("Mock 演示模式，已填入预设示例。")
                for field, key in [("name","name"),("description","desc"),("role_background","role"),("eval_rules","rules")]:
                    if result.get(field):
                        st.session_state[SKH[key]] = result[field]
                st.success("AI 已生成场景方案，可在下方编辑后保存。")
                st.rerun()

        st.divider()

        hr_dept = "全员通用" if st.session_state[SKH["scope"]] == "全员通用" else st.session_state[SKH["dept"]]
        st.text_input("场景名称 *",         key=SKH["name"],  placeholder="例：职场合规行为规范")
        st.text_area("场景描述 *",  height=100, key=SKH["desc"])
        st.text_area("角色背景、需求和性格 *", height=130, key=SKH["role"])
        st.text_input("能力评估维度 *",      key=SKH["rules"], placeholder="用中文逗号分隔")

        if st.button("保存并下发场景", type="primary", use_container_width=True, key="hr_save_scene"):
            name  = st.session_state[SKH["name"]].strip()
            desc  = st.session_state[SKH["desc"]].strip()
            role  = st.session_state[SKH["role"]].strip()
            rules = st.session_state[SKH["rules"]].strip()
            if not all([name, desc, role, rules]):
                st.error("请填写所有必填字段")
            else:
                import uuid as _uuid
                cfg = build_custom_scenario_config(
                    scenario_id=f"custom_{_uuid.uuid4().hex[:8]}",
                    name=name, department=hr_dept, description=desc,
                    role_background=role, evaluation_rules_str=rules,
                )
                save_custom_scenario(cfg)
                for k in SKH.values():
                    st.session_state[k] = ""
                scope_label = "全员通用" if st.session_state.get(SKH["scope"]) == "全员通用" else "HR专属"
                st.success(f"场景「{name}」已保存（{scope_label}），相关部门员工可立即使用。")
                st.rerun()

        # 已有场景列表
        st.divider()
        st.subheader("已有自定义场景")
        custom_list = load_custom_scenarios()
        if custom_list:
            rows = [{"场景名称": c["name"], "所属部门": c["department"],
                     "评估维度": "、".join(c["evaluation_rules"][:2]) + ("..." if len(c["evaluation_rules"]) > 2 else ""),
                     "场景ID": c["id"]}
                    for c in custom_list]
            scene_df = pd.DataFrame(rows)
            st.dataframe(scene_df[["场景名称","所属部门","评估维度"]], use_container_width=True, hide_index=True)
        else:
            st.info("暂无自定义场景。")

    # ── Tab3: 能力模型管理 ────────────────────────────────────────
    with tab_model:
        st.subheader("各部门能力维度与权重配置")
        st.caption("可直接在表格中修改权重值（各部门权重之和应为 100%），修改后点击「保存配置」生效。")

        skill_df = get_skill_model_config()

        edited = st.data_editor(
            skill_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "部门":     st.column_config.TextColumn("部门",     disabled=True),
                "能力维度": st.column_config.TextColumn("能力维度", disabled=True),
                "权重(%)":  st.column_config.NumberColumn("权重(%)", min_value=0, max_value=100, step=5),
                "状态":     st.column_config.SelectboxColumn("状态", options=["启用", "停用"]),
            },
            key="hr_skill_editor",
        )

        if st.button("保存配置", type="primary", key="hr_save_model"):
            # 校验每个部门的权重是否合计 100
            weight_check = edited.groupby("部门")["权重(%)"].sum()
            invalid = weight_check[weight_check != 100]
            if not invalid.empty:
                for dept_name, total in invalid.items():
                    st.error(f"「{dept_name}」权重合计为 {total}%，须等于 100%")
            else:
                st.success("能力模型配置已保存。（Demo 模式：重启后恢复默认值）")

        st.divider()
        st.subheader("新增能力维度")
        nc1, nc2, nc3 = st.columns([2, 2, 1])
        new_dept_m  = nc1.selectbox("所属部门", DEPARTMENTS, key="hr_new_skill_dept")
        new_skill_m = nc2.text_input("维度名称", placeholder="例：客户满意度管理", key="hr_new_skill_name")
        nc3.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if nc3.button("添加", key="hr_add_skill"):
            if new_skill_m.strip():
                st.success(f"已为「{new_dept_m}」添加维度「{new_skill_m}」（Demo 模式：重启后恢复）")
            else:
                st.error("维度名称不能为空")

    # ── Tab4: 全局训练数据查询 ────────────────────────────────────
    with tab_query:
        st.subheader("全员实训进度总览")

        # 筛选栏
        fc1, fc2, fc3 = st.columns([2, 2, 2])
        filter_dept   = fc1.selectbox("筛选部门", ["全部"] + DEPARTMENTS, key="hr_filter_dept")
        filter_label  = fc2.selectbox("梯队标签", ["全部", "高潜人才", "稳健成长", "成长中", "需重点关注"], key="hr_filter_label")
        filter_status = fc3.selectbox("参训状态", ["全部", "活跃", "入门", "未开始"], key="hr_filter_status")

        global_df = get_global_user_table()
        if filter_dept != "全部":
            global_df = global_df[global_df["部门"] == filter_dept]
        if filter_label != "全部":
            global_df = global_df[global_df["梯队标签"] == filter_label]
        if filter_status != "全部":
            pass  # 状态信息在 dept_user_detail，全局表未冗余，此处演示筛选框

        st.caption(f"共 {len(global_df)} 条记录")
        st.dataframe(global_df, use_container_width=True, hide_index=True)

        # 梯队汇总
        st.divider()
        st.subheader("全公司梯队分布")
        tier_df = get_global_user_table()["梯队标签"].value_counts().reset_index()
        tier_df.columns = ["梯队标签", "人数"]
        tier_df["占比"] = tier_df["人数"].apply(lambda x: f"{x/len(get_global_user_table())*100:.1f}%")
        st.dataframe(tier_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════
# 视图四：系统超管端
# ══════════════════════════════════════════════════════════════════
def view_super_admin():
    import pandas as pd
    from utils.mock_data import (
        get_dept_manager_table, get_token_stats,
        get_dept_token_usage, get_api_health, DEPARTMENTS,
    )
    from utils.db import db_get_all_users, db_update_user

    st.markdown('<div class="page-title">系统超管端</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">部门架构  ·  权限分配  ·  资源与模型监控</div>', unsafe_allow_html=True)

    tab_org, tab_monitor = st.tabs(["部门架构与权限分配", "系统资源与大模型监控"])

    # ── Tab1: 部门架构与权限分配 ──────────────────────────────────
    with tab_org:
        st.subheader("部门主管账号分配")
        mgr_df = get_dept_manager_table()
        st.dataframe(mgr_df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("变更部门主管")
        all_users = db_get_all_users()
        user_options = {f"{u['name']} ({u['username']})": u["username"] for u in all_users}

        oc1, oc2, oc3 = st.columns([2, 2, 1])
        assign_dept = oc1.selectbox("目标部门", DEPARTMENTS, key="sa_assign_dept")
        assign_user_label = oc2.selectbox("指派主管账号", list(user_options.keys()), key="sa_assign_user")
        oc3.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if oc3.button("确认指派", type="primary", key="sa_assign_btn"):
            target_username = user_options[assign_user_label]
            db_update_user(target_username,
                           name=next(u["name"] for u in all_users if u["username"] == target_username),
                           department=assign_dept,
                           role="manager")
            st.success(f"已将 {assign_user_label} 设为「{assign_dept}」主管，部门已同步更新。")
            st.rerun()

        st.divider()
        st.subheader("全体用户账号列表")
        users_df = pd.DataFrame([{
            "用户名":   u["username"],
            "姓名":     u["name"],
            "部门":     u["department"],
            "角色":     u["role"],
            "创建时间": u["created_at"],
        } for u in all_users])
        st.dataframe(users_df, use_container_width=True, hide_index=True)

    # ── Tab2: 系统资源与大模型监控 ────────────────────────────────
    with tab_monitor:
        ts = get_token_stats()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("本月累计 Token 消耗", f"{ts['total_tokens']:,}")
        m2.metric("今日 Token 消耗",      f"{ts['today_tokens']:,}")
        m3.metric("人均单次消耗",          f"{ts['avg_per_session']:,}")
        m4.metric("本月预估费用(CNY)",      f"¥ {ts['cost_cny']}")

        st.divider()

        cl, cr = st.columns([1, 1])
        with cl:
            st.subheader("各部门算力资源占用")
            st.dataframe(get_dept_token_usage(), use_container_width=True, hide_index=True)

        with cr:
            st.subheader("API 接口健康度")
            health_df = get_api_health()
            # 对状态列着色提示
            st.dataframe(health_df, use_container_width=True, hide_index=True)
            watching = health_df[health_df["状态"] == "观察中"]
            if not watching.empty:
                st.warning(f"以下接口可用率低于 98%，建议关注：{', '.join(watching['接口名称'].tolist())}")
            else:
                st.success("所有接口运行正常。")

        st.divider()
        st.subheader("大模型配置")
        ark_key   = os.getenv("ARK_API_KEY", "")
        ark_model = os.getenv("ARK_MODEL", "未配置")
        ark_url   = os.getenv("ARK_BASE_URL", "未配置")
        cfg_data = pd.DataFrame([
            {"配置项": "API Key 状态",  "当前值": "已配置" if ark_key else "未配置（Mock 模式运行中）"},
            {"配置项": "模型 ID",        "当前值": ark_model},
            {"配置项": "API Base URL",  "当前值": ark_url},
        ])
        st.dataframe(cfg_data, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════
# 共用报告渲染
# ══════════════════════════════════════════════════════════════════
def _render_report(report: dict):
    st.markdown('<div class="page-title">训练报告</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="page-subtitle">'
        f'{report["scenario_name"]} · {report["date"]} · 共 {report["round_count"]} 轮对话'
        f'</div>',
        unsafe_allow_html=True,
    )

    if report.get("is_mock"):
        st.info("Mock 演示报告 — 以下内容为预设示例，展示报告格式和能力画像更新流程。")

    col_report, col_chart = st.columns([3, 2])

    with col_report:
        st.markdown(clean_report(report["report_md"]))

    with col_chart:
        st.subheader("本次训练得分")
        scores = report.get("scores", {})
        for skill, score in scores.items():
            st.write(f"**{skill}**")
            st.progress(score / 10, text=f"{score}/10")
        st.metric("综合得分", f"{report.get('overall', 0)}/10")

        st.divider()
        st.subheader("能力画像（当前）")
        profile = get_user_profile(st.session_state.user["username"])
        if profile and profile.get("capabilities"):
            fig = create_radar_chart(profile["capabilities"])
            if fig:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ══════════════════════════════════════════════════════════════════
# 主路由
# ══════════════════════════════════════════════════════════════════
def main():
    if not st.session_state.authenticated:
        page_login()
        return

    render_sidebar()
    page = st.session_state.page

    # Full-page bypasses — render without view wrapper
    if page == "training":
        page_training()
        return
    if page == "report":
        page_report()
        return
    if page == "history_report":
        page_history_report()
        return

    # View-based routing via sidebar selectbox
    view = st.session_state.get("platform_view", "员工虚拟实训端")
    VIEW_MAP = {
        "员工虚拟实训端":    view_employee,
        "普通部门主管端":    view_dept_manager,
        "HR全局培训管理端": view_hr_admin,
        "系统超管端":        view_super_admin,
    }
    fn = VIEW_MAP.get(view)
    if fn:
        fn()
    else:
        view_employee()


if __name__ == "__main__":
    main()
