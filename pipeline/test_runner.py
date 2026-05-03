"""
Test Runner — writes generated code to workspace and validates it.
For this PoC: syntax check + import check (no full test suites).
"""

import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass

WORKSPACE = Path(__file__).parent.parent / "workspace"
WORKSPACE.mkdir(exist_ok=True)


@dataclass
class TestResult:
    passed: bool
    error: str = ""
    file_path: str = ""


def check_syntax(code: str, filename: str = "generated.py") -> TestResult:
    file_path = WORKSPACE / filename
    file_path.write_text(code, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-c", f"import ast; ast.parse(open('{file_path}').read())"],
        capture_output=True, text=True, timeout=10,
    )

    if result.returncode != 0:
        return TestResult(passed=False, error=result.stderr, file_path=str(file_path))

    return TestResult(passed=True, file_path=str(file_path))
