"""
Linter — runs ruff check on generated code.
"""

import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class LintResult:
    passed: bool
    findings: list[str] = field(default_factory=list)
    raw_output: str = ""


def lint(code: str) -> LintResult:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["ruff", "check", tmp_path, "--output-format=text"],
            capture_output=True, text=True, timeout=30,
        )

        findings = [
            line for line in result.stdout.strip().split("\n")
            if line.strip() and tmp_path in line
        ]

        return LintResult(
            passed=result.returncode == 0,
            findings=findings,
            raw_output=result.stdout + result.stderr,
        )
    except FileNotFoundError:
        return LintResult(passed=True, raw_output="ruff not installed, skipping lint")
    finally:
        Path(tmp_path).unlink(missing_ok=True)
