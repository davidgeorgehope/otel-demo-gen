"""
Base class for infrastructure telemetry generators.

Provides common functionality for formatting OTLP payloads, creating metrics,
and handling correlation attributes. This eliminates code duplication across
network, VM, load balancer, storage, and database generators.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import time

from config_schema import ScenarioConfig
from correlation_manager import CorrelationManager


class BaseInfrastructureGenerator(ABC):
    """
    Abstract base class for infrastructure telemetry generators.

    Provides common methods for:
    - OTLP attribute formatting
    - Gauge and sum metric creation
    - Resource metrics payload building
    - Correlation attribute injection
    - Log record creation
    """

    SCHEMA_URL = "https://opentelemetry.io/schemas/1.35.0"

    def __init__(self, config: ScenarioConfig, correlation_manager: Optional[CorrelationManager] = None):
        """
        Initialize the base generator.

        Args:
            config: The scenario configuration
            correlation_manager: Optional correlation manager for incident tracking
        """
        self.config = config
        self.correlation_manager = correlation_manager
        self._counters: Dict[str, Dict[str, Any]] = {}

    @abstractmethod
    def generate_metrics_payload(self) -> Dict[str, Any]:
        """
        Generate the complete OTLP metrics payload.

        Must be implemented by subclasses.

        Returns:
            OTLP metrics payload dictionary
        """
        pass

    def _format_attributes(self, attrs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert a dictionary of attributes to OTLP format.

        Handles string, bool, int, and float types appropriately.

        Args:
            attrs: Dictionary of key-value attribute pairs

        Returns:
            List of OTLP-formatted attribute dictionaries
        """
        formatted = []
        for key, value in attrs.items():
            if isinstance(value, str):
                val_dict = {"stringValue": value}
            elif isinstance(value, bool):
                # Note: bool check must come before int (bool is subclass of int)
                val_dict = {"boolValue": value}
            elif isinstance(value, int):
                val_dict = {"intValue": value}
            elif isinstance(value, float):
                val_dict = {"doubleValue": value}
            else:
                val_dict = {"stringValue": str(value)}
            formatted.append({"key": key, "value": val_dict})
        return formatted

    def _create_gauge_metric(
        self,
        name: str,
        unit: str,
        data_points: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create a gauge metric.

        Args:
            name: Metric name (e.g., "hw.network.bandwidth.utilization")
            unit: Unit of measurement (e.g., "By", "1", "percent")
            data_points: List of data point dictionaries

        Returns:
            OTLP gauge metric dictionary
        """
        return {
            "name": name,
            "unit": unit,
            "gauge": {"dataPoints": data_points}
        }

    def _create_sum_metric(
        self,
        name: str,
        unit: str,
        is_monotonic: bool,
        data_points: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create a sum (counter) metric.

        Args:
            name: Metric name (e.g., "hw.network.io")
            unit: Unit of measurement (e.g., "By", "packets")
            is_monotonic: Whether the counter only increases
            data_points: List of data point dictionaries

        Returns:
            OTLP sum metric dictionary
        """
        return {
            "name": name,
            "unit": unit,
            "sum": {
                "isMonotonic": is_monotonic,
                "aggregationTemporality": 2,  # CUMULATIVE
                "dataPoints": data_points,
            },
        }

    def _build_resource_metrics(
        self,
        resource_attrs: Dict[str, Any],
        scope_name: str,
        metrics: List[Dict[str, Any]],
        scope_version: str = "1.0.0"
    ) -> Dict[str, Any]:
        """
        Build a complete resource metrics structure for OTLP.

        Args:
            resource_attrs: Resource-level attributes
            scope_name: Instrumentation scope name
            metrics: List of metric dictionaries
            scope_version: Instrumentation scope version

        Returns:
            Complete resourceMetrics structure
        """
        return {
            "resource": {
                "attributes": self._format_attributes(resource_attrs),
                "schemaUrl": self.SCHEMA_URL,
            },
            "scopeMetrics": [{
                "scope": {
                    "name": scope_name,
                    "version": scope_version,
                },
                "metrics": metrics,
            }],
        }

    def _build_resource_logs(
        self,
        resource_attrs: Dict[str, Any],
        scope_name: str,
        log_records: List[Dict[str, Any]],
        scope_version: str = "1.0.0"
    ) -> Dict[str, Any]:
        """
        Build a complete resource logs structure for OTLP.

        Args:
            resource_attrs: Resource-level attributes
            scope_name: Instrumentation scope name
            log_records: List of log record dictionaries
            scope_version: Instrumentation scope version

        Returns:
            Complete resourceLogs structure
        """
        return {
            "resource": {
                "attributes": self._format_attributes(resource_attrs),
                "schemaUrl": self.SCHEMA_URL,
            },
            "scopeLogs": [{
                "scope": {
                    "name": scope_name,
                    "version": scope_version,
                },
                "logRecords": log_records,
            }],
        }

    def _apply_correlation(
        self,
        attrs: Dict[str, Any],
        component_name: str
    ) -> Dict[str, Any]:
        """
        Add correlation attributes if component is affected by an incident.

        Args:
            attrs: Existing attributes dictionary
            component_name: Name of the component to check

        Returns:
            Updated attributes with correlation info (if applicable)
        """
        if self.correlation_manager:
            correlation_attrs = self.correlation_manager.get_attributes_for_component(component_name)
            attrs.update(correlation_attrs)
        return attrs

    def _get_effect_for_component(self, component_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the current effect for a component if part of an incident.

        Args:
            component_name: Name of the component to check

        Returns:
            Effect dictionary if component is affected, None otherwise
        """
        if not self.correlation_manager:
            return None

        effect = self.correlation_manager.get_effect_for_component(component_name)
        if effect:
            incident_id = None
            attrs = self.correlation_manager.get_attributes_for_component(component_name)
            if attrs:
                incident_id = attrs.get("incident.id")
            return {"effect": effect, "incident_id": incident_id}
        return None

    def _create_log_record(
        self,
        time_ns: str,
        level: str,
        message: str,
        severity_number: int,
        incident_id: Optional[str] = None,
        extra_attrs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an OTLP log record.

        Args:
            time_ns: Timestamp in nanoseconds as string
            level: Log level (e.g., "INFO", "ERROR")
            message: Log message body
            severity_number: OTel severity number (1-24)
            incident_id: Optional incident ID for correlation
            extra_attrs: Additional attributes to include

        Returns:
            OTLP log record dictionary
        """
        attributes = []

        if incident_id:
            attributes.append({
                "key": "incident.id",
                "value": {"stringValue": incident_id},
            })

        if extra_attrs:
            attributes.extend(self._format_attributes(extra_attrs))

        return {
            "timeUnixNano": time_ns,
            "observedTimeUnixNano": time_ns,
            "severityText": level,
            "severityNumber": severity_number,
            "body": {"stringValue": message},
            "attributes": attributes,
        }

    def _create_data_point(
        self,
        value: Any,
        time_ns: str,
        start_time_ns: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an OTLP metric data point.

        Args:
            value: The metric value (int or float)
            time_ns: Timestamp in nanoseconds as string
            start_time_ns: Start time for cumulative metrics
            attributes: Optional data point attributes

        Returns:
            Data point dictionary
        """
        point = {"timeUnixNano": time_ns}

        if start_time_ns:
            point["startTimeUnixNano"] = start_time_ns

        if isinstance(value, int):
            point["asInt"] = str(value)
        elif isinstance(value, float):
            point["asDouble"] = value
        else:
            point["asDouble"] = float(value)

        if attributes:
            point["attributes"] = self._format_attributes(attributes)

        return point

    @staticmethod
    def current_time_ns() -> str:
        """Get current time in nanoseconds as string."""
        return str(time.time_ns())

    @staticmethod
    def hours_ago_ns(hours: int = 1) -> str:
        """Get time N hours ago in nanoseconds as string."""
        return str(time.time_ns() - (hours * 3600_000_000_000))
