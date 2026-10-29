"""最小真实 Tool Calling 探测。成功条件：模型返回至少一个可解析的 tool_call。

用法（在项目根目录）：
  .venv\\Scripts\\python.exe scripts\\probe_tool_calling.py

不打印 API Key。结果写入 examples/unit_tests/probe_tool_calling.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from content_agent.config import load_settings
from content_agent.llm import RealLLM
from content_agent.prompts import tool_schemas


def main() -> int:
    settings = load_settings()
    out = {
        "ok": False,
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "thinking": settings.llm_thinking,
        "configured": settings.llm_configured,
    }
    if not settings.llm_configured:
        out["error"] = "LLM_API_KEY 或 LLM_MODEL 未配置"
        _write(out)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 2

    llm = RealLLM(settings)
    messages = [
        {
            "role": "system",
            "content": "你是探测助手。请调用 update_plan 工具，steps 至少包含一个 search_materials 步骤。",
        },
        {
            "role": "user",
            "content": "主题：夏季新品发布。请立刻调用 update_plan。",
        },
    ]
    try:
        response = llm.complete(messages, tool_schemas())
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        _write(out)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    out["response_model"] = response.model
    out["finish_reason"] = response.finish_reason
    out["tool_call_count"] = len(response.tool_calls)
    out["tool_calls"] = [
        {
            "id": tc.id,
            "name": tc.name,
            "parse_error": tc.parse_error,
            "arguments": tc.arguments,
        }
        for tc in response.tool_calls
    ]
    out["ok"] = bool(response.tool_calls) and all(tc.parse_error is None for tc in response.tool_calls)
    _write(out)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


def _write(payload: dict) -> None:
    path = ROOT / "examples" / "unit_tests" / "probe_tool_calling.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
