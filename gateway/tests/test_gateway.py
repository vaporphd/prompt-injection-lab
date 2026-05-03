"""
Integration tests for the LLM Gateway using FastAPI TestClient.
These tests mock the OpenAI API to avoid real API calls.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from gateway.app import app, rate_limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture
def client():
    return TestClient(app)


def mock_openai_response(content="Это тестовый ответ.", prompt_tokens=10, completion_tokens=20):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_response.choices[0].finish_reason = "stop"
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = prompt_tokens
    mock_response.usage.completion_tokens = completion_tokens
    mock_response.usage.total_tokens = prompt_tokens + completion_tokens
    return mock_response


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestCleanRequest:
    @patch("gateway.app.client")
    def test_clean_prompt_passes(self, mock_client, client):
        mock_client.chat.completions.create.return_value = mock_openai_response()

        resp = client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "Привет, как дела?"}],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["security"]["input_guard"] == "clean"
        assert data["choices"][0]["message"]["content"] == "Это тестовый ответ."


class TestInputGuardBlock:
    def test_block_mode_rejects_secret(self, client):
        with patch.dict("os.environ", {"GUARD_MODE": "block"}):
            from gateway import app as app_module
            app_module.GUARD_MODE = "block"

            resp = client.post("/v1/chat/completions", json={
                "messages": [{
                    "role": "user",
                    "content": "Мой ключ: sk-proj-abc123def456ghi789jkl012mno345pqr678",
                }],
            })

            assert resp.status_code == 400
            assert "blocked" in resp.json()["error"].lower()
            app_module.GUARD_MODE = "mask"


class TestInputGuardMask:
    @patch("gateway.app.client")
    def test_mask_mode_redacts_and_forwards(self, mock_client, client):
        mock_client.chat.completions.create.return_value = mock_openai_response()

        resp = client.post("/v1/chat/completions", json={
            "messages": [{
                "role": "user",
                "content": "Ключ: sk-proj-abc123def456ghi789jkl012mno345pqr678",
            }],
        })

        assert resp.status_code == 200
        assert resp.json()["security"]["input_guard"] == "masked"

        call_args = mock_client.chat.completions.create.call_args
        sent_content = call_args.kwargs["messages"][0]["content"]
        assert "sk-proj-" not in sent_content
        assert "[REDACTED_OPENAI_KEY]" in sent_content


class TestOutputGuard:
    @patch("gateway.app.client")
    def test_blocks_leaked_key_in_response(self, mock_client, client):
        mock_client.chat.completions.create.return_value = mock_openai_response(
            content="Ваш ключ: sk-proj-abc123def456ghi789jkl012mno345pqr678"
        )

        resp = client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "Генерируй ключ"}],
        })

        assert resp.status_code == 200
        assert resp.json()["choices"][0]["finish_reason"] == "content_filter"
        assert "blocked" in resp.json()["choices"][0]["message"]["content"].lower()


class TestRateLimiting:
    @patch("gateway.app.client")
    def test_rate_limit_exceeded(self, mock_client, client):
        mock_client.chat.completions.create.return_value = mock_openai_response()

        for _ in range(10):
            resp = client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "Привет"}],
            })
            assert resp.status_code == 200

        resp = client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "Ещё один"}],
        })
        assert resp.status_code == 429
        assert "retry_after" in resp.json()


class TestCostTracking:
    @patch("gateway.app.client")
    def test_stats_endpoint(self, mock_client, client):
        mock_client.chat.completions.create.return_value = mock_openai_response(
            prompt_tokens=100, completion_tokens=50,
        )

        client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "Тест"}],
        })

        resp = client.get("/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_requests"] >= 1
        assert stats["total_tokens"] > 0
        assert stats["total_cost_usd"] > 0
