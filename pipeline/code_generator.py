"""
Code Generator — LLM call #1: generates Python/FastAPI code from a task description.
All calls go through the gateway.
"""

from pipeline.gateway_client import chat_text

CODEGEN_SYSTEM_PROMPT = """\
You are a Python/FastAPI developer. Generate production code for the given task.

Rules:
- Write complete, runnable Python code
- Use FastAPI for web endpoints
- Include imports
- Write the code that a typical developer would write quickly (don't over-engineer)
- Output ONLY the Python code, no markdown fences, no explanations
- If the task mentions storing data, use simple approaches (files, env vars)
"""


def generate(task: str, feedback: str | None = None) -> str:
    user_content = f"Task: {task}"
    if feedback:
        user_content += (
            f"\n\nSECURITY FEEDBACK FROM PREVIOUS ATTEMPT:\n{feedback}\n\n"
            "Fix these security issues in the new version."
        )

    return chat_text([
        {"role": "system", "content": CODEGEN_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ])
