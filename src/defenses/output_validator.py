"""
Defense Layer 3: Output Validation
Checks LLM output for signs of successful injection — suspicious patterns
that shouldn't appear in legitimate responses.
Analogous to WAF (Web Application Firewall) for SQL injection.
"""

import re

SUSPICIOUS_PATTERNS = [
    (r'(?:перевести|перевод|wire|transfer)\s+(?:оплату|деньги|средства|\d)', "financial_transfer"),
    (r'(?:р/с|расчётный счёт|счёт)\s*\d{10,}', "bank_account"),
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', "email_address"),
    (r'https?://\S*(?:evil|malicious|attack|phish|hack)', "suspicious_url"),
    (r'(?:пароль|password)\S*\s*(?:обновить|сменить|reset|change)', "password_reset"),
    (r'(?:СРОЧНО|URGENT|НЕМЕДЛЕННО|IMMEDIATELY)[:\s]', "urgency_marker"),
    (r'(?:STRONG BUY|ПОКУПАТЬ.*(?:немедленно|срочно|однозначно))', "manipulated_recommendation"),
    (r'(?:безопасн\w+ в любой дозе|safe in any dose|no contraindications)', "dangerous_medical_claim"),
    (r'(?:дети.*любого возраста|children of all ages).*(?:безопасно|safe)', "dangerous_pediatric_claim"),
    (r'(?:10\s*г|10g)\s*(?:в сутки|per day|daily)', "dangerous_dosage"),
]


def validate(output: str, context: str = "") -> dict:
    findings = []

    for pattern, category in SUSPICIOUS_PATTERNS:
        matches = re.findall(pattern, output, re.IGNORECASE)
        if matches:
            findings.append({
                "category": category,
                "matches": matches,
                "pattern": pattern,
            })

    return {
        "is_clean": len(findings) == 0,
        "findings": findings,
        "risk_level": "HIGH" if findings else "LOW",
    }


def validate_and_block(output: str, fallback: str = "Ответ заблокирован системой безопасности — обнаружен подозрительный контент.") -> str:
    result = validate(output)
    if result["is_clean"]:
        return output
    return fallback
