"""
Security Reviewer — LLM call #2: reviews generated code for security vulnerabilities.
Uses a separate security-focused system prompt. All calls go through the gateway.
"""

import json

from pipeline.gateway_client import chat, get_security_info
from pipeline.security_prompt import SECURITY_REVIEW_SYSTEM_PROMPT


def review(code: str) -> dict:
    numbered_code = "\n".join(
        f"{i+1}: {line}" for i, line in enumerate(code.split("\n"))
    )

    data = chat([
        {"role": "system", "content": SECURITY_REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": f"Review this code:\n\n{numbered_code}"},
    ])

    response_text = data["choices"][0]["message"]["content"]
    gateway_security = get_security_info(data)

    try:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(response_text[start:end])
        else:
            result = {
                "findings": [],
                "overall_severity": "clean",
                "summary": "Could not parse review response.",
            }
    except json.JSONDecodeError:
        result = {
            "findings": [{"severity": "medium", "category": "parse_error",
                          "description": f"Raw response: {response_text[:200]}",
                          "fix": "N/A", "line": None}],
            "overall_severity": "medium",
            "summary": "Failed to parse security review JSON.",
        }

    result["gateway_security"] = gateway_security
    return result


def format_feedback(review_result: dict) -> str:
    lines = []
    for f in review_result.get("findings", []):
        loc = f"line {f['line']}" if f.get("line") else "general"
        lines.append(f"[{f['severity'].upper()}] {f['category']} ({loc}): {f['description']}. Fix: {f['fix']}")
    return "\n".join(lines)


def max_severity(review_result: dict) -> str:
    return review_result.get("overall_severity", "clean")


def should_block(review_result: dict) -> bool:
    sev = max_severity(review_result)
    return sev in ("critical", "high")
