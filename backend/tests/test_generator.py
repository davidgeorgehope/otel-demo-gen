"""
Tests for the TelemetryGenerator class.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_schema import ScenarioConfig, Operation, BusinessDataField
from generator import TelemetryGenerator


class TestFormatAttributes:
    """Tests for _format_attributes method."""

    def test_format_string_attribute(self, minimal_scenario_config, mock_httpx_client):
        """Test formatting string attributes."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        result = generator._format_attributes({"key": "value"})
        assert result == [{"key": "key", "value": {"stringValue": "value"}}]

    def test_format_int_attribute(self, minimal_scenario_config, mock_httpx_client):
        """Test formatting integer attributes."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        result = generator._format_attributes({"count": 42})
        assert result == [{"key": "count", "value": {"intValue": "42"}}]

    def test_format_float_attribute(self, minimal_scenario_config, mock_httpx_client):
        """Test formatting float attributes."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        result = generator._format_attributes({"rate": 0.5})
        assert result == [{"key": "rate", "value": {"doubleValue": 0.5}}]

    def test_format_bool_attribute(self, minimal_scenario_config, mock_httpx_client):
        """Test formatting boolean attributes."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        result = generator._format_attributes({"enabled": True})
        assert result == [{"key": "enabled", "value": {"boolValue": True}}]

    def test_format_mixed_attributes(self, minimal_scenario_config, mock_httpx_client):
        """Test formatting mixed attribute types."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        attrs = {
            "name": "test",
            "count": 10,
            "rate": 0.75,
            "active": False
        }
        result = generator._format_attributes(attrs)
        assert len(result) == 4

        # Convert to dict for easier checking
        result_dict = {item["key"]: item["value"] for item in result}
        assert result_dict["name"] == {"stringValue": "test"}
        assert result_dict["count"] == {"intValue": "10"}
        assert result_dict["rate"] == {"doubleValue": 0.75}
        assert result_dict["active"] == {"boolValue": False}


class TestFindEntryPoints:
    """Tests for _find_entry_points method."""

    def test_single_service_is_entry_point(self, minimal_scenario_config, mock_httpx_client):
        """Single service with no dependencies is entry point."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        entry_points = generator._find_entry_points()
        assert len(entry_points) == 1
        assert entry_points[0].name == "test-service"

    def test_frontend_is_entry_point(self, multi_service_scenario_config, mock_httpx_client):
        """Frontend service (not a dependency) is entry point."""
        generator = TelemetryGenerator(
            config=multi_service_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        entry_points = generator._find_entry_points()
        assert len(entry_points) == 1
        assert entry_points[0].name == "frontend"

    def test_empty_services_rejected_by_validation(self, mock_httpx_client):
        """Empty services list is rejected by Pydantic validation."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="At least one service is required"):
            ScenarioConfig(
                services=[],
                telemetry={"trace_rate": 1, "error_rate": 0, "metrics_interval": 10, "include_logs": True}
            )


