"""
Execution Loop — orchestrates: generate → lint → test → security review → decide.

Usage (gateway must be running on port 8000):
    python -m pipeline.executor
    python -m pipeline.executor --task 1        # run single task
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from pipeline.code_generator import generate
from pipeline.security_reviewer import review, format_feedback, should_block, max_severity
from pipeline.linter import lint
from pipeline.test_runner import check_syntax

PROJECT_ROOT = Path(__file__).parent.parent
TASKS_DIR = Path(__file__).parent / "tasks"

console = Console()

MAX_ITERATIONS = 3

TASKS = [
    {
        "id": 1,
        "name": "Save Auth Token",
        "file": "task_01_save_token.md",
        "output": "auth_token_storage.py",
    },
    {
        "id": 2,
        "name": "Log All Requests",
        "file": "task_02_log_requests.md",
        "output": "request_logger.py",
    },
    {
        "id": 3,
        "name": "Make API Call",
        "file": "task_03_api_call.md",
        "output": "api_client.py",
    },
]


def load_task(task: dict) -> str:
    return (TASKS_DIR / task["file"]).read_text(encoding="utf-8")


def run_task(task: dict) -> dict:
    task_text = load_task(task)
    console.print(Panel(f"[bold]{task['name']}[/]\n{task_text[:200]}...", title=f"Task #{task['id']}"))

    iterations = []
    feedback = None
    final_code = None
    final_status = "unknown"

    for iteration in range(1, MAX_ITERATIONS + 1):
        console.print(f"\n[cyan]--- Iteration {iteration}/{MAX_ITERATIONS} ---[/]")

        # Step 1: Generate code
        console.print("[yellow]▶ Generating code...[/]")
        try:
            code = generate(task_text, feedback=feedback)
        except Exception as e:
            console.print(f"[red]Generation failed: {e}[/]")
            iterations.append({"iteration": iteration, "step": "generate", "error": str(e)})
            break

        console.print(Syntax(code[:500] + ("..." if len(code) > 500 else ""), "python", theme="monokai"))

        # Step 2: Lint
        console.print("[yellow]▶ Running linter...[/]")
        lint_result = lint(code)
        if not lint_result.passed:
            console.print(f"[red]Lint failed: {lint_result.findings[:3]}[/]")
        else:
            console.print("[green]Lint passed[/]")

        # Step 3: Syntax check
        console.print("[yellow]▶ Checking syntax...[/]")
        test_result = check_syntax(code, task["output"])
        if not test_result.passed:
            console.print(f"[red]Syntax error: {test_result.error}[/]")
            feedback = f"Code has syntax error: {test_result.error}. Fix it."
            iterations.append({
                "iteration": iteration,
                "step": "syntax_check",
                "passed": False,
                "error": test_result.error,
            })
            continue
        console.print("[green]Syntax OK[/]")

        # Step 4: Security review
        console.print("[yellow]▶ Security review (via gateway)...[/]")
        try:
            review_result = review(code)
        except Exception as e:
            console.print(f"[red]Security review failed: {e}[/]")
            iterations.append({"iteration": iteration, "step": "security_review", "error": str(e)})
            break

        severity = max_severity(review_result)
        findings_count = len(review_result.get("findings", []))
        gateway_info = review_result.get("gateway_security", {})

        console.print(f"  Severity: [{'red' if severity in ('critical','high') else 'yellow' if severity in ('medium',) else 'green'}]{severity.upper()}[/]")
        console.print(f"  Findings: {findings_count}")
        console.print(f"  Gateway: input={gateway_info.get('input_guard','?')}, output={gateway_info.get('output_guard','?')}")

        for f in review_result.get("findings", [])[:5]:
            loc = f"L{f['line']}" if f.get("line") else "?"
            console.print(f"    [{f['severity'].upper()}] {f['category']} ({loc}): {f['description']}")

        iteration_data = {
            "iteration": iteration,
            "code_length": len(code),
            "lint_passed": lint_result.passed,
            "lint_findings": len(lint_result.findings),
            "syntax_passed": True,
            "security_severity": severity,
            "security_findings": findings_count,
            "gateway_security": gateway_info,
            "findings": review_result.get("findings", []),
        }
        iterations.append(iteration_data)

        # Step 5: Decision
        if should_block(review_result):
            console.print(f"[red]⛔ BLOCKED — {severity.upper()} issues found. Looping back...[/]")
            feedback = format_feedback(review_result)
            continue
        elif severity in ("medium", "low"):
            console.print(f"[yellow]⚠ WARNING — {severity} issues, proceeding with warnings[/]")
            final_code = code
            final_status = f"passed_with_{severity}_warnings"
            break
        else:
            console.print("[green]✅ CLEAN — no security issues[/]")
            final_code = code
            final_status = "clean"
            break
    else:
        console.print(f"[red]❌ Max iterations ({MAX_ITERATIONS}) reached[/]")
        final_code = code if 'code' in dir() else None
        final_status = "max_iterations_reached"

    return {
        "task_id": task["id"],
        "task_name": task["name"],
        "status": final_status,
        "iterations": iterations,
        "total_iterations": len(iterations),
        "final_code": final_code,
    }


def main():
    parser = argparse.ArgumentParser(description="Day 14: Security Step Pipeline")
    parser.add_argument("--task", type=int, help="Run single task (1-3)")
    args = parser.parse_args()

    console.print(Panel("[bold magenta]Day 14: Security Step in Execution Loop[/]\nAll LLM calls go through Gateway on port 8000"))

    tasks_to_run = TASKS
    if args.task:
        tasks_to_run = [t for t in TASKS if t["id"] == args.task]

    results = []
    for task in tasks_to_run:
        result = run_task(task)
        results.append(result)
        console.print()

    # Summary table
    table = Table(title="Pipeline Results")
    table.add_column("Task", style="cyan")
    table.add_column("Status")
    table.add_column("Iterations", justify="center")
    table.add_column("Final Severity")

    for r in results:
        status_style = {
            "clean": "[green]CLEAN[/]",
            "max_iterations_reached": "[red]FAILED[/]",
        }.get(r["status"], f"[yellow]{r['status']}[/]")

        last_sev = "—"
        if r["iterations"]:
            last = r["iterations"][-1]
            last_sev = last.get("security_severity", "—")

        table.add_row(r["task_name"], status_style, str(r["total_iterations"]), last_sev)

    console.print(table)

    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "results": [{k: v for k, v in r.items() if k != "final_code"} for r in results],
    }

    out_path = PROJECT_ROOT / "reports" / "day14_results.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    console.print(f"\n[green]Results saved to reports/day14_results.json[/]")

    # Gateway stats
    try:
        from pipeline.gateway_client import get_stats
        stats = get_stats()
        console.print(f"\n[magenta]Gateway stats:[/] {stats['total_requests']} requests, "
                       f"${stats['total_cost_usd']:.4f} total cost")
    except Exception:
        pass


if __name__ == "__main__":
    main()
