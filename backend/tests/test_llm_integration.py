"""
Tests for LLM-dependent functionality with proper mocking.
These tests ensure the LLM integration works correctly without making actual API calls.
"""
import pytest
import json
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Sample valid config that would be returned by LLM
MOCK_LLM_CONFIG = {
    "title": "E-commerce Demo",
    "services": [
        {
            "name": "api-gateway",
            "language": "nodejs",
            "role": "API Gateway",
            "depends_on": [{"service": "order-service"}]
        },
        {
            "name": "order-service",
            "language": "python",
            "role": "Order processing",
            "depends_on": [{"db": "postgres"}]
        }
    ],
    "databases": [{"name": "postgres", "type": "postgresql"}],
    "message_queues": [],
    "telemetry": {
        "trace_rate": 1,
        "error_rate": 0.05,
        "metrics_interval": 10,
        "include_logs": True
    }
}


@pytest.fixture
def mock_llm_response():
    """Mock the LLM to return a valid config."""
    with patch('llm_config_gen.generate_config_from_description') as mock:
        mock.return_value = json.dumps(MOCK_LLM_CONFIG)
        yield mock


@pytest.fixture
def mock_llm_error():
    """Mock the LLM to raise an error."""
    with patch('llm_config_gen.generate_config_from_description') as mock:
        mock.side_effect = ValueError("LLM API error")
        yield mock


@pytest.fixture
def mock_bedrock_client():
    """Mock the Bedrock client to avoid AWS calls."""
    with patch('llm_config_gen._get_bedrock_client') as mock:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "emit_config",
                            "input": MOCK_LLM_CONFIG
                        }
                    ]
                }
            },
            "stopReason": "tool_use"
        }
        mock.return_value = mock_client
        yield mock_client


class TestLLMConfigGeneration:
    """Tests for LLM-based config generation."""

    def test_generate_config_empty_description_raises(self):
        """Test that empty description raises ValueError."""
        from llm_config_gen import generate_config_from_description

        with pytest.raises(ValueError, match="Description must not be empty"):
            generate_config_from_description("")

    def test_generate_config_whitespace_description_raises(self):
        """Test that whitespace-only description raises ValueError."""
        from llm_config_gen import generate_config_from_description

        with pytest.raises(ValueError, match="Description must not be empty"):
            generate_config_from_description("   ")


class TestScenarioGeneration:
    """Tests for LLM-based scenario generation."""

    @pytest.fixture
    def mock_scenario_llm(self):
        """Mock the scenario LLM to return a valid scenario."""
        mock_scenario = {
            "type": "latency_spike",
            "target_services": ["api-gateway"],
            "target_operations": [],
            "parameters": [{"key": "multiplier", "value": 3.0}]
        }
        with patch('scenario_llm_gen.generate_scenario_from_description') as mock:
            mock.return_value = mock_scenario
            yield mock

    def test_scenario_templates_available(self):
        """Test that predefined templates are available without LLM."""
        from scenario_llm_gen import get_predefined_templates

        templates = get_predefined_templates()
        assert len(templates) > 0
        # Verify template structure
        for template in templates:
            assert "name" in template
            assert "description" in template
            assert "category" in template
            # Templates can have either 'modification' or 'cascade_config'
            assert "modification" in template or "cascade_config" in template


class TestConfigWorkerWithMockedLLM:
    """Tests for the background config generation worker with mocked LLM."""

    @pytest.fixture
    def client_with_mocked_llm(self, mock_bedrock_client):
        """Create test client with mocked LLM."""
        from main import app
        return TestClient(app)

    def test_config_job_lifecycle(self, client_with_mocked_llm):
        """Test full config job lifecycle with mocked LLM."""
        client = client_with_mocked_llm

        # Create job
        response = client.post("/generate-config", json={
            "description": "A microservices application with user auth"
        })
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # Job should be pending or running
        status_response = client.get(f"/generate-config/{job_id}")
        assert status_response.status_code == 200
        status = status_response.json()["status"]
        assert status in ["pending", "running", "succeeded", "failed"]

    def test_multiple_config_jobs(self, client_with_mocked_llm):
        """Test creating multiple config jobs."""
        client = client_with_mocked_llm

        job_ids = []
        for i in range(3):
            response = client.post("/generate-config", json={
                "description": f"Test application {i}"
            })
            assert response.status_code == 202
            job_ids.append(response.json()["job_id"])

        # All jobs should be retrievable
        for job_id in job_ids:
            response = client.get(f"/generate-config/{job_id}")
            assert response.status_code == 200


class TestSelectContentFromBlocks:
    """Tests for the content extraction helper function."""

    def test_prefers_tool_use_with_content(self):
        """Tool use with content is preferred over text."""
        from llm_config_gen import _select_content_from_blocks

        tool_payload = {"services": [{"name": "test"}]}
        content, empty_tool = _select_content_from_blocks([
            {"type": "tool_use", "name": "emit_config", "input": tool_payload},
            {"type": "text", "text": '{"different": "content"}'}
        ])

        assert empty_tool is False
        assert json.loads(content) == tool_payload

    def test_falls_back_to_text_when_tool_empty(self):
        """Falls back to text when tool payload is empty."""
        from llm_config_gen import _select_content_from_blocks

        fallback = '{"services": [{"name": "fallback"}]}'
        content, empty_tool = _select_content_from_blocks([
            {"type": "tool_use", "name": "emit_config", "input": {}},
            {"type": "text", "text": fallback}
        ])

        assert empty_tool is True
        assert json.loads(content) == json.loads(fallback)

    def test_handles_text_only(self):
        """Handles responses with only text blocks."""
        from llm_config_gen import _select_content_from_blocks

        text_content = '{"services": []}'
        content, empty_tool = _select_content_from_blocks([
            {"type": "text", "text": text_content}
        ])

        assert content == text_content

    def test_handles_empty_blocks(self):
        """Handles empty block list."""
        from llm_config_gen import _select_content_from_blocks

        content, empty_tool = _select_content_from_blocks([])
        assert content is None
