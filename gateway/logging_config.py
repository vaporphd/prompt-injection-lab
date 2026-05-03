"""
Structured audit logging — all requests/responses logged as JSONL.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

AUDIT_LOG = LOG_DIR / "audit.jsonl"


def get_audit_logger() -> logging.Logger:
    logger = logging.getLogger("gateway.audit")
    if not logger.handlers:
        handler = logging.FileHandler(AUDIT_LOG, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


_audit = get_audit_logger()


def log_request(
    client_ip: str,
    messages: list[dict],
    input_guard_result: dict | None = None,
    output_guard_result: dict | None = None,
    response_text: str | None = None,
    blocked: bool = False,
    block_reason: str | None = None,
    cost: dict | None = None,
):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "client_ip": client_ip,
        "messages_count": len(messages),
        "user_message_preview": next(
            (m["content"][:100] for m in reversed(messages) if m["role"] == "user"),
            None,
        ),
        "blocked": blocked,
        "block_reason": block_reason,
        "input_guard": input_guard_result,
        "output_guard": output_guard_result,
        "response_preview": response_text[:200] if response_text else None,
        "cost": cost,
    }
    _audit.info(json.dumps(entry, ensure_ascii=False))
