"""
profile_manager.py — 用户能力画像管理

职责：
  - 从 data/users.json 读取用户信息
  - 登录验证
  - 训练后更新能力画像（加权移动平均，防止单次波动过大）
  - 保存训练会话记录

Demo 使用 JSON 文件存储，生产环境替换为数据库即可。
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, List, Any

# 数据文件路径
DATA_DIR = Path(__file__).parent.parent / "data"
USERS_FILE = DATA_DIR / "users.json"
CUSTOM_SCENARIOS_FILE = DATA_DIR / "custom_scenarios.json"


# ── 用户认证 ─────────────────────────────────────────────────────
def authenticate(username: str, password: str) -> Optional[Dict]:
    """
    验证用户名和密码，成功返回用户 profile dict，失败返回 None。
    Demo 版：明文密码匹配，从 JSON 文件读取。
    """
    users = _load_users()
    user = users.get(username)
    if user and user.get("password") == password:
        # 返回时去掉密码字段
        return {k: v for k, v in user.items() if k != "password"}
    return None


# ── 用户数据读写 ──────────────────────────────────────────────────
def get_user_profile(username: str) -> Optional[Dict]:
    """读取单个用户的完整 profile。"""
    users = _load_users()
    user = users.get(username)
    if user:
        return {k: v for k, v in user.items() if k != "password"}
    return None


def save_training_result(username: str, result: dict) -> None:
    """
    训练结束后：
    1. 将本次训练记录追加到 user.training_sessions
    2. 用加权移动平均更新 user.capabilities

    加权方式：新分数权重 0.3，历史均值权重 0.7，避免单次波动过大。
    """
    users = _load_users()
    user = users.get(username)
    if not user:
        return

    # 1. 记录本次训练 session（含完整报告文本，用于历史页面展开查看）
    session_record = {
        "id": result["session_id"],
        "scenario_id": result["scenario_id"],
        "scenario_name": result["scenario_name"],
        "date": result["date"],
        "scores": result["scores"],
        "overall_score": result["overall"],
        "round_count": result["round_count"],
        "report_md": result.get("report_md", ""),
    }
    user.setdefault("training_sessions", []).append(session_record)

    # 2. 更新能力画像（加权移动平均）
    capabilities = user.setdefault("capabilities", {})
    for skill, new_score in result["scores"].items():
        old_score = capabilities.get(skill, 5.0)
        # 如果是首次，直接使用新分数；否则加权平均
        if old_score == 5.0 and skill not in capabilities:
            updated = new_score
        else:
            updated = round(old_score * 0.7 + new_score * 0.3, 1)
        capabilities[skill] = updated

    _save_users(users)


# ── 自定义场景 CRUD ───────────────────────────────────────────────
def load_custom_scenarios() -> List[Dict]:
    """加载所有自定义场景。"""
    try:
        with open(CUSTOM_SCENARIOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_custom_scenario(scenario: dict) -> None:
    """保存一个新的自定义场景。"""
    scenarios = load_custom_scenarios()
    # 用 id 去重（如果已存在则覆盖）
    scenarios = [s for s in scenarios if s.get("id") != scenario.get("id")]
    scenarios.append(scenario)
    with open(CUSTOM_SCENARIOS_FILE, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, ensure_ascii=False, indent=2)


def delete_custom_scenario(scenario_id: str) -> None:
    """删除一个自定义场景。"""
    scenarios = load_custom_scenarios()
    scenarios = [s for s in scenarios if s.get("id") != scenario_id]
    with open(CUSTOM_SCENARIOS_FILE, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, ensure_ascii=False, indent=2)


# ── 场景 Prompt 自动生成 ──────────────────────────────────────────
def build_custom_scenario_config(
    scenario_id: str,
    name: str,
    department: str,
    description: str,
    role_background: str,
    evaluation_rules_str: str,
) -> dict:
    """
    根据用户填写的三要素（场景描述、角色背景、评估规则），
    自动生成完整的场景配置（含角色/教练/追踪 Agent 的系统提示词）。
    """
    rules = [r.strip() for r in evaluation_rules_str.split("，") if r.strip()]
    if not rules:
        rules = evaluation_rules_str.split(",")
        rules = [r.strip() for r in rules if r.strip()]

    role_prompt = f"""你是一个训练场景中的角色扮演者。

场景：{name}
你的角色背景和设定：
{role_background}

行为准则：
- 完全沉浸在角色中，用第一人称回应
- 根据学员的回应，真实地表现角色的情绪和反应
- 不要轻易配合或全盘接受，保持角色的真实立场
- 每次回复2-4句话，保持对话自然流畅

请用中文回复，保持角色扮演的沉浸感。"""

    rules_formatted = "\n".join([f"{i+1}. **{r}**" for i, r in enumerate(rules)])
    coach_prompt = f"""你是专业培训教练，负责{name}场景的学员辅导。

评估维度：
{rules_formatted}

当学员完成一轮对话后，给出简洁实用的教练反馈。

【输出格式（使用Markdown）】

**⭐ 做得好的地方**
（本次回应的亮点，1-2条）

**💡 改进建议**
（具体可操作的建议，1-2条）

**📝 参考话术**
（一个更有效的回应示例）

总字数控制在200字以内。"""

    rules_table = "\n".join([f"- {r}：是否在该维度表现良好" for r in rules])
    # Python 3.9 不支持 f-string 内嵌反斜杠，提前构建需要的字符串
    table_rows = "".join([f"| {r} | X/10 | 简评 |\n" for r in rules])
    scores_placeholder = ", ".join([f'"{r}": X' for r in rules])
    tracking_prompt = (
        f"你是专业能力评估专家，根据完整训练对话生成{name}场景的评估报告。\n\n"
        f"评估维度（每项1-10分）：\n{rules_table}\n\n"
        "【输出格式（使用Markdown）】\n\n"
        "## 📊 本次训练评分\n\n"
        "| 评估维度 | 得分 | 表现 |\n"
        "|---------|------|------|\n"
        f"{table_rows}"
        "| **综合得分** | **X/10** | |\n\n"
        "## ✅ 做得好的地方\n（3-4条具体优点）\n\n"
        "## 🔧 需要改进的地方\n（3-4条具体建议）\n\n"
        "## 🎯 下次训练建议\n（1-2句话推荐）\n\n"
        "JSON分数：\n"
        "```json\n"
        '{"scores": {' + scores_placeholder + '}, "overall": X}\n'
        "```"
    )

    return {
        "id": scenario_id,
        "name": name,
        "department": department,
        "icon": "🎯",
        "description": description,
        "role_name": f"场景角色（{name}）",
        "evaluation_rules": rules,
        "difficulty": "自定义",
        "estimated_time": "15-25分钟",
        "supports_code": False,
        "is_custom": True,
        "role_system_prompt": role_prompt,
        "coach_system_prompt": coach_prompt,
        "tracking_system_prompt": tracking_prompt,
    }


# ── 内部辅助 ─────────────────────────────────────────────────────
def _load_users() -> dict:
    """从 JSON 文件加载所有用户数据。"""
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_users(users: dict) -> None:
    """将用户数据写回 JSON 文件。"""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
