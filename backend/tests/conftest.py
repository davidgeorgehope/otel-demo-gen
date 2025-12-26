"""
Pytest fixtures for otel-demo-gen tests.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_schema import (
    ScenarioConfig, Service, ServiceDependency, DbDependency,
    Database, Telemetry, LatencyConfig, Operation, BusinessDataField
)


@pytest.fixture
def minimal_config():
    """Minimal valid scenario configuration."""
    return {
        "services": [
            {
                "name": "test-service",
                "language": "python",
                "depends_on": []
            }
        ],
        "telemetry": {
            "trace_rate": 1,
            "error_rate": 0.1,
            "metrics_interval": 10,
            "include_logs": True
        }
    }


@pytest.fixture
def minimal_scenario_config(minimal_config):
    """Minimal ScenarioConfig object."""
    return ScenarioConfig(**minimal_config)


@pytest.fixture
def multi_service_config():
    """Configuration with multiple services and dependencies."""
    return {
        "services": [
            {
                "name": "frontend",
                "language": "javascript",
                "depends_on": [
                    {"service": "api-gateway", "protocol": "http"}
                ]
            },
            {
                "name": "api-gateway",
                "language": "go",
                "depends_on": [
                    {"service": "user-service", "protocol": "grpc"},
                    {"db": "postgres-main"}
                ]
            },
            {
                "name": "user-service",
                "language": "python",
                "depends_on": [
                    {"db": "postgres-main"}
                ]
            }
        ],
        "databases": [
            {"name": "postgres-main", "type": "postgres"}
        ],
        "telemetry": {
            "trace_rate": 5,
            "error_rate": 0.05,
            "metrics_interval": 10,
            "include_logs": True
        }
    }


@pytest.fixture
def multi_service_scenario_config(multi_service_config):
    """Multi-service ScenarioConfig object."""
    return ScenarioConfig(**multi_service_config)


@pytest.fixture
def config_with_business_data():
    """Configuration with business data fields."""
    return {
        "services": [
            {
                "name": "order-service",
                "language": "java",
                "operations": [
                    {
                        "name": "CreateOrder",
                        "span_name": "POST /orders",
                        "business_data": [
                            {"name": "order_id", "type": "string", "pattern": "ORD-{uuid}"},
                            {"name": "amount", "type": "number", "min_value": 10.0, "max_value": 1000.0},
                            {"name": "quantity", "type": "integer", "min_value": 1, "max_value": 100},
                            {"name": "is_express", "type": "boolean"},
                            {"name": "status", "type": "enum", "values": ["pending", "confirmed", "shipped"]}
                        ]
                    }
                ],
                "depends_on": []
            }
        ],
        "telemetry": {
            "trace_rate": 1,
            "error_rate": 0.0,
            "metrics_interval": 10,
            "include_logs": True
        }
    }


@pytest.fixture
def config_with_invalid_minmax():
    """Configuration with min > max for testing validation."""
    return {
        "services": [
            {
                "name": "test-service",
                "language": "python",
                "operations": [
                    {
                        "name": "TestOp",
                        "span_name": "GET /test",
                        "business_data": [
                            {"name": "value", "type": "number", "min_value": 100.0, "max_value": 10.0},
                            {"name": "count", "type": "integer", "min_value": 50, "max_value": 5}
                        ]
                    }
                ],
                "depends_on": []
            }
        ],
        "telemetry": {
            "trace_rate": 1,
            "error_rate": 0.0,
            "metrics_interval": 10,
            "include_logs": True
        }
    }


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for testing without network calls."""
    with patch('httpx.Client') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_async_httpx_client():
    """Mock async httpx client for FastAPI testing."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = MagicMock(return_value=None)
        yield mock_client


# --- LLM Mocking Fixtures ---

MOCK_LLM_CONFIG_RESPONSE = {
    "title": "Test Application",
    "services": [
        {
            "name": "api-service",
            "language": "python",
            "role": "API backend",
            "depends_on": []
        }
    ],
    "databases": [],
    "message_queues": [],
    "telemetry": {
        "trace_rate": 1,
        "error_rate": 0.05,
        "metrics_interval": 10,
        "include_logs": True
    }
}


@pytest.fixture
def mock_bedrock_client():
    """Mock AWS Bedrock client to avoid actual LLM calls."""
    import json
    with patch('llm_config_gen._get_bedrock_client') as mock:
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "emit_config",
                            "input": MOCK_LLM_CONFIG_RESPONSE
                        }
                    ]
                }
            },
            "stopReason": "tool_use"
        }
        mock.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_generate_config():
    """Mock the generate_config_from_description function directly."""
    import json
    with patch('main.generate_config_from_description') as mock:
        mock.return_value = json.dumps(MOCK_LLM_CONFIG_RESPONSE)
        yield mock


@pytest.fixture
def mock_generate_scenario():
    """Mock the generate_scenario_from_description function."""
    mock_scenario = {
        "type": "latency_spike",
        "target_services": ["api-service"],
        "target_operations": [],
        "parameters": [{"key": "multiplier", "value": 2.0}],
        "contextual_patterns": [],
        "ramp_up_seconds": 0,
        "ramp_down_seconds": 0
    }
    with patch('main.generate_scenario_from_description') as mock:
        mock.return_value = mock_scenario
        yield mock
