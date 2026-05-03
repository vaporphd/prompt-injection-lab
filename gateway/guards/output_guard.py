"""
Output Guard — checks LLM responses before returning to user.

Detects:
- Hallucinated/leaked API keys and secrets
- System prompt leakage
- Suspicious URLs (IP-based, known bad TLDs)
- Dangerous shell commands
"""

import re
from dataclasses import dataclass, field


@dataclass
class OutputFinding:
    category: str
    match: str
    severity: str  # "high", "medium", "low"


@dataclass
class OutputGuardResult:
    is_clean: bool
    findings: list[OutputFinding] = field(default_factory=list)
    blocked: bool = False

    @property
    def severity(self) -> str:
        if not self.findings:
            return "none"
        severities = [f.severity for f in self.findings]
        if "high" in severities:
            return "high"
        if "medium" in severities:
            return "medium"
        return "low"


LEAKED_SECRET_PATTERNS = [
    (r'\bsk-proj-[A-Za-z0-9_-]{20,}', "leaked_openai_key", "high"),
    (r'\bsk-[A-Za-z0-9_-]{20,}', "leaked_openai_key", "high"),
    (r'\bAKIA[0-9A-Z]{16}\b', "leaked_aws_key", "high"),
    (r'\bghp_[A-Za-z0-9]{36,}\b', "leaked_github_token", "high"),
    (r'\bxoxb-[0-9]{10,}-[A-Za-z0-9-]+', "leaked_slack_token", "high"),
    (r'(?:Bearer|Authorization:)\s+[A-Za-z0-9_\-/.+=]{20,}', "leaked_bearer_token", "high"),
]

SUSPICIOUS_URL_PATTERNS = [
    (r'https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?', "ip_based_url", "medium"),
    (r'https?://[^\s]*\.(?:tk|ml|ga|cf|gq|xyz\.)', "suspicious_tld_url", "medium"),
    (r'https?://[^\s]*(?:evil|malicious|phish|hack|attack)', "known_bad_url", "high"),
]

DANGEROUS_COMMAND_PATTERNS = [
    (r'(?:sudo\s+)?rm\s+-[rf]{1,2}(?:\s+[/~])', "destructive_rm", "high"),
    (r'curl\s+[^\s]+\s*\|\s*(?:ba)?sh', "curl_pipe_shell", "high"),
    (r'wget\s+[^\s]+\s*(?:&&|\|)\s*(?:ba)?sh', "wget_pipe_shell", "high"),
    (r'chmod\s+[0-7]*777', "world_writable", "medium"),
    (r'>\s*/etc/', "overwrite_etc", "high"),
    (r'(?:DROP|DELETE\s+FROM|TRUNCATE)\s+', "sql_destructive", "medium"),
]


def check_system_prompt_leak(response: str, system_prompt: str | None = None) -> list[OutputFinding]:
    if not system_prompt:
        return []

    findings = []
    lines = system_prompt.strip().split("\n")
    significant_lines = [l.strip() for l in lines if len(l.strip()) > 20]

    leaked_count = sum(1 for line in significant_lines if line in response)
    if leaked_count >= 2 or (significant_lines and leaked_count == len(significant_lines)):
        findings.append(OutputFinding(
            category="system_prompt_leak",
            match=f"{leaked_count} lines of system prompt detected in output",
            severity="high",
        ))

    return findings


def scan(response: str, system_prompt: str | None = None) -> list[OutputFinding]:
    findings = []

    all_patterns = (
        LEAKED_SECRET_PATTERNS
        + SUSPICIOUS_URL_PATTERNS
        + DANGEROUS_COMMAND_PATTERNS
    )

    for pattern, category, severity in all_patterns:
        for match in re.finditer(pattern, response, re.IGNORECASE):
            findings.append(OutputFinding(
                category=category,
                match=match.group(),
                severity=severity,
            ))

    findings.extend(check_system_prompt_leak(response, system_prompt))

    return findings


def guard(response: str, system_prompt: str | None = None, block_on_high: bool = True) -> OutputGuardResult:
    findings = scan(response, system_prompt)

    if not findings:
        return OutputGuardResult(is_clean=True)

    should_block = block_on_high and any(f.severity == "high" for f in findings)

    return OutputGuardResult(
        is_clean=False,
        findings=findings,
        blocked=should_block,
    )
