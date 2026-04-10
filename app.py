"""
app.py — AI练兵平台主入口（Streamlit 前端）

页面：
  login         — 登录
  home          — 首页（能力画像 + 推荐场景）
  scene_select  — 场景选择（learner 专属，显示本部门所有可用场景）
  training      — 训练室（多Agent对话 + 教练实时反馈）
  report        — 当次训练报告
  scenarios     — 场景管理（manager / admin 创建自定义场景）
  history       — 历史记录列表
  history_report— 历史某次训练的完整报告
  user_mgmt     — 用户管理（admin 专属：增删改查）
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
    page_title="AI练兵平台",
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
        "authenticated": False,
        "user": None,
        "page": "login",
        "training_session": None,
        "chat_history": [],
        "coach_feedbacks": [],
        "current_scenario": None,
        "training_finished": False,
        "training_report": None,
        "input_mode": "text",
        "viewing_history_report": None,   # 历史报告查看时存放的 session record
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
        st.markdown(f"## {user['name']}")
        st.caption(f"{user['department']}  ·  {user['role'].upper()}")
        st.divider()

        # 导航菜单：根据角色显示不同页面
        pages = [("首页", "home")]
        if user["role"] == "learner":
            pages.append(("场景选择", "scene_select"))
        pages.append(("训练历史", "history"))
        if user["role"] in ("manager", "admin"):
            pages.append(("场景管理", "scenarios"))
        if user["role"] == "admin":
            pages.append(("用户管理", "user_mgmt"))

        for label, pg in pages:
            if st.button(label, use_container_width=True, key=f"nav_{pg}"):
                nav_to(pg)

        st.divider()

        # 当前训练状态
        if st.session_state.training_session and not st.session_state.training_finished:
            sc = st.session_state.current_scenario
            if sc:
                st.caption("训练进行中")
                st.write(f"**{sc['name']}**")
                st.write(f"已对话 {st.session_state.training_session.round_count} 轮")
                if st.button("进入训练室", use_container_width=True):
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
        st.markdown("## AI 练兵平台")
        st.markdown("##### 多部门 · 多Agent · 实时教练")
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
    user = st.session_state.user
    if user["role"] not in ("manager", "admin"):
        st.warning("仅部门管理者和管理员可访问此页面")
        return

    st.markdown('<div class="page-title">场景管理</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">创建、管理训练场景 — 填写 3 个要素，平台自动生成 Agent 配置</div>', unsafe_allow_html=True)

    tab_create, tab_existing = st.tabs(["创建新场景", "已有场景"])

    with tab_create:
        st.info("只需填写 3 个要素，平台自动生成角色 Agent、教练 Agent 的完整配置。")
        with st.form("create_scenario_form"):
            c1, c2 = st.columns(2)
            scene_name = c1.text_input("场景名称 *", placeholder="例：客服投诉处理")
            scene_dept = c2.selectbox(
                "所属部门 *",
                ["HR部门", "销售部门", "技术部门", "客服部门", "财务部门", "运营部门", "其他"],
            )
            scene_desc = st.text_area(
                "① 场景描述 *",
                placeholder="描述训练场景的背景和目标",
                height=100,
            )
            role_background = st.text_area(
                "② 角色背景、需求和性格 *",
                placeholder="描述角色扮演者的设定、核心诉求、性格特征",
                height=150,
            )
            eval_rules = st.text_input(
                "③ 能力评估维度 *",
                placeholder="用中文逗号分隔，例如：情绪安抚，问题解决，服务规范",
            )
            submitted = st.form_submit_button("生成场景配置并保存", type="primary", use_container_width=True)

        if submitted:
            if not all([scene_name, scene_desc, role_background, eval_rules]):
                st.error("请填写所有必填字段")
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
                    st.success(f"场景「{scene_name}」创建成功，Agent 配置已自动生成。")
                    with st.expander("查看角色 Agent 提示词"):
                        st.code(cfg["role_system_prompt"], language="markdown")
                    with st.expander("查看教练 Agent 提示词"):
                        st.code(cfg["coach_system_prompt"], language="markdown")
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
    render_sidebar()
    page = st.session_state.page

    if not st.session_state.authenticated and page != "login":
        page = "login"

    dispatch = {
        "login":          page_login,
        "home":           page_home,
        "scene_select":   page_scene_select,
        "training":       page_training,
        "report":         page_report,
        "scenarios":      page_scenarios,
        "history":        page_history,
        "history_report": page_history_report,
        "user_mgmt":      page_user_mgmt,
    }
    fn = dispatch.get(page)
    if fn:
        fn()
    else:
        nav_to("home"); st.rerun()


if __name__ == "__main__":
    main()
