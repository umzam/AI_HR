"""
profile_manager.py — 用户能力画像管理

所有数据读写已切换至 SQLite（utils/db.py），JSON 文件仅保留为备份。
对外接口保持不变，app.py 无需感知底层存储细节。
"""

import json
import uuid
from pathlib import Path
from typing import Optional, Dict, List

from utils.db import (
    db_authenticate,
    db_get_user,
    db_save_training_result,
    db_load_custom_scenarios,
    db_save_custom_scenario,
    db_delete_custom_scenario,
)

DATA_DIR = Path(__file__).parent.parent / "data"
CUSTOM_SCENARIOS_FILE = DATA_DIR / "custom_scenarios.json"


# ── 用户认证 ─────────────────────────────────────────────────────
def authenticate(username: str, password: str) -> Optional[Dict]:
    return db_authenticate(username, password)


# ── 用户数据读取 ──────────────────────────────────────────────────
def get_user_profile(username: str) -> Optional[Dict]:
    return db_get_user(username)


# ── 训练结果保存 ──────────────────────────────────────────────────
def save_training_result(username: str, result: dict) -> None:
    db_save_training_result(username, result)


# ── 自定义场景 CRUD ───────────────────────────────────────────────
def load_custom_scenarios() -> List[Dict]:
    return db_load_custom_scenarios()


def save_custom_scenario(scenario: dict) -> None:
    db_save_custom_scenario(scenario)


def delete_custom_scenario(scenario_id: str) -> None:
    db_delete_custom_scenario(scenario_id)


# ── 场景 Prompt 自动生成 ──────────────────────────────────────────
def build_custom_scenario_config(
    scenario_id: str,
    name: str,
    department: str,
    description: str,
    role_background: str,
    evaluation_rules_str: str,
) -> dict:
    rules = [r.strip() for r in evaluation_rules_str.split("，") if r.strip()]
    if not rules:
        rules = [r.strip() for r in evaluation_rules_str.split(",") if r.strip()]

    role_prompt = (
        f"你是一个训练场景中的角色扮演者。\n\n"
        f"场景：{name}\n"
        f"你的角色背景和设定：\n{role_background}\n\n"
        "行为准则：\n"
        "- 完全沉浸在角色中，用第一人称回应\n"
        "- 根据学员的回应，真实地表现角色的情绪和反应\n"
        "- 不要轻易配合或全盘接受，保持角色的真实立场\n"
        "- 每次回复2-4句话，保持对话自然流畅\n\n"
        "请用中文回复，保持角色扮演的沉浸感。"
    )

    rules_formatted = "\n".join([f"{i+1}. **{r}**" for i, r in enumerate(rules)])
    coach_prompt = (
        f"你是专业培训教练，负责{name}场景的学员辅导。\n\n"
        f"评估维度：\n{rules_formatted}\n\n"
        "当学员完成一轮对话后，给出简洁实用的教练反馈。\n\n"
        "【输出格式（使用Markdown）】\n\n"
        "**做得好的地方**\n（本次回应的亮点，1-2条）\n\n"
        "**改进建议**\n（具体可操作的建议，1-2条）\n\n"
        "**参考话术**\n（一个更有效的回应示例）\n\n"
        "总字数控制在200字以内。"
    )

    rules_table  = "\n".join([f"- {r}：是否在该维度表现良好" for r in rules])
    table_rows   = "".join([f"| {r} | X/10 | 简评 |\n" for r in rules])
    scores_ph    = ", ".join([f'"{r}": X' for r in rules])
    tracking_prompt = (
        f"你是专业能力评估专家，根据完整训练对话生成{name}场景的评估报告。\n\n"
        f"评估维度（每项1-10分）：\n{rules_table}\n\n"
        "【输出格式（使用Markdown）】\n\n"
        "## 本次训练评分\n\n"
        "| 评估维度 | 得分 | 表现 |\n"
        "|---------|------|------|\n"
        f"{table_rows}"
        "| **综合得分** | **X/10** | |\n\n"
        "## 做得好的地方\n（3-4条具体优点）\n\n"
        "## 需要改进的地方\n（3-4条具体建议）\n\n"
        "## 下次训练建议\n（1-2句话推荐）\n\n"
        "JSON分数：\n"
        "```json\n"
        '{"scores": {' + scores_ph + '}, "overall": X}\n'
        "```"
    )

    return {
        "id": scenario_id,
        "name": name,
        "department": department,
        "icon": "",
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
