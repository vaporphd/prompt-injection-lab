"""
Defense Layer 1: Input Sanitization
Strips potentially malicious content from external data before it reaches the LLM.
Analogous to input escaping/parameterization in SQL injection defense.
"""

import re


ZERO_WIDTH_CHARS = (
    "​"  # zero width space
    "‌"  # zero width non-joiner
    "‍"  # zero width joiner
    "‎"  # left-to-right mark
    "‏"  # right-to-left mark
    "⁠"  # word joiner
    "⁡"  # function application
    "⁢"  # invisible times
    "⁣"  # invisible separator
    "⁤"  # invisible plus
    "﻿"  # zero width no-break space (BOM)
    "­"  # soft hyphen
    "͏"  # combining grapheme joiner
    "؜"  # arabic letter mark
    "᠎"  # mongolian vowel separator
)

HIDDEN_CSS_PATTERNS = [
    r'<[^>]+style\s*=\s*"[^"]*(?:display\s*:\s*none|'
    r'visibility\s*:\s*hidden|'
    r'font-size\s*:\s*0|'
    r'opacity\s*:\s*0|'
    r'color\s*:\s*(?:white|#fff|#ffffff|transparent)|'
    r'height\s*:\s*0|'
    r'overflow\s*:\s*hidden|'
    r'position\s*:\s*absolute\s*;\s*left\s*:\s*-\d+)'
    r'[^"]*"[^>]*>.*?</[^>]+>',
]


def strip_html_comments(text: str) -> str:
    return re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)


def strip_hidden_elements(text: str) -> str:
    for pattern in HIDDEN_CSS_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)
    return text


def strip_zero_width(text: str) -> str:
    for char in ZERO_WIDTH_CHARS:
        text = text.replace(char, '')
    return text


def strip_markdown_title_payloads(text: str) -> str:
    def clean_title(match):
        prefix = match.group(1)
        url = match.group(2)
        return f'{prefix}({url})'
    return re.sub(r'(\[[^\]]*\])\((\S+)\s+"[^"]*"\)', clean_title, text)


def sanitize(text: str) -> str:
    text = strip_html_comments(text)
    text = strip_hidden_elements(text)
    text = strip_zero_width(text)
    text = strip_markdown_title_payloads(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
