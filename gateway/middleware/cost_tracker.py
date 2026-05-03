"""
Cost Tracker — counts tokens and logs cost per request.
"""

from dataclasses import dataclass, field
from datetime import datetime

MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},       # per 1M tokens
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}


@dataclass
class RequestCost:
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: str


@dataclass
class CostTracker:
    requests: list[RequestCost] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0

    def track(self, model: str, prompt_tokens: int, completion_tokens: int) -> RequestCost:
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o-mini"])

        cost = (
            prompt_tokens * pricing["input"] / 1_000_000
            + completion_tokens * pricing["output"] / 1_000_000
        )

        entry = RequestCost(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=round(cost, 6),
            timestamp=datetime.now().isoformat(),
        )

        self.requests.append(entry)
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost_usd += cost

        return entry

    def stats(self) -> dict:
        return {
            "total_requests": len(self.requests),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "recent_requests": [
                {
                    "model": r.model,
                    "tokens": r.total_tokens,
                    "cost": r.cost_usd,
                    "time": r.timestamp,
                }
                for r in self.requests[-10:]
            ],
        }
