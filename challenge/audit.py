"""
Audit logging — structured JSONL, downloadable for reports.
"""

import json
from datetime import datetime
from pathlib import Path
from threading import Lock

LOG_DIR = Path(__file__).parent / "data"
LOG_FILE = LOG_DIR / "audit.jsonl"


class AuditLog:
    def __init__(self):
        LOG_DIR.mkdir(exist_ok=True)
        self.log_path = str(LOG_FILE)
        self._lock = Lock()
        self._stats = {"total": 0, "successful": 0, "ips": set(), "flags": set()}
        self._load_stats()

    def _load_stats(self):
        if not LOG_FILE.exists():
            return
        for line in LOG_FILE.read_text(encoding="utf-8").strip().split("\n"):
            if not line:
                continue
            try:
                entry = json.loads(line)
                self._stats["total"] += 1
                self._stats["ips"].add(entry.get("client_ip", ""))
                leaks = entry.get("leaks", [])
                if leaks:
                    self._stats["successful"] += 1
                    self._stats["flags"].update(leaks)
            except json.JSONDecodeError:
                continue

    def append(self, entry: dict):
        with self._lock:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._stats["total"] += 1
            self._stats["ips"].add(entry.get("client_ip", ""))
            if entry.get("leaks"):
                self._stats["successful"] += 1
                self._stats["flags"].update(entry["leaks"])

    def get_stats(self) -> dict:
        return {
            "total": self._stats["total"],
            "unique_ips": len(self._stats["ips"]),
            "successful": self._stats["successful"],
            "flags_found": sorted(self._stats["flags"]),
        }


def log_attempt(
    audit: AuditLog,
    request_id: str,
    client_ip: str,
    message: str,
    response: str,
    tokens: int,
    cost: float,
    leaks: list[str],
):
    audit.append({
        "timestamp": datetime.now().isoformat(),
        "request_id": request_id,
        "client_ip": client_ip,
        "message": message,
        "response": response,
        "tokens": tokens,
        "cost_usd": round(cost, 6),
        "leaks": leaks,
        "leaked": bool(leaks),
    })
