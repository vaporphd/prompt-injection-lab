"""
Cost Guard — global budget cap for the challenge.
Persists to disk so it survives restarts.
"""

import json
from pathlib import Path
from threading import Lock

PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

STATE_FILE = Path(__file__).parent / "data" / "cost_state.json"


class CostGuard:
    def __init__(self, max_cost_usd: float = 2.0):
        self.max_cost_usd = max_cost_usd
        self.total_cost = 0.0
        self.total_tokens = 0
        self.total_requests = 0
        self._lock = Lock()

    def track(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = PRICING.get(model, PRICING["gpt-4o-mini"])
        cost = (
            prompt_tokens * pricing["input"] / 1_000_000
            + completion_tokens * pricing["output"] / 1_000_000
        )
        with self._lock:
            self.total_cost += cost
            self.total_tokens += prompt_tokens + completion_tokens
            self.total_requests += 1
            if self.total_requests % 10 == 0:
                self.save()
        return cost

    def is_exhausted(self) -> bool:
        return self.total_cost >= self.max_cost_usd

    def remaining(self) -> float:
        return max(0, self.max_cost_usd - self.total_cost)

    def save(self):
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "total_requests": self.total_requests,
        }))

    def load(self):
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            self.total_cost = data.get("total_cost", 0)
            self.total_tokens = data.get("total_tokens", 0)
            self.total_requests = data.get("total_requests", 0)
