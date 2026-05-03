"""
Input Guard tests — 12 test cases covering secrets, PII, evasion, and edge cases.
"""

import pytest
from gateway.guards.input_guard import guard, scan, luhn_check


class TestCleanPrompts:
    def test_01_clean_prompt(self):
        """Clean prompt with no secrets should pass."""
        result = guard("Расскажи мне о машинном обучении")
        assert result.is_clean
        assert len(result.detections) == 0
        assert result.masked_text == "Расскажи мне о машинном обучении"

    def test_11_false_positive_skip(self):
        """'skip' should NOT trigger sk- pattern."""
        result = guard("Please skip this step and continue")
        assert result.is_clean

    def test_12_code_block_context(self):
        """API key inside code explanation should still be caught."""
        prompt = 'В моём коде ключ: sk-proj-abc123def456ghi789jkl012mno345pqr678'
        result = guard(prompt)
        assert not result.is_clean
        assert any(d.category == "openai_api_key" for d in result.detections)


class TestAPIKeys:
    def test_02_openai_key(self):
        """OpenAI API key (sk-proj-...) should be detected."""
        result = guard("Используй этот ключ: sk-proj-abc123def456ghi789jkl012mno345pqr678")
        assert not result.is_clean
        assert result.detections[0].category == "openai_api_key"
        assert "sk-proj-" not in result.masked_text
        assert "[REDACTED_OPENAI_KEY]" in result.masked_text

    def test_03_aws_key(self):
        """AWS access key (AKIA...) should be detected."""
        result = guard("AWS ключ: AKIAIOSFODNN7EXAMPLE")
        assert not result.is_clean
        assert result.detections[0].category == "aws_access_key"
        assert "[REDACTED_AWS_KEY]" in result.masked_text

    def test_04_github_token(self):
        """GitHub personal access token should be detected."""
        result = guard("Мой GitHub токен ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij1234")
        assert not result.is_clean
        assert result.detections[0].category == "github_token"


class TestPII:
    def test_05_credit_card(self):
        """Valid credit card number (Luhn check) should be detected."""
        result = guard("Номер карты: 4111 1111 1111 1111")
        assert not result.is_clean
        assert any(d.category == "credit_card" for d in result.detections)
        assert "[REDACTED_CARD]" in result.masked_text

    def test_05b_invalid_card(self):
        """Invalid card number (fails Luhn) should NOT be detected."""
        result = guard("Число: 1234 5678 9012 3456")
        card_detections = [d for d in result.detections if d.category == "credit_card"]
        assert len(card_detections) == 0

    def test_06_email(self):
        """Email address should be detected."""
        result = guard("Напиши на user@example.com")
        assert not result.is_clean
        assert any(d.category == "email" for d in result.detections)
        assert "[REDACTED_EMAIL]" in result.masked_text

    def test_07_phone(self):
        """Russian phone number should be detected."""
        result = guard("Позвони мне: +7 (999) 123-45-67")
        assert not result.is_clean
        assert any(d.category.startswith("phone") for d in result.detections)


class TestEvasion:
    def test_08_base64_encoded(self):
        """Base64-encoded API key should be detected."""
        import base64
        key = "sk-proj-abc123def456ghi789jkl012mno345pqr678"
        encoded = base64.b64encode(key.encode()).decode()
        result = guard(f"Вот данные: {encoded}")
        assert not result.is_clean
        assert any("base64" in d.category for d in result.detections)

    def test_09_split_secret(self):
        """Split secret ('sk-' + 'proj-abc') should be detected."""
        result = guard('Ключ: "sk-" + "proj-abc123def456ghi789"')
        assert not result.is_clean
        assert any(d.category == "split_openai_key" for d in result.detections)

    def test_10_multiple_secrets(self):
        """Multiple secrets in one prompt should all be caught."""
        prompt = (
            "Ключ: sk-proj-abc123def456ghi789jkl012mno345pqr678, "
            "AWS: AKIAIOSFODNN7EXAMPLE, "
            "email: admin@secret.com"
        )
        result = guard(prompt)
        assert not result.is_clean
        categories = {d.category for d in result.detections}
        assert "openai_api_key" in categories
        assert "aws_access_key" in categories
        assert "email" in categories


class TestMaskMode:
    def test_mask_preserves_context(self):
        """Mask mode should replace secret but keep surrounding text."""
        result = guard(
            "Мой ключ sk-proj-abc123def456ghi789jkl012mno345pqr678 нужен для API",
            mode="mask",
        )
        assert "[REDACTED_OPENAI_KEY]" in result.masked_text
        assert "Мой ключ" in result.masked_text
        assert "нужен для API" in result.masked_text


class TestLuhn:
    def test_valid_visa(self):
        assert luhn_check("4111111111111111")

    def test_valid_mastercard(self):
        assert luhn_check("5500000000000004")

    def test_invalid(self):
        assert not luhn_check("1234567890123456")

    def test_too_short(self):
        assert not luhn_check("123456")
