"""运行 Trace：追加写入 JSONL。不记录 API Key 或完整密钥相关字段。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceWriter:
    def __init__(self, path: Path, *, run_id: str, llm_mode: str, model: str | None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.llm_mode = llm_mode
        self.model = model
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "llm_mode": self.llm_mode,
            "model": self.model,
            "event": event_type,
            **payload,
        }
        # 防御：剔除可能误传入的密钥字段
        for banned in ("api_key", "LLM_API_KEY", "authorization", "Authorization"):
            event.pop(banned, None)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return event
