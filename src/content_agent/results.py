"""所有工具共用的结构化返回格式。

成功：{"ok": true,  "tool": ..., "data": {...}, "error": null}
失败：{"ok": false, "tool": ..., "data": null, "error": {"code", "message", "retryable", ...}}
"""

from __future__ import annotations

from typing import Any


def ok(tool: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "tool": tool, "data": data, "error": None}


def fail(tool: str, code: str, message: str, retryable: bool = False, **details: Any) -> dict[str, Any]:
    error = {"code": code, "message": message, "retryable": retryable, **details}
    return {"ok": False, "tool": tool, "data": None, "error": error}
