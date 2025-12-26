"""
Tests for Pydantic models in config_schema.py.
"""
import pytest
from pydantic import ValidationError
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_schema import (
    ScenarioConfig, Service, ServiceDependency, DbDependency, CacheDependency,
    Database, MessageQueue, Telemetry, LatencyConfig, Operation,
    BusinessDataField, LogSample, ScenarioModification, ScenarioParameter,
    NetworkDevice, VirtualMachine, LoadBalancer, StorageSystem, InfrastructureConfig,
    CascadeStage, CascadingOutageConfig, IncidentCorrelation
)


class TestServiceModel:
    """Tests for Service model."""

    def test_minimal_service(self):
        """Service with only required fields."""
        service = Service(name="test-service", depends_on=[])
        assert service.name == "test-service"
        assert service.language == "python"  # Default value
        assert service.depends_on == []

    def test_service_with_language(self):
        """Service with language specified."""
        service = Service(name="api", language="python", depends_on=[])
        assert service.language == "python"

    def test_service_with_operations(self):
        """Service with operations."""
        service = Service(
            name="api",
            depends_on=[],
            operations=[
                Operation(name="GetUser", span_name="GET /users/{id}")
            ]
        )
        assert len(service.operations) == 1
        assert service.operations[0].name == "GetUser"


class TestDependencyModels:
    """Tests for dependency models."""

    def test_service_dependency(self):
        """ServiceDependency with basic fields."""
        dep = ServiceDependency(service="backend", protocol="http")
        assert dep.service == "backend"
        assert dep.protocol == "http"

    def test_service_dependency_with_latency(self):
        """ServiceDependency with latency config."""
        dep = ServiceDependency(
            service="backend",
            latency=LatencyConfig(min_ms=10, max_ms=100)
        )
        assert dep.latency.min_ms == 10
        assert dep.latency.max_ms == 100

    def test_db_dependency(self):
        """DbDependency model."""
        dep = DbDependency(db="postgres-main")
        assert dep.db == "postgres-main"

    def test_cache_dependency(self):
        """CacheDependency model."""
        dep = CacheDependency(cache="redis-cache")
        assert dep.cache == "redis-cache"


class TestLatencyConfig:
    """Tests for LatencyConfig model."""

    def test_latency_defaults(self):
        """LatencyConfig with defaults."""
        latency = LatencyConfig(min_ms=10, max_ms=100)
        assert latency.probability == 1.0  # Default

    def test_latency_with_probability(self):
        """LatencyConfig with custom probability."""
        latency = LatencyConfig(min_ms=10, max_ms=100, probability=0.5)
        assert latency.probability == 0.5


class TestBusinessDataField:
    """Tests for BusinessDataField model."""

    def test_string_field(self):
        """String type business data field."""
        field = BusinessDataField(name="user_id", type="string")
        assert field.name == "user_id"
        assert field.type == "string"

    def test_number_field_with_range(self):
        """Number type with min/max values."""
        field = BusinessDataField(
            name="amount",
            type="number",
            min_value=0.0,
            max_value=1000.0
        )
        assert field.min_value == 0.0
        assert field.max_value == 1000.0

    def test_enum_field(self):
        """Enum type with values."""
        field = BusinessDataField(
            name="status",
            type="enum",
            values=["pending", "confirmed", "shipped"]
        )
        assert len(field.values) == 3


class TestScenarioConfig:
    """Tests for ScenarioConfig model."""

    def test_minimal_scenario_config(self):
        """ScenarioConfig with minimal valid data."""
        config = ScenarioConfig(
            services=[Service(name="test", depends_on=[])],
            telemetry=Telemetry(
                trace_rate=1,
                error_rate=0.1,
                metrics_interval=10,
                include_logs=True
            )
        )
        assert len(config.services) == 1
        assert config.telemetry.trace_rate == 1

    def test_scenario_config_with_databases(self):
        """ScenarioConfig with databases."""
        config = ScenarioConfig(
            services=[Service(name="api", depends_on=[])],
            databases=[Database(name="postgres", type="postgres")],
            telemetry=Telemetry(
                trace_rate=1,
                error_rate=0.1,
                metrics_interval=10,
                include_logs=True
            )
        )
        assert len(config.databases) == 1

    def test_scenario_config_with_infrastructure(self):
        """ScenarioConfig with infrastructure."""
        config = ScenarioConfig(
            services=[Service(name="api", depends_on=[])],
            infrastructure=InfrastructureConfig(
                network_devices=[
                    NetworkDevice(name="switch-1", type="switch")
                ]
            ),
            telemetry=Telemetry(
                trace_rate=1,
                error_rate=0.1,
                metrics_interval=10,
                include_logs=True
            )
        )
        assert len(config.infrastructure.network_devices) == 1


