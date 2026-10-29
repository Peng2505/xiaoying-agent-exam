"""LLM 客户端：真实 OpenAI 兼容接口 + Mock（仅流程验证）。

真实客户端默认关闭 DeepSeek thinking，避免思考模式与 Tool Calling 的额外协议负担。
本模块不执行任何业务工具。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from content_agent.config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments_raw: str
    arguments: dict[str, Any] | None
    parse_error: str | None = None


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_assistant_message: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    finish_reason: str | None = None


class LLMClient(Protocol):
    mode: str
    model_name: str

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        ...


def _parse_tool_calls(message: Any) -> tuple[list[ToolCall], dict[str, Any]]:
    raw = {
        "role": "assistant",
        "content": getattr(message, "content", None),
    }
    # DeepSeek thinking 关闭时通常无 reasoning_content；若存在则原样保留以便兼容。
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:
        raw["reasoning_content"] = reasoning

    tool_calls: list[ToolCall] = []
    api_calls = getattr(message, "tool_calls", None) or []
    if api_calls:
        raw["tool_calls"] = []
        for tc in api_calls:
            fn = tc.function
            raw_args = fn.arguments or "{}"
            parsed: dict[str, Any] | None
            err: str | None
            try:
                loaded = json.loads(raw_args)
                if not isinstance(loaded, dict):
                    parsed = None
                    err = "工具参数 JSON 必须是对象"
                else:
                    parsed = loaded
                    err = None
            except json.JSONDecodeError as exc:
                parsed = None
                err = f"工具参数 JSON 解析失败：{exc}"
            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=fn.name,
                    arguments_raw=raw_args,
                    arguments=parsed,
                    parse_error=err,
                )
            )
            raw["tool_calls"].append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": fn.name, "arguments": raw_args},
                }
            )
    return tool_calls, raw


class RealLLM:
    mode = "real"

    def __init__(self, settings: Settings):
        if not settings.llm_configured:
            raise RuntimeError("未配置 LLM_API_KEY / LLM_MODEL，无法使用真实模型")
        from openai import OpenAI

        self.settings = settings
        self.model_name = settings.llm_model
        self._client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0,
        }
        # DeepSeek：非思考模式。官方示例使用 extra_body.thinking.type=disabled
        if self.settings.llm_thinking == "disabled":
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        else:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        tool_calls, raw = _parse_tool_calls(message)
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            raw_assistant_message=raw,
            model=getattr(response, "model", None) or self.model_name,
            finish_reason=response.choices[0].finish_reason,
        )


class MockLLM:
    """按预设脚本返回 tool_calls。仅验证流程，不得作为真实决策证据。"""

    mode = "mock"

    def __init__(self, script: list[dict[str, Any]], model_name: str = "mock-llm"):
        self.model_name = model_name
        self._script = list(script)
        self._index = 0

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        if self._index >= len(self._script):
            return LLMResponse(
                content="mock script exhausted",
                tool_calls=[],
                raw_assistant_message={"role": "assistant", "content": "mock script exhausted"},
                model=self.model_name,
                finish_reason="stop",
            )
        item = self._script[self._index]
        self._index += 1
        name = item["name"]
        args = item.get("arguments", {})
        call_id = item.get("id", f"mock_call_{self._index}")
        raw_args = json.dumps(args, ensure_ascii=False)
        tc = ToolCall(id=call_id, name=name, arguments_raw=raw_args, arguments=args)
        raw = {
            "role": "assistant",
            "content": item.get("content"),
            "tool_calls": [
                {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw_args}}
            ],
        }
        return LLMResponse(
            content=item.get("content"),
            tool_calls=[tc],
            raw_assistant_message=raw,
            model=self.model_name,
            finish_reason="tool_calls",
        )


class CompletePathMockLLM:
    """确定性完整成功路径 Mock：update_plan → search → generate → estimate → save → finish。

    明确标记为模拟模式（mode=mock），仅用于离线流程验证，不得作为真实模型自主决策证据。
    动态 ID（material_ids / script_id / estimate_id）从对话中上一轮工具观察解析，不硬编码随机值。
    """

    mode = "mock"

    def __init__(self, model_name: str = "mock-llm-complete-path"):
        self.model_name = model_name
        self._index = 0

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self._index += 1
        step = self._index
        if step == 1:
            return self._emit(
                "update_plan",
                {
                    "reason": "mock complete-path: create plan",
                    "steps": [
                        {
                            "step_id": "s1",
                            "name": "检索素材",
                            "tool": "search_materials",
                            "depends_on": [],
                        },
                        {
                            "step_id": "s2",
                            "name": "生成脚本",
                            "tool": "generate_script",
                            "depends_on": ["s1"],
                        },
                        {
                            "step_id": "s3",
                            "name": "估算成本",
                            "tool": "estimate_cost",
                            "depends_on": ["s2"],
                        },
                        {
                            "step_id": "s4",
                            "name": "保存方案",
                            "tool": "save_plan",
                            "depends_on": ["s3"],
                        },
                    ],
                },
            )
        if step == 2:
            return self._emit(
                "search_materials",
                {
                    "step_id": "s1",
                    "source": "primary",
                    "limit": 3,
                    "reason": "mock complete-path: search",
                },
            )
        if step == 3:
            data = self._latest_ok_data(messages, "search_materials")
            material_ids = list((data or {}).get("material_ids") or [])
            return self._emit(
                "generate_script",
                {
                    "step_id": "s2",
                    "material_ids": material_ids,
                    "format": "graphic",
                    "reason": "mock complete-path: generate",
                },
            )
        if step == 4:
            data = self._latest_ok_data(messages, "generate_script")
            script_id = (data or {}).get("script_id")
            return self._emit(
                "estimate_cost",
                {
                    "step_id": "s3",
                    "script_id": script_id,
                    "reason": "mock complete-path: estimate",
                },
            )
        if step == 5:
            script = self._latest_ok_data(messages, "generate_script") or {}
            estimate = self._latest_ok_data(messages, "estimate_cost") or {}
            return self._emit(
                "save_plan",
                {
                    "step_id": "s4",
                    "script_id": script.get("script_id"),
                    "estimate_id": estimate.get("estimate_id"),
                    "reason": "mock complete-path: save",
                },
            )
        if step == 6:
            return self._emit(
                "finish",
                {
                    "status": "completed",
                    "summary": "mock complete-path finished（模拟模式，非真实决策证据）",
                },
            )
        return LLMResponse(
            content="mock complete-path exhausted",
            tool_calls=[],
            raw_assistant_message={
                "role": "assistant",
                "content": "mock complete-path exhausted",
            },
            model=self.model_name,
            finish_reason="stop",
        )

    def _emit(self, name: str, args: dict[str, Any]) -> LLMResponse:
        call_id = f"mock_complete_{self._index}"
        raw_args = json.dumps(args, ensure_ascii=False)
        tc = ToolCall(id=call_id, name=name, arguments_raw=raw_args, arguments=args)
        raw = {
            "role": "assistant",
            "content": f"[MOCK] {name}",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": raw_args},
                }
            ],
        }
        return LLMResponse(
            content=f"[MOCK] {name}",
            tool_calls=[tc],
            raw_assistant_message=raw,
            model=self.model_name,
            finish_reason="tool_calls",
        )

    @staticmethod
    def _latest_ok_data(messages: list[dict[str, Any]], tool: str) -> dict[str, Any] | None:
        for msg in reversed(messages):
            if msg.get("role") != "tool":
                continue
            try:
                obs = json.loads(msg.get("content") or "{}")
            except json.JSONDecodeError:
                continue
            if obs.get("ok") and obs.get("tool") == tool and isinstance(obs.get("data"), dict):
                return obs["data"]
        return None


def build_llm(
    settings: Settings,
    mode: str = "real",
    mock_script: list[dict[str, Any]] | None = None,
) -> LLMClient:
    if mode == "mock":
        # 显式脚本优先；否则走完整确定性成功路径（仍为模拟模式）
        if mock_script is not None:
            return MockLLM(mock_script)
        return CompletePathMockLLM()
    return RealLLM(settings)