class TestGenerateSpans:
    """Tests for generate_spans method."""

    def test_generate_spans_returns_dict(self, minimal_scenario_config, mock_httpx_client):
        """generate_spans returns dictionary keyed by service name."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        spans = generator.generate_spans()
        assert isinstance(spans, dict)
        assert "test-service" in spans

    def test_generate_spans_creates_trace_id(self, minimal_scenario_config, mock_httpx_client):
        """All spans share the same trace ID."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        spans = generator.generate_spans()
        if spans.get("test-service"):
            trace_id = spans["test-service"][0]["traceId"]
            assert len(trace_id) == 32  # 16 bytes = 32 hex chars

    def test_generate_spans_empty_services_rejected(self, mock_httpx_client):
        """Empty services is rejected by Pydantic validation."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="At least one service is required"):
            ScenarioConfig(
                services=[],
                telemetry={"trace_rate": 1, "error_rate": 0, "metrics_interval": 10, "include_logs": True}
            )


class TestBusinessDataGeneration:
    """Tests for _generate_business_data_attributes method."""

    def test_business_data_with_invalid_minmax(self, config_with_invalid_minmax, mock_httpx_client):
        """Business data with min > max should swap values and not crash."""
        config = ScenarioConfig(**config_with_invalid_minmax)
        generator = TelemetryGenerator(config=config, otlp_endpoint="http://localhost:4318")

        operation = config.services[0].operations[0]
        attrs = generator._generate_business_data_attributes(operation)

        # Should not crash and should produce values
        assert "value" in attrs
        assert "count" in attrs
        # Values should be within swapped range
        assert 10.0 <= attrs["value"] <= 100.0
        assert 5 <= attrs["count"] <= 50

    def test_business_data_string_pattern(self, config_with_business_data, mock_httpx_client):
        """String patterns are processed correctly."""
        config = ScenarioConfig(**config_with_business_data)
        generator = TelemetryGenerator(config=config, otlp_endpoint="http://localhost:4318")

        operation = config.services[0].operations[0]
        attrs = generator._generate_business_data_attributes(operation)

        assert "order_id" in attrs
        assert attrs["order_id"].startswith("ORD-")

    def test_business_data_enum(self, config_with_business_data, mock_httpx_client):
        """Enum type selects from valid values."""
        config = ScenarioConfig(**config_with_business_data)
        generator = TelemetryGenerator(config=config, otlp_endpoint="http://localhost:4318")

        operation = config.services[0].operations[0]
        attrs = generator._generate_business_data_attributes(operation)

        assert "status" in attrs
        assert attrs["status"] in ["pending", "confirmed", "shipped"]


class TestMetricCreation:
    """Tests for metric creation methods."""

    def test_create_gauge_metric(self, minimal_scenario_config, mock_httpx_client):
        """Gauge metric has correct structure."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        metric = generator._create_gauge_metric(
            "test.metric",
            "count",
            [{"timeUnixNano": "123", "asDouble": 1.5}]
        )

        assert metric["name"] == "test.metric"
        assert metric["unit"] == "count"
        assert "gauge" in metric
        assert metric["gauge"]["dataPoints"][0]["asDouble"] == 1.5

    def test_create_sum_metric(self, minimal_scenario_config, mock_httpx_client):
        """Sum metric has correct structure."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        metric = generator._create_sum_metric(
            "test.counter",
            "requests",
            True,
            [{"timeUnixNano": "123", "asInt": "100"}]
        )

        assert metric["name"] == "test.counter"
        assert metric["unit"] == "requests"
        assert "sum" in metric
        assert metric["sum"]["isMonotonic"] is True
        assert metric["sum"]["aggregationTemporality"] == 2


class TestGeneratorLifecycle:
    """Tests for generator start/stop lifecycle."""

    def test_generator_not_running_initially(self, minimal_scenario_config, mock_httpx_client):
        """Generator is not running after initialization."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        assert generator.is_running() is False

    def test_generator_client_closed_on_stop(self, minimal_scenario_config, mock_httpx_client):
        """Client is properly closed on stop."""
        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )
        generator.start()
        generator.stop()

        # Verify client.close was called
        mock_httpx_client.close.assert_called()


class TestScenarioModifications:
    """Tests for scenario modification application."""

    def test_apply_scenario(self, minimal_scenario_config, mock_httpx_client):
        """Scenario can be applied and retrieved."""
        from config_schema import ScenarioModification, ScenarioParameter

        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )

        scenario = ScenarioModification(
            type="latency_spike",
            target_services=["test-service"],
            parameters=[ScenarioParameter(key="multiplier", value=2.0)]
        )

        generator.apply_scenario("test-scenario", scenario)
        active = generator.get_active_scenarios()

        assert "test-scenario" in active
        assert active["test-scenario"].type == "latency_spike"

    def test_stop_scenario(self, minimal_scenario_config, mock_httpx_client):
        """Scenario can be stopped."""
        from config_schema import ScenarioModification, ScenarioParameter

        generator = TelemetryGenerator(
            config=minimal_scenario_config,
            otlp_endpoint="http://localhost:4318"
        )

        scenario = ScenarioModification(
            type="error_rate",
            target_services=["test-service"],
            parameters=[ScenarioParameter(key="error_percentage", value=50.0)]
        )

        generator.apply_scenario("test-scenario", scenario)
        generator.stop_scenario("test-scenario")
        active = generator.get_active_scenarios()

        assert "test-scenario" not in active
