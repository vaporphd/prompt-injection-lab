"""
Input Guard — detects and masks secrets/PII in user prompts before they reach the LLM.

Two modes:
- BLOCK: reject the request entirely, return warning
- MASK: replace secrets with [REDACTED_*] placeholders, forward to LLM
"""

import re
import base64
from dataclasses import dataclass, field


@dataclass
class Detection:
    category: str
    value: str
    masked: str
    start: int
    end: int


@dataclass
class GuardResult:
    is_clean: bool
    detections: list[Detection] = field(default_factory=list)
    original_text: str = ""
    masked_text: str = ""
    mode: str = "block"

    @property
    def summary(self) -> str:
        if self.is_clean:
            return "clean"
        cats = set(d.category for d in self.detections)
        return f"detected: {', '.join(sorted(cats))}"


SECRET_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, category, mask_label)
    # OpenAI keys
    (r'\bsk-proj-[A-Za-z0-9_-]{20,}', "openai_api_key", "[REDACTED_OPENAI_KEY]"),
    (r'\bsk-[A-Za-z0-9_-]{20,}', "openai_api_key", "[REDACTED_OPENAI_KEY]"),
    # AWS keys
    (r'\bAKIA[0-9A-Z]{16}\b', "aws_access_key", "[REDACTED_AWS_KEY]"),
    (r'\b[A-Za-z0-9/+=]{40}\b(?=.*AKIA)', "aws_secret_key", "[REDACTED_AWS_SECRET]"),
    # GitHub tokens
    (r'\bghp_[A-Za-z0-9]{36,}\b', "github_token", "[REDACTED_GITHUB_TOKEN]"),
    (r'\bgho_[A-Za-z0-9]{36,}\b', "github_token", "[REDACTED_GITHUB_TOKEN]"),
    (r'\bghs_[A-Za-z0-9]{36,}\b', "github_token", "[REDACTED_GITHUB_TOKEN]"),
    # Slack tokens
    (r'\bxoxb-[0-9]{10,}-[A-Za-z0-9-]+', "slack_token", "[REDACTED_SLACK_TOKEN]"),
    (r'\bxoxp-[0-9]{10,}-[A-Za-z0-9-]+', "slack_token", "[REDACTED_SLACK_TOKEN]"),
    # Generic long tokens/secrets
    (r'\b(?:token|secret|password|api_key|apikey)\s*[=:]\s*["\']?([A-Za-z0-9_\-/.+=]{20,})["\']?',
     "generic_secret", "[REDACTED_SECRET]"),
]

PII_PATTERNS: list[tuple[str, str, str]] = [
    # Credit card numbers (13-19 digits, possibly with spaces/dashes)
    (r'\b(?:\d[ -]*?){13,19}\b', "credit_card", "[REDACTED_CARD]"),
    # Email addresses
    (r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', "email", "[REDACTED_EMAIL]"),
    # Phone numbers (international)
    (r'(?:\+7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}', "phone_ru", "[REDACTED_PHONE]"),
    (r'\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{2,4}', "phone_intl", "[REDACTED_PHONE]"),
]

SPLIT_SECRET_PATTERNS: list[tuple[str, str, str]] = [
    # "sk-" + "proj-abc123"
    (r'["\']sk-["\']?\s*[\+\.\s]+\s*["\']?(?:proj-)?[A-Za-z0-9_-]{5,}',
     "split_openai_key", "[REDACTED_SPLIT_KEY]"),
    # Variations: sk- concatenated with proj-
    (r'sk-\s*\+?\s*proj-[A-Za-z0-9_-]{5,}',
     "split_openai_key", "[REDACTED_SPLIT_KEY]"),
]


def luhn_check(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def check_base64_secrets(text: str) -> list[Detection]:
    detections = []
    b64_pattern = re.compile(r'(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{20,}={0,2}(?![A-Za-z0-9+/=])')

    for match in b64_pattern.finditer(text):
        b64_str = match.group()
        try:
            decoded = base64.b64decode(b64_str).decode("utf-8", errors="ignore")
        except Exception:
            continue

        for pattern, category, mask in SECRET_PATTERNS[:6]:
            if re.search(pattern, decoded):
                detections.append(Detection(
                    category=f"base64_{category}",
                    value=b64_str,
                    masked="[REDACTED_BASE64_SECRET]",
                    start=match.start(),
                    end=match.end(),
                ))
                break

    return detections


def scan(text: str) -> list[Detection]:
    detections = []

    for pattern, category, mask in SECRET_PATTERNS:
        for match in re.finditer(pattern, text):
            detections.append(Detection(
                category=category,
                value=match.group(),
                masked=mask,
                start=match.start(),
                end=match.end(),
            ))

    for pattern, category, mask in PII_PATTERNS:
        for match in re.finditer(pattern, text):
            value = match.group()
            if category == "credit_card":
                clean = re.sub(r'[\s-]', '', value)
                if not luhn_check(clean):
                    continue
            detections.append(Detection(
                category=category,
                value=value,
                masked=mask,
                start=match.start(),
                end=match.end(),
            ))

    for pattern, category, mask in SPLIT_SECRET_PATTERNS:
        for match in re.finditer(pattern, text):
            detections.append(Detection(
                category=category,
                value=match.group(),
                masked=mask,
                start=match.start(),
                end=match.end(),
            ))

    detections.extend(check_base64_secrets(text))

    # Deduplicate overlapping detections (keep longer match)
    detections.sort(key=lambda d: (d.start, -(d.end - d.start)))
    filtered = []
    last_end = -1
    for d in detections:
        if d.start >= last_end:
            filtered.append(d)
            last_end = d.end

    return filtered


def mask_text(text: str, detections: list[Detection]) -> str:
    result = []
    pos = 0
    for d in sorted(detections, key=lambda x: x.start):
        result.append(text[pos:d.start])
        result.append(d.masked)
        pos = d.end
    result.append(text[pos:])
    return "".join(result)


def guard(text: str, mode: str = "block") -> GuardResult:
    detections = scan(text)

    if not detections:
        return GuardResult(is_clean=True, original_text=text, masked_text=text, mode=mode)

    masked = mask_text(text, detections)
    return GuardResult(
        is_clean=False,
        detections=detections,
        original_text=text,
        masked_text=masked,
        mode=mode,
    )