class TestInfrastructureModels:
    """Tests for infrastructure models."""

    def test_network_device(self):
        """NetworkDevice model."""
        device = NetworkDevice(
            name="core-switch-01",
            type="switch",
            vendor="cisco"
        )
        assert device.name == "core-switch-01"
        assert device.type == "switch"
        assert device.vendor == "cisco"

    def test_virtual_machine(self):
        """VirtualMachine model."""
        vm = VirtualMachine(
            name="vm-001",
            hypervisor_type="esxi",
            host_name="esxi-host-01",
            vcpus=4,
            memory_gb=16
        )
        assert vm.vcpus == 4
        assert vm.memory_gb == 16

    def test_load_balancer(self):
        """LoadBalancer model."""
        lb = LoadBalancer(
            name="prod-lb",
            type="haproxy",
            backend_services=["api-1", "api-2"]
        )
        assert len(lb.backend_services) == 2

    def test_storage_system(self):
        """StorageSystem model."""
        storage = StorageSystem(
            name="san-primary",
            type="san",
            capacity_tb=100.0
        )
        assert storage.capacity_tb == 100.0


class TestCascadeModels:
    """Tests for cascading outage models."""

    def test_cascade_stage(self):
        """CascadeStage model."""
        stage = CascadeStage(
            component="switch-1",
            effect="port_down",
            delay_ms=5000
        )
        assert stage.component == "switch-1"
        assert stage.effect == "port_down"
        assert stage.delay_ms == 5000

    def test_cascading_outage_config(self):
        """CascadingOutageConfig model."""
        config = CascadingOutageConfig(
            name="Network Cascade",
            description="Test cascade",
            origin="infrastructure",
            trigger_component="switch-1",
            cascade_chain=[
                CascadeStage(component="switch-1", effect="port_down", delay_ms=0),
                CascadeStage(component="database", effect="timeout", delay_ms=5000)
            ]
        )
        assert len(config.cascade_chain) == 2
        assert config.origin == "infrastructure"


class TestScenarioModification:
    """Tests for scenario modification models."""

    def test_scenario_modification(self):
        """ScenarioModification model."""
        scenario = ScenarioModification(
            type="latency_spike",
            target_services=["api-gateway"],
            parameters=[
                ScenarioParameter(key="multiplier", value=3.0)
            ]
        )
        assert scenario.type == "latency_spike"
        assert len(scenario.target_services) == 1
        assert scenario.parameters[0].value == 3.0

    def test_scenario_parameter(self):
        """ScenarioParameter model."""
        param = ScenarioParameter(key="error_percentage", value=50.0)
        assert param.key == "error_percentage"
        assert param.value == 50.0


class TestLogSample:
    """Tests for LogSample model."""

    def test_log_sample(self):
        """LogSample model."""
        sample = LogSample(
            level="ERROR",
            message="Connection timeout after {timeout_ms}ms"
        )
        assert sample.level == "ERROR"
        assert "{timeout_ms}" in sample.message


class TestTelemetry:
    """Tests for Telemetry model."""

    def test_telemetry_config(self):
        """Telemetry with all fields."""
        config = Telemetry(
            trace_rate=10,
            error_rate=0.05,
            metrics_interval=30,
            include_logs=True
        )
        assert config.trace_rate == 10
        assert config.error_rate == 0.05
        assert config.metrics_interval == 30
        assert config.include_logs is True

    def test_telemetry_config_defaults(self):
        """Telemetry uses defaults."""
        config = Telemetry(
            trace_rate=1,
            error_rate=0.1,
            metrics_interval=10,
            include_logs=True
        )
        # Just verify it creates without error
        assert config is not None
