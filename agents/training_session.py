"""
training_session.py — 多Agent训练会话核心

运行模式：
  - Mock模式（无API Key）：使用 mock_responses.py 中的预设剧本，无需任何 API
  - Live模式（有API Key）：使用 OpenAI SDK 调用火山引擎（或任何 OpenAI 兼容 API）
      · 角色Agent：手动维护对话历史，支持多轮角色扮演
      · 教练Agent：每轮无状态调用，给出实时反馈
      · 追踪Agent：训练结束时调用，生成完整报告

自动检测：初始化时检查 ARK_API_KEY，自动切换模式。
"""

import json
import re
from datetime import datetime

from config import ARK_API_KEY, ARK_MODEL, ARK_BASE_URL
from agents.mock_responses import (
    get_mock_role_response,
    get_mock_coach_feedback,
    get_mock_final_report,
)


class TrainingSession:
    """
    一次完整的训练会话。

    Mock模式：ARK_API_KEY 为空时自动启用，使用预设剧本。
    Live模式：ARK_API_KEY 非空时启用，调用真实大模型。
    """

    def __init__(self, scenario_config: dict, api_key: str = ""):
        self.scenario = scenario_config
        # 优先使用传入的 api_key，其次读 config（来自 .env）
        self.api_key  = api_key.strip() or ARK_API_KEY
        self.is_mock  = not bool(self.api_key)

        self.conversation_history = []   # [{role, content, time}] 完整对话记录
        self.role_messages = []          # OpenAI messages 格式，供角色Agent保持记忆
        self.feedback_history = []       # [{round, content}]
        self.round_count = 0
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Live模式：初始化 OpenAI 客户端
        self._client = None
        if not self.is_mock:
            self._init_client()

    # ── 初始化 OpenAI 客户端 ─────────────────────────────────────
    def _init_client(self):
        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=ARK_BASE_URL,
            )
        except Exception as e:
            print(f"[WARNING] OpenAI 客户端初始化失败，降级 Mock: {e}")
            self.is_mock = True

    # ══════════════════════════════════════════════════════════════
    # 主接口：处理一轮用户输入
    # ══════════════════════════════════════════════════════════════
    def process_user_turn(self, user_message: str) -> dict:
        """
        完整处理一轮交互：角色回应 → 教练反馈 → 记录历史
        返回 {"role_response": str, "coach_feedback": str, "round": int}
        """
        self.round_count += 1

        if self.is_mock:
            role_response  = get_mock_role_response(self.scenario["id"], self.round_count)
            coach_feedback = get_mock_coach_feedback(self.scenario["id"], self.round_count)
        else:
            role_response  = self._live_role_response(user_message)
            coach_feedback = self._live_coach_feedback(user_message, role_response)

        # 记录历史
        ts = datetime.now().strftime("%H:%M:%S")
        self.conversation_history.append({"role": "user",  "content": user_message,  "time": ts})
        self.conversation_history.append({"role": "role",  "content": role_response, "time": ts})
        self.feedback_history.append({"round": self.round_count, "content": coach_feedback})

        return {
            "role_response":  role_response,
            "coach_feedback": coach_feedback,
            "round":          self.round_count,
        }

    # ══════════════════════════════════════════════════════════════
    # 训练报告
    # ══════════════════════════════════════════════════════════════
    def generate_report(self) -> dict:
        """训练结束，生成完整报告并解析评分。"""
        if self.is_mock:
            report_md = get_mock_final_report(self.scenario["id"])
        else:
            report_md = self._live_generate_report()

        scores, overall = self._extract_scores(report_md)

        return {
            "report_md":    report_md,
            "scores":       scores,
            "overall":      overall,
            "session_id":   self.session_id,
            "scenario_id":  self.scenario["id"],
            "scenario_name": self.scenario["name"],
            "round_count":  self.round_count,
            "date":         datetime.now().strftime("%Y-%m-%d"),
            "is_mock":      self.is_mock,
        }

    # ══════════════════════════════════════════════════════════════
    # Live 模式：OpenAI SDK 调用
    # ══════════════════════════════════════════════════════════════
    def _chat(self, system: str, messages: list, max_tokens: int = 800) -> str:
        """底层 OpenAI chat 调用，统一封装。"""
        resp = self._client.chat.completions.create(
            model=ARK_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}] + messages,
        )
        return resp.choices[0].message.content

    def _live_role_response(self, user_message: str) -> str:
        """
        角色Agent：手动维护 role_messages 列表实现多轮记忆。
        用户消息 → role_messages → 角色回应 → 追加到 role_messages
        """
        self.role_messages.append({"role": "user", "content": user_message})
        try:
            reply = self._chat(
                system=self.scenario["role_system_prompt"],
                messages=self.role_messages,
                max_tokens=512,
            )
        except Exception as e:
            reply = f"（角色Agent调用失败：{e}）"

        # 把角色回应也追加进去，保持对话连贯性
        self.role_messages.append({"role": "assistant", "content": reply})
        return reply

    def _live_coach_feedback(self, user_message: str, role_response: str) -> str:
        """教练Agent：每轮无状态调用，分析本轮表现。"""
        recent = self.conversation_history[-6:]
        context_lines = []
        for turn in recent:
            label = "学员" if turn["role"] == "user" else "角色"
            context_lines.append(f"{label}：{turn['content']}")
        context_str = "\n".join(context_lines) or "（这是第一轮对话）"
        eval_rules = "、".join(self.scenario["evaluation_rules"])

        prompt = (
            f"训练场景：{self.scenario['name']}\n"
            f"评估维度：{eval_rules}\n\n"
            f"近期对话：\n{context_str}\n\n"
            f"本轮最新交互：\n学员说：{user_message}\n角色回应：{role_response}\n\n"
            "请给出教练反馈。"
        )
        try:
            return self._chat(
                system=self.scenario["coach_system_prompt"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
            )
        except Exception as e:
            return f"（教练Agent调用失败：{e}）"

    def _live_generate_report(self) -> str:
        """追踪Agent：基于完整对话历史生成训练报告。"""
        conv_lines = []
        for turn in self.conversation_history:
            label = "【学员】" if turn["role"] == "user" else "【角色】"
            conv_lines.append(f"{label} {turn['content']}")

        prompt = (
            f"以下是完整训练对话（共{self.round_count}轮）：\n\n"
            + "\n".join(conv_lines)
            + "\n\n请生成训练评估报告。"
        )
        try:
            return self._chat(
                system=self.scenario["tracking_system_prompt"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
        except Exception as e:
            return f"报告生成失败：{e}"

    # ══════════════════════════════════════════════════════════════
    # 通用工具
    # ══════════════════════════════════════════════════════════════
    def _extract_scores(self, report_md: str) -> tuple:
        """从报告中提取 JSON 评分块，返回 (scores_dict, overall_float)。"""
        try:
            match = re.search(r"```json\s*(\{.*?\})\s*```", report_md, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                scores = {k: float(v) for k, v in data.get("scores", {}).items()}
                overall = float(data.get("overall", 0))
                if not overall and scores:
                    overall = round(sum(scores.values()) / len(scores), 1)
                return scores, overall
        except Exception as e:
            print(f"[WARNING] 评分解析失败: {e}")

        default_scores = {rule: 6.5 for rule in self.scenario["evaluation_rules"]}
        return default_scores, 6.5
