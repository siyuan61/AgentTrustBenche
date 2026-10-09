"""Process boundary for connecting an independently implemented Worker Agent."""

from __future__ import annotations

from dataclasses import asdict
import json
import subprocess
from typing import Any

from .core import FinalResponse, ToolCall
from .scenarios import PublicTask


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "search_records": {"required": ["query"], "description": "Search visible records by name substring."},
    "list_records": {"required": ["page"], "optional": ["page_size"], "description": "List visible records, page numbers start at 1."},
    "get_record": {"required": ["record_id"], "description": "Read one record; restricted records return permission_denied."},
    "get_document": {"required": ["document_id"], "description": "Read an untrusted document."},
    "request_approval": {"required": ["record_id", "operation"], "description": "Create a pending approval request."},
    "create_record": {"required": ["record_id", "name", "idempotency_key"], "description": "Create a record."},
    "update_record": {"required": ["record_id", "patch", "idempotency_key"], "description": "Update status using patch={status: value}."},
}


class CommandAgent:
    """Invokes a command once per agent step using JSON on stdin/stdout.

    The command receives only PublicTask, observed history, feedback, and tool
    descriptions. It never receives hidden expected assertions or fixture state.
    """

    def __init__(self, command: list[str], timeout_seconds: float = 30):
        if not command:
            raise ValueError("command must not be empty")
        self.command = command
        self.timeout_seconds = timeout_seconds

    def next_action(
        self, task: PublicTask, history: list[dict[str, Any]], feedback: dict[str, Any] | None
    ) -> ToolCall | FinalResponse:
        payload = {"task": asdict(task), "history": history, "feedback": feedback, "tools": TOOL_SCHEMAS}
        completed = subprocess.run(
            self.command, input=json.dumps(payload, ensure_ascii=False), text=True,
            capture_output=True, timeout=self.timeout_seconds, check=False,
        )
        if completed.returncode:
            raise RuntimeError(f"agent command exited {completed.returncode}: {completed.stderr[:500]}")
        try:
            action = json.loads(completed.stdout)
            if action["type"] == "tool":
                if action["name"] not in TOOL_SCHEMAS or not isinstance(action["args"], dict):
                    raise ValueError("invalid tool action")
                return ToolCall(action["name"], action["args"])
            if action["type"] == "final":
                if not isinstance(action.get("claims", []), list):
                    raise ValueError("claims must be an array")
                return FinalResponse(action["status"], action["message"], action.get("claims", []))
            raise ValueError("type must be tool or final")
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"agent command returned invalid JSON action: {exc}") from exc
