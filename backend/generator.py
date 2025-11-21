import threading
import time
import secrets
import random
import os
import requests
import json
import httpx
import uuid
import re
from typing import Dict, List, Any, Tuple, Union, Optional, Set
from datetime import datetime, timezone

from config_schema import ScenarioConfig, Service, ServiceDependency, DbDependency, CacheDependency, LatencyConfig, Operation, BusinessDataField, ScenarioModification
from k8s_metrics_generator import K8sMetricsGenerator

class TelemetryGenerator:
    """
    Generates and sends telemetry data (traces, metrics, logs) based on a scenario config.
    """
    SPAN_KIND_MAP = {
        "UNSPECIFIED": 0,
        "INTERNAL": 1,
        "SERVER": 2,
        "CLIENT": 3,
        "PRODUCER": 4,
        "CONSUMER": 5,
    }

    STATUS_CODE_MAP = {
        "STATUS_CODE_UNSET": 0,
        "STATUS_CODE_OK": 1,
        "STATUS_CODE_ERROR": 2,
    }

    SEVERITY_NUMBER_MAP = {
        "INFO": 9,
        "ERROR": 17,
    }

    RUNTIME_INFO = {
        "python": {"name": "CPython", "version": "3.11.5"},
        "java": {"name": "OpenJDK Runtime Environment", "version": "17.0.5"},
        "nodejs": {"name": "Node.js", "version": "18.12.1"},
        "go": {"name": "Go", "version": "1.21.0"},
        "ruby": {"name": "Ruby", "version": "3.2.2"},
        "dotnet": {"name": ".NET", "version": "7.0.0"},
        "javascript": {"name": "Node.js", "version": "18.12.1"},
        "typescript": {"name": "Node.js", "version": "18.12.1"},
        "php": {"name": "PHP", "version": "8.2"},
        "rust": {"name": "Rust", "version": "1.84.0"},
        "swift": {"name": "Swift", "version": "5.10"},
        "erlang": {"name": "Erlang/OTP", "version": "26.2"},
        "cpp": {"name": "C++", "version": "23"},
    }

    def __init__(self, config: ScenarioConfig, otlp_endpoint: str, api_key: Optional[str] = None, auth_type: str = "ApiKey", failure_callback=None):
        self.config = config
        self.api_key = api_key
        self.auth_type = auth_type
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._k8s_thread: Optional[threading.Thread] = None  # New: K8s metrics thread
        
        # Error handling and connection monitoring
        self.failure_callback = failure_callback  # Callback to report failures to job management
        self.consecutive_failures = 0
        self.max_failures = 5  # Fail the job after 5 consecutive OTLP failures
        self.last_successful_send = None
        self.is_failed = False  # Track if generator has failed due to connection issues
        
        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            self.headers["Authorization"] = f"{self.auth_type} {self.api_key}"

        self.client = httpx.Client(headers=self.headers, http2=True)

        self.services_map = {s.name: s for s in self.config.services}
        self.db_map = {db.name: db for db in self.config.databases}
        self.mq_map = {mq.name: mq for mq in self.config.message_queues}
        
        # Initialize K8s metrics generator
        self.k8s_generator = K8sMetricsGenerator(config)
        
        # Pre-generate resource attributes for each service (using k8s data)
        self.service_resource_attributes_metrics = {
            s.name: self._generate_resource_attributes(s, "metrics") for s in self.config.services
        }
        self.service_resource_attributes_traces = {
            s.name: self._generate_resource_attributes(s, "traces") for s in self.config.services
        }
        self.service_operations_map = {
            s.name: {op.name: op for op in s.operations} 
            for s in self.config.services if s.operations
        }

        # OTel Collector Endpoint
        # Prioritize the provided endpoint, then an environment variable, and finally a default value.
        collector_url_base = otlp_endpoint or os.getenv("OTEL_COLLECTOR_URL") or "http://localhost:4318"
        self.collector_url = collector_url_base.rstrip('/')
        if not self.collector_url.endswith('/'):
            self.collector_url += '/'

        # State for metric counters
        self._request_counters = {s.name: 0 for s in self.config.services}

        # Scenario injection system
        self._active_scenarios: Dict[str, ScenarioModification] = {}  # scenario_id -> modification
        self._scenario_lock = threading.Lock()  # Thread safety for scenario modifications
        self._error_counters = {s.name: 0 for s in self.config.services}
        self._runtime_counters = {s.name: 0 for s in self.config.services}

    @staticmethod
    def _get_service_language(service: Service) -> str:
        return (service.language or 'python').lower()

    def _generate_k8s_telemetry(self):
        """The main loop for the k8s metrics generator thread."""
        # For demo purposes, send K8s metrics more frequently
        k8s_metrics_interval = 10  # Send every 10 seconds instead of 30
        
        print("Kubernetes metrics generation loop started.")
        while not self._stop_event.is_set():
            self.generate_and_send_k8s_metrics()
            self.generate_and_send_k8s_logs()  # Also send K8s logs
            
            # Wait for the interval or until stop event is set
            self._stop_event.wait(k8s_metrics_interval)
        
        print("Kubernetes metrics generation loop finished.")

    def generate_and_send_k8s_metrics(self):
        """Generates and sends Kubernetes pod metrics."""
        if not self.collector_url:
            print("Warning: OTLP endpoint not configured. Cannot send k8s metrics.")
            return
            
        k8s_metrics_payload = self.k8s_generator.generate_k8s_metrics_payload()
        if k8s_metrics_payload.get("resourceMetrics"):
            self._send_payload(f"{self.collector_url}v1/metrics", k8s_metrics_payload, "k8s-metrics")

    def generate_and_send_k8s_logs(self, dry_run=False):
        """
        Generates and sends Kubernetes structured logs.
        If dry_run is True, it returns the payload as a JSON string instead of sending it.
        """
        if not self.collector_url and not dry_run:
            print("Warning: OTLP endpoint not configured. Cannot send k8s logs.")
            return
            
        # Generate logs occasionally, but always for a dry run
        if dry_run or random.random() < 0.9:
            k8s_logs_payload = self.k8s_generator.generate_k8s_logs_payload()
            if k8s_logs_payload.get("resourceLogs"):
                if dry_run:
                    return json.dumps(k8s_logs_payload, indent=2)
                else:
                    self._send_payload(f"{self.collector_url}v1/logs", k8s_logs_payload, "k8s-logs")
        return None





    def _generate_resource_attributes(self, service: Service, telemetry_type: str = "metrics") -> Dict[str, Any]:
        """Generates resource attributes for telemetry data compatible with collector processors."""
        lang = self._get_service_language(service)
        runtime_info = self.RUNTIME_INFO.get(lang, {"name": lang, "version": "1.0.0"})
        
        # Get k8s pod data for this service to maintain consistency
        pod_data = self.k8s_generator._k8s_pod_data[service.name]

        return {
            # Core service attributes
            "service.name": service.name,
            "service.namespace": pod_data['namespace'],
            "service.version": "1.2.3",
            "service.instance.id": f"{service.name}-{pod_data['pod_name']}",
            
            # Telemetry SDK attributes
            "telemetry.sdk.language": lang,
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.24.0",
            
            # Runtime attributes
            "process.runtime.name": runtime_info["name"],
            "process.runtime.version": runtime_info["version"],
            
            # Cloud and host attributes - now using dynamic cloud provider from k8s generator
            "cloud.provider": pod_data['cloud_provider'],
            "cloud.platform": pod_data['cloud_platform'],
            "cloud.region": pod_data['cloud_region'],
            "cloud.availability_zone": pod_data['zone'],
            "deployment.environment": "production",
            "host.name": pod_data['node_name'],
            "host.architecture": "amd64",  # Elasticsearch exporter maps this to host.architecture 
            "os.type": "linux",
            "os.description": pod_data['os_description'],
            
            # Container attributes for better ECS mapping
            "container.image.name": f"{service.name}:latest",
            "container.image.tag": "latest", 
            "container.image.tags": ["latest", "v1.2.3"],  # Elasticsearch exporter maps this to container.image.tag
            
            # Basic k8s attributes for regular app metrics
            "k8s.cluster.name": pod_data['cluster_name'],
            "k8s.namespace.name": pod_data['namespace'],
            "k8s.pod.name": pod_data['pod_name'],
            "k8s.node.name": pod_data['node_name'],
            
            # CRITICAL: Data stream attributes for Elastic routing
            "data_stream.type": telemetry_type,
            "data_stream.dataset": "generic", 
            "data_stream.namespace": "default"
        }

    def _generate_telemetry(self):
        """The main loop for the generator thread."""
        try:
            trace_interval = 1.0 / self.config.telemetry.trace_rate if self.config.telemetry.trace_rate > 0 else -1
        except ZeroDivisionError:
            trace_interval = -1 # Effectively disable trace generation

        metrics_interval = self.config.telemetry.metrics_interval
        last_metrics_time = time.time()

        print("Telemetry generation loop started.")
        while not self._stop_event.is_set():
            if trace_interval > 0:
                self.generate_and_send_traces_and_logs()

            if time.time() - last_metrics_time >= metrics_interval:
                self.generate_and_send_metrics()
                last_metrics_time = time.time()

            # The wait call will be interrupted if the stop event is set
            self._stop_event.wait(trace_interval if trace_interval > 0 else 1)
        
        print("Telemetry generation loop finished.")

    def start(self):
        """Starts the telemetry generation in a background thread."""
        if self._thread and self._thread.is_alive():
            print("Generator is already running.")
            return

        print("Starting telemetry generator...")
        self._stop_event.clear()
        
        # Start main telemetry thread
        self._thread = threading.Thread(target=self._generate_telemetry, name="TelemetryGeneratorThread")
        self._thread.daemon = True
        self._thread.start()
        
        # Start k8s metrics thread
        self._k8s_thread = threading.Thread(target=self._generate_k8s_telemetry, name="K8sMetricsThread")
        self._k8s_thread.daemon = True
        self._k8s_thread.start()
        
        print("Generator threads started (main + k8s metrics).")

    def is_running(self) -> bool:
        """Checks if the generator threads are currently running."""
        main_running = self._thread is not None and self._thread.is_alive()
        k8s_running = self._k8s_thread is not None and self._k8s_thread.is_alive()
        return main_running or k8s_running

    def get_config_as_dict(self) -> Dict[str, Any]:
        """Returns the current scenario configuration as a dictionary."""
        return self.config.model_dump(mode="json")

    def stop(self):
        """Stops the telemetry generation."""
        if not self.is_running():
            print("Generator is not running.")
            return

        print("Stopping telemetry generator...")
        self._stop_event.set()
        
        # Stop main thread
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                print("Warning: Main generator thread did not stop in time.")
        self._thread = None
        
        # Stop k8s thread
        if self._k8s_thread and self._k8s_thread.is_alive():
            self._k8s_thread.join(timeout=5)
            if self._k8s_thread.is_alive():
                print("Warning: K8s metrics thread did not stop in time.")
        self._k8s_thread = None
        
        self.client.close()
        print("Generator stopped.")

    def apply_scenario(self, scenario_id: str, scenario: ScenarioModification):
        """Applies a scenario modification to the telemetry generation."""
        with self._scenario_lock:
            self._active_scenarios[scenario_id] = scenario
            print(f"Applied scenario '{scenario_id}': {scenario.type} targeting {scenario.target_services}")

    def stop_scenario(self, scenario_id: str):
        """Stops a specific scenario."""
        with self._scenario_lock:
            if scenario_id in self._active_scenarios:
                scenario = self._active_scenarios.pop(scenario_id)
                print(f"Stopped scenario '{scenario_id}': {scenario.type}")
            else:
                print(f"Scenario '{scenario_id}' not found")

    def get_active_scenarios(self) -> Dict[str, ScenarioModification]:
        """Returns copy of currently active scenarios."""
        with self._scenario_lock:
            return self._active_scenarios.copy()

    def _generate_realistic_log_message(self, service_name: str, span: Dict[str, Any], is_error: bool = False) -> str:
        """Generate realistic log message using LLM-generated samples."""
        service = self.services_map.get(service_name)
        if not service or not service.log_samples:
            # Fallback to default messages
            if is_error:
                return f"Operation '{span['name']}' failed unexpectedly."
            return f"Operation '{span['name']}' handled."

        # Filter log samples by level
        if is_error:
            error_samples = [log for log in service.log_samples if log.level in ["ERROR", "WARN"]]
            if error_samples:
                log_sample = secrets.choice(error_samples)
            else:
                return f"Operation '{span['name']}' failed unexpectedly."
        else:
            info_samples = [log for log in service.log_samples if log.level in ["INFO", "DEBUG"]]
            if info_samples:
                log_sample = secrets.choice(info_samples)
            else:
                return f"Operation '{span['name']}' handled."

        message = log_sample.message

        # Determine contextual attributes up front so we don't clobber scenario-specific placeholders
        is_error_span = span.get("status", {}).get("code") == "STATUS_CODE_ERROR"
        contextual_attrs = self._get_contextual_attributes(service_name, is_failure=is_error and is_error_span)
        protected_placeholders = {
            "{" + attr.replace(".", "_") + "}"
            for attr in contextual_attrs
        }

        message = self._fill_log_placeholders(message, protected_placeholders)
        message = self._inject_contextual_data_into_log_message(message, contextual_attrs)

        return message

    def _apply_scenario_modifications(self, service_name: str, operation_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Applies scenario modifications and returns modification parameters.
        Returns dict with keys like 'latency_multiplier', 'error_rate_override', etc.
        """
        modifications = {}

        with self._scenario_lock:
            for scenario_id, scenario in self._active_scenarios.items():
                # Check if this scenario applies to this service
                if service_name not in scenario.target_services:
                    continue

                # Check if this scenario applies to this operation (if specified)
                if scenario.target_operations and operation_name not in scenario.target_operations:
                    continue

                # Apply modifications based on scenario type
                if scenario.type == "latency_spike":
                    for param in scenario.parameters:
                        if param.key == "multiplier":
                            modifications["latency_multiplier"] = modifications.get("latency_multiplier", 1.0) * param.value
                        elif param.key == "base_latency_ms":
                            modifications["base_latency_ms"] = max(modifications.get("base_latency_ms", 0), param.value)

                elif scenario.type == "error_rate":
                    for param in scenario.parameters:
                        if param.key == "error_percentage":
                            # Take the highest error rate if multiple scenarios apply
                            modifications["error_rate_override"] = max(modifications.get("error_rate_override", 0), param.value / 100.0)
                        elif param.key == "error_code":
                            modifications["error_code"] = param.value

                elif scenario.type == "service_unavailable":
                    for param in scenario.parameters:
                        if param.key == "unavailable_percentage":
                            modifications["unavailable_rate"] = max(modifications.get("unavailable_rate", 0), param.value / 100.0)

                elif scenario.type == "database_slow":
                    for param in scenario.parameters:
                        if param.key == "query_delay_ms":
                            modifications["db_delay_ms"] = max(modifications.get("db_delay_ms", 0), param.value)

                elif scenario.type == "memory_pressure":
                    for param in scenario.parameters:
                        if param.key == "memory_percentage":
                            modifications["memory_usage_override"] = max(modifications.get("memory_usage_override", 0), param.value / 100.0)

                elif scenario.type == "cpu_spike":
                    for param in scenario.parameters:
                        if param.key == "cpu_percentage":
                            modifications["cpu_usage_override"] = max(modifications.get("cpu_usage_override", 0), param.value / 100.0)

                elif scenario.type == "network_partition":
                    for param in scenario.parameters:
                        if param.key == "additional_latency_ms":
                            modifications["additional_latency_ms"] = modifications.get("additional_latency_ms", 0) + param.value
                        elif param.key == "packet_loss_percentage":
                            modifications["packet_loss_rate"] = max(modifications.get("packet_loss_rate", 0), param.value / 100.0)

        return modifications

    def _get_contextual_attributes(self, service_name: str, is_failure: bool = False) -> Dict[str, Any]:
        """
        Get contextual attributes based on active scenarios and failure state.
        Returns attributes that should be added to spans and logs.
        """
        attributes = {}

        with self._scenario_lock:
            for scenario_id, scenario in self._active_scenarios.items():
                # Check if this scenario applies to this service
                if service_name not in scenario.target_services:
                    continue

                # Apply contextual patterns
                for pattern in scenario.contextual_patterns:
                    if is_failure and pattern.failure_values:
                        # Use failure-specific values
                        value = secrets.choice(pattern.failure_values)
                    elif pattern.normal_values:
                        # Use normal values
                        value = secrets.choice(pattern.normal_values)
                    else:
                        continue

                    attributes[pattern.attribute_name] = value

        return attributes

    def _fill_log_placeholders(self, message: str, protected_tokens: Optional[Set[str]] = None) -> str:
        """Replace templated placeholders with realistic synthetic values."""
        if not message:
            return message

        protected_tokens = protected_tokens or set()
        placeholders = set(re.findall(r"{([^{}]+)}", message))
        if not placeholders:
            return message

        for placeholder in placeholders:
            token = "{" + placeholder + "}"
            if token in protected_tokens:
                continue

            value = self._generate_placeholder_value(placeholder)
            message = message.replace(token, value)

        return message

    def _generate_placeholder_value(self, placeholder: str) -> str:
        """Generate a context-aware replacement for a placeholder token."""
        normalized = placeholder.strip().lower()

        predefined_generators = {
            "user_id": lambda: f"user_{secrets.randbelow(99999):05d}",
            "order_id": lambda: f"ord-{secrets.randbelow(999999):06d}",
            "payment_id": lambda: f"pay-{secrets.randbelow(999999):06d}",
            "session_id": lambda: f"sess_{uuid.uuid4().hex[:8]}",
            "product_id": lambda: f"prod-{secrets.randbelow(9999):04d}",
            "item_count": lambda: str(secrets.randbelow(10) + 1),
            "error_reason": lambda: secrets.choice(["timeout", "connection_failed", "invalid_data", "rate_limit_exceeded"]),
            "region": lambda: secrets.choice(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]),
            "order_total": lambda: f"{random.uniform(10.99, 599.99):.2f}",
            "payment_method": lambda: secrets.choice(["credit_card", "paypal", "bank_transfer", "apple_pay"]),
        }

        if normalized in predefined_generators:
            return str(predefined_generators[normalized]())

        numeric_ms_tokens = ["ms", "_ms", "milliseconds"]
        if any(normalized.endswith(suffix) for suffix in numeric_ms_tokens) or "duration" in normalized:
            return str(secrets.randbelow(4900) + 100)

        if normalized.endswith("_seconds") or normalized.endswith("_secs"):
            return str(secrets.randbelow(55) + 1)

        if normalized.endswith("_count") or "count" in normalized:
            return str(secrets.randbelow(900) + 1)

        if normalized.endswith("_points") or "points" in normalized:
            return str(secrets.randbelow(5000) + 50)

        if normalized.endswith("_amount") or normalized.endswith("_total") or "amount" in normalized or "total" in normalized:
            return f"{random.uniform(5.0, 1500.0):.2f}"

        if normalized.endswith("_status"):
            return secrets.choice(["active", "inactive", "degraded", "recovering"])

        if normalized.endswith("_mode"):
            return secrets.choice(["normal", "fallback", "maintenance"])

        if normalized.endswith("_id") or normalized.endswith("id"):
            base = re.sub(r"_?id$", "", placeholder).lower()
            prefix = base or "id"
            return f"{prefix}_{uuid.uuid4().hex[:8]}"

        if normalized.endswith("_name") or normalized.endswith("name"):
            base = re.sub(r"name$", "", placeholder).strip("_") or "resource"
            return f"{base.lower()}-{secrets.randbelow(999):03d}"

        if normalized.endswith("_code") or "code" in normalized:
            return f"{secrets.randbelow(899) + 100}"

        if normalized.endswith("_percentage") or normalized.endswith("_pct"):
            return str(round(random.uniform(0, 100), 2))

        # Default fallback keeps placeholder readable but unique
        safe_name = re.sub(r"[^a-z0-9]+", "-", normalized) or "value"
        return f"{safe_name}-{uuid.uuid4().hex[:6]}"

    def _inject_contextual_data_into_log_message(self, message: str, contextual_attrs: Dict[str, Any]) -> str:
        """
        Inject contextual data into log message placeholders.
        """
        for attr_name, value in contextual_attrs.items():
            # Convert attribute names to placeholder format
            placeholder = "{" + attr_name.replace(".", "_") + "}"
            message = message.replace(placeholder, str(value))

        return message

    def generate_and_send_traces_and_logs(self):
        """Generates and sends a single trace and its associated logs."""
        if not self.collector_url:
            print("Warning: OTLP endpoint not configured. Cannot send telemetry.")
            return

        spans = self.generate_spans()
        if spans:
            trace_payload = self.format_otlp_trace_payload(spans)
            self._send_payload(f"{self.collector_url}v1/traces", trace_payload, "traces")
            
            if self.config.telemetry.include_logs:
                logs_payload = self.generate_otlp_logs_payload(spans)
                if logs_payload.get("resourceLogs"):
                    self._send_payload(f"{self.collector_url}v1/logs", logs_payload, "logs")

    def generate_and_send_metrics(self):
        """Generates and sends a batch of metrics for all services."""
        if not self.collector_url:
            print("Warning: OTLP endpoint not configured. Cannot send telemetry.")
            return
            
        metrics_payload = self.generate_otlp_metrics_payload()
        self._send_payload(f"{self.collector_url}v1/metrics", metrics_payload, "metrics")

    def _send_payload(self, url: str, payload: Dict, signal_name: str):
        """Helper function to POST a JSON payload using the httpx client."""
        try:
            response = self.client.post(url, data=json.dumps(payload), timeout=5)
            response.raise_for_status()
            print(f"Successfully sent {signal_name} to {url} - Status: {response.status_code}")
            
            # Reset failure count on successful send
            self.consecutive_failures = 0
            self.last_successful_send = datetime.now()
            
            # Debug: Log payload structure for metrics
            if signal_name == "k8s-metrics" and payload.get("resourceMetrics"):
                resource_count = len(payload["resourceMetrics"])
                if resource_count > 0:
                    metric_count = len(payload["resourceMetrics"][0].get("scopeMetrics", [{}])[0].get("metrics", []))
                    scope_name = payload["resourceMetrics"][0].get("scopeMetrics", [{}])[0].get("scope", {}).get("name", "unknown")
                    print(f"  📊 Sent {metric_count} k8s metrics from {resource_count} resources with scope: {scope_name}")
            
            # Debug: Log payload structure for K8s logs
            if signal_name == "k8s-logs" and payload.get("resourceLogs"):
                resource_count = len(payload["resourceLogs"])
                total_logs = sum(len(rl.get("scopeLogs", [{}])[0].get("logRecords", [])) for rl in payload["resourceLogs"])
                if total_logs > 0:
                    print(f"  📝 Sent {total_logs} k8s logs from {resource_count} resources")
            
        except httpx.RequestError as e:
            self._handle_connection_failure(f"Connection error sending {signal_name}: {e}", url)
        except httpx.HTTPStatusError as e:
            self._handle_connection_failure(f"HTTP error sending {signal_name}: {e.response.status_code} {e.response.reason_phrase}", url)
        except Exception as e:
            self._handle_connection_failure(f"Unexpected error sending {signal_name}: {e}", url)
    
    def _handle_connection_failure(self, error_message: str, url: str):
        """Handle OTLP connection failures with escalating response."""
        self.consecutive_failures += 1
        print(f"❌ {error_message} (failure {self.consecutive_failures}/{self.max_failures})")
        
        # If we've reached the failure threshold, mark the job as failed
        if self.consecutive_failures >= self.max_failures and not self.is_failed:
            self.is_failed = True
            full_error = f"OTLP endpoint unreachable: {self.consecutive_failures} consecutive failures to {url}. Last error: {error_message}"
            print(f"🚨 Generator marking job as failed: {full_error}")
            
            # Notify the job management system via callback
            if self.failure_callback:
                self.failure_callback(full_error)
            
            # Stop the generator
            self.stop()

    def _generate_id(self, byte_length: int) -> str:
        """Generates a random hex ID."""
        return secrets.token_hex(byte_length)

    def _format_attributes(self, attrs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Converts a dictionary of attributes to the OTLP key-value list format."""
        formatted = []
        for key, value in attrs.items():
            if isinstance(value, str):
                val_dict = {"stringValue": value}
            elif isinstance(value, bool):
                val_dict = {"boolValue": value}
            elif isinstance(value, int):
                # According to the OTLP/JSON specification, intValue must be a *string* representation of
                # the integer to avoid 64-bit precision loss in JavaScript environments. Sending the raw
                # integer results in a 400 Bad Request from strict back-ends (e.g., Elastic APM).  
                val_dict = {"intValue": str(value)}
            elif isinstance(value, float):
                val_dict = {"doubleValue": value}
            else:
                val_dict = {"stringValue": str(value)}
            formatted.append({"key": key, "value": val_dict})
        return formatted

    def _find_entry_points(self) -> List[Service]:
        """Finds all services that are not dependencies of any other service."""
        if not self.config.services:
            return []

        dependency_names = set()
        for service in self.config.services:
            for dep in service.depends_on:
                if isinstance(dep, ServiceDependency):
                    dependency_names.add(dep.service)
        
        entry_points = [
            service for service in self.config.services
            if service.name not in dependency_names
        ]

        # Fallback: if all services are dependencies (e.g., a cycle),
        # return the full list of services to choose from.
        if not entry_points:
            return self.config.services
            
        return entry_points

    def _get_transaction_result(self, status_code: int) -> str:
        """Generates a transaction result string from an HTTP status code."""
        if 200 <= status_code < 300:
            return f"HTTP {status_code // 100}xx"
        if 400 <= status_code < 500:
            return f"HTTP {status_code // 100}xx"
        if 500 <= status_code < 600:
            return f"HTTP {status_code // 100}xx"
        return "Unknown"

    def _get_latency_ns(self, latency_config: Optional['LatencyConfig'], service_name: str = "", operation_name: str = "") -> int:
        """Calculates a latency in nanoseconds based on a LatencyConfig and scenario modifications."""
        base_latency_ms = 0

        # Get base latency from config
        if latency_config and random.random() < latency_config.probability:
            base_latency_ms = random.randint(latency_config.min_ms, latency_config.max_ms)

        # Apply scenario modifications
        if service_name:
            modifications = self._apply_scenario_modifications(service_name, operation_name)

            # Apply latency multiplier
            if "latency_multiplier" in modifications:
                base_latency_ms = int(base_latency_ms * modifications["latency_multiplier"])

            # Apply base latency override
            if "base_latency_ms" in modifications:
                base_latency_ms = max(base_latency_ms, modifications["base_latency_ms"])

            # Apply additional network latency
            if "additional_latency_ms" in modifications:
                base_latency_ms += modifications["additional_latency_ms"]

        return base_latency_ms * 1_000_000

    def _generate_business_data_attributes(self, operation: Operation) -> Dict[str, Any]:
        """Generates business data attributes based on the operation's business_data configuration."""
        attributes = {}
        
        if not operation.business_data:
            return attributes
            
        for field in operation.business_data:
            try:
                if field.type == "string":
                    if field.pattern:
                        # Replace pattern placeholders with generated values
                        value = field.pattern
                        if "{random}" in value:
                            value = value.replace("{random}", secrets.token_hex(4))
                        if "{uuid}" in value:
                            value = value.replace("{uuid}", str(uuid.uuid4()))
                        if "{random_string}" in value:
                            value = value.replace("{random_string}", secrets.token_hex(6))
                        attributes[field.name] = value
                    else:
                        # Default string generation
                        attributes[field.name] = f"value_{secrets.token_hex(4)}"
                        
                elif field.type == "number":
                    min_val = field.min_value if field.min_value is not None else 0.0
                    max_val = field.max_value if field.max_value is not None else 100.0
                    attributes[field.name] = round(random.uniform(min_val, max_val), 2)
                    
                elif field.type == "integer":
                    min_val = int(field.min_value) if field.min_value is not None else 0
                    max_val = int(field.max_value) if field.max_value is not None else 100
                    attributes[field.name] = random.randint(min_val, max_val)
                    
                elif field.type == "boolean":
                    attributes[field.name] = random.choice([True, False])
                    
                elif field.type == "enum":
                    if field.values:
                        attributes[field.name] = secrets.choice(field.values)
                    else:
                        attributes[field.name] = "default_value"
                        
                else:
                    # Fallback for unknown types
                    attributes[field.name] = f"unknown_type_{field.type}"
                    
            except Exception as e:
                print(f"Warning: Error generating business data for field '{field.name}': {e}")
                attributes[field.name] = "generation_error"
                
        return attributes

    def format_otlp_trace_payload(self, spans_by_service: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Any]]:
        """
        Formats a dictionary of generated spans into an OTLP/JSON TracesData payload.
        """
        resource_spans = []

        for service_name, spans in spans_by_service.items():
            if not spans:
                continue

            service_config = self.services_map.get(service_name)
            if not service_config:
                continue
            
            resource_attrs = self._format_attributes(
                self.service_resource_attributes_traces.get(service_name, {"service.name": service_name})
            )

            otlp_spans = []
            for span in spans:
                otlp_spans.append({
                    "traceId": span["traceId"],
                    "spanId": span["spanId"],
                    **({"parentSpanId": span["parentSpanId"]} if span.get("parentSpanId") else {}),
                    "name": span["name"],
                    "kind": self.SPAN_KIND_MAP.get(span["kind"], 0),
                    "startTimeUnixNano": span["startTimeUnixNano"],
                    "endTimeUnixNano": span["endTimeUnixNano"],
                    "attributes": self._format_attributes(span.get("attributes", {})),
                    "status": {
                        "code": self.STATUS_CODE_MAP.get(span["status"]["code"], 0)
                    },
                })
            
            scope_spans = [{
                "scope": {"name": "otel-demo-generator"},
                "spans": otlp_spans,
            }]

            resource_spans.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": "https://opentelemetry.io/schemas/1.35.0"
                },
                "scopeSpans": scope_spans,
            })
            
        return {"resourceSpans": resource_spans}

    def generate_otlp_logs_payload(self, spans_by_service: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Any]]:
        """
        Generates a complete OTLP/JSON LogsData payload for a given trace.
        """
        resource_logs = []

        for service_name, spans in spans_by_service.items():
            if not spans:
                continue

            service_config = self.services_map.get(service_name)
            if not service_config:
                continue

            resource_attrs = self._format_attributes(
                self.service_resource_attributes_traces.get(service_name, {"service.name": service_name})
            )

            log_records = []
            for span in spans:
                # Generate realistic info log
                info_message = self._generate_realistic_log_message(service_name, span, is_error=False)
                info_log = {
                    "timeUnixNano": span["endTimeUnixNano"],
                    "severityText": "INFO",
                    "severityNumber": self.SEVERITY_NUMBER_MAP["INFO"],
                    "body": {"stringValue": info_message},
                    "traceId": span["traceId"],
                    "spanId": span["spanId"],
                }
                log_records.append(info_log)

                if span["status"]["code"] == "STATUS_CODE_ERROR":
                    # Generate realistic error log
                    error_scenarios = [
                        ("ConnectionTimeoutException", "Connection to database timed out after 5000ms"),
                        ("ServiceUnavailableException", "Upstream service responded with 503 Unavailable"),
                        ("NullPointerException", "Attempt to invoke method 'getId()' on null object"),
                        ("IllegalArgumentException", "Invalid input parameters provided for request"),
                        ("PaymentProcessingException", "Payment gateway rejected transaction: Insufficient funds"),
                        ("DatabaseExecutionException", "Query failed: deadlock detected"),
                    ]
                    err_type, err_msg = secrets.choice(error_scenarios)
                    
                    error_message = self._generate_realistic_log_message(service_name, span, is_error=True)
                    error_log = {
                        "timeUnixNano": span["endTimeUnixNano"],
                        "severityText": "ERROR",
                        "severityNumber": self.SEVERITY_NUMBER_MAP["ERROR"],
                        "body": {"stringValue": error_message},
                        "traceId": span["traceId"],
                        "spanId": span["spanId"],
                        "attributes": self._format_attributes({
                            "exception.type": err_type,
                            "exception.message": err_msg,
                            "exception.stacktrace": f"java.lang.{err_type}: {err_msg}\n\tat com.example.Service.process(Service.java:42)\n\tat com.example.Controller.handle(Controller.java:23)"
                        }),
                    }
                    log_records.append(error_log)
            
            if not log_records:
                continue

            scope_logs = [{
                "scope": {"name": "otel-demo-generator"},
                "logRecords": log_records,
            }]

            resource_logs.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": "https://opentelemetry.io/schemas/1.35.0"
                },
                "scopeLogs": scope_logs,
            })

        return {"resourceLogs": resource_logs}

    def generate_otlp_metrics_payload(self) -> Dict[str, List[Any]]:
        """
        Generates a complete OTLP/JSON MetricsData payload for all services.
        """
        resource_metrics = []
        current_time_ns = str(time.time_ns())

        for service in self.config.services:
            metrics = []

            # Apply scenario modifications
            modifications = self._apply_scenario_modifications(service.name)

            # --- Standard Metrics ---
            cpu_utilization = random.uniform(0.1, 0.9)
            if "cpu_usage_override" in modifications:
                cpu_utilization = modifications["cpu_usage_override"]
            metrics.append(self._create_gauge_metric("system.cpu.utilization", "%", [
                {"timeUnixNano": current_time_ns, "asDouble": cpu_utilization}
            ]))

            memory_usage = random.randint(200_000_000, 800_000_000)
            if "memory_usage_override" in modifications:
                # Convert percentage to bytes (assuming 1GB total for demo)
                memory_usage = int(modifications["memory_usage_override"] * 1_000_000_000)
            metrics.append(self._create_gauge_metric("process.memory.usage", "By", [
                {"timeUnixNano": current_time_ns, "asInt": str(memory_usage)}
            ]))

            self._request_counters[service.name] += random.randint(5, 20)
            metrics.append(self._create_sum_metric("http.server.request.count", "requests", True, [
                {"timeUnixNano": current_time_ns, "startTimeUnixNano": str(time.time_ns() - 3600_000_000_000), "asInt": str(self._request_counters[service.name])}
            ]))

            # Check for scenario-overridden error rates
            error_rate = self.config.telemetry.error_rate
            if "error_rate_override" in modifications:
                error_rate = modifications["error_rate_override"]
            elif "unavailable_rate" in modifications:
                error_rate = max(error_rate, modifications["unavailable_rate"])

            if random.random() < error_rate:
                self._error_counters[service.name] += 1
            metrics.append(self._create_sum_metric("http.server.request.error.count", "errors", True, [
                {"timeUnixNano": current_time_ns, "startTimeUnixNano": str(time.time_ns() - 3600_000_000_000), "asInt": str(self._error_counters[service.name])}
            ]))

            # --- Runtime-Specific Metrics ---
            lang = self._get_service_language(service)
            if lang == "java":
                self._runtime_counters[service.name] += random.randint(0, 2)
                metrics.append(self._create_sum_metric("jvm.gc.collection_count", "collections", True, [
                    {"timeUnixNano": current_time_ns, "startTimeUnixNano": str(time.time_ns() - 3600_000_000_000), "asInt": str(self._runtime_counters[service.name])}
                ]))
            elif lang == "go":
                metrics.append(self._create_gauge_metric("go.goroutines", "goroutines", [
                    {"timeUnixNano": current_time_ns, "asInt": str(random.randint(20, 150))}
                ]))
            elif lang == "nodejs":
                metrics.append(self._create_gauge_metric("nodejs.eventloop.delay.avg", "ms", [
                    {"timeUnixNano": current_time_ns, "asDouble": random.uniform(0.5, 5.0)}
                ]))
            elif lang == "python":
                 self._runtime_counters[service.name] += random.randint(0, 3)
                 metrics.append(self._create_sum_metric("python.gc.collections", "collections", True, [
                    {"timeUnixNano": current_time_ns, "startTimeUnixNano": str(time.time_ns() - 3600_000_000_000), "asInt": str(self._runtime_counters[service.name])}
                 ]))
            
            resource_attrs = self._format_attributes(
                self.service_resource_attributes_metrics.get(service.name, {"service.name": service.name})
            )
            scope_metrics = [{"scope": {"name": "otel-demo-generator"}, "metrics": metrics}]
            resource_metrics.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": "https://opentelemetry.io/schemas/1.35.0"
                },
                "scopeMetrics": scope_metrics,
            })

        return {"resourceMetrics": resource_metrics}

    def _create_gauge_metric(self, name: str, unit: str, data_points: List[Dict[str, Any]]):
        return {"name": name, "unit": unit, "gauge": {"dataPoints": data_points}}
    
    def _create_sum_metric(self, name: str, unit: str, is_monotonic: bool, data_points: List[Dict[str, Any]]):
        return {"name": name, "unit": unit, "sum": {"isMonotonic": is_monotonic, "aggregationTemporality": 2, "dataPoints": data_points}}

    def generate_spans(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generates a single trace by traversing the service dependency graph.
        """
        spans_by_service: Dict[str, List[Dict[str, Any]]] = {
            s.name: [] for s in self.config.services
        }
        entry_points = self._find_entry_points()
        if not entry_points:
            return {}
        
        entry_point = secrets.choice(entry_points)

        trace_id = self._generate_id(16)

        # Determine if trace has error, considering scenario modifications
        trace_has_error = random.random() < self.config.telemetry.error_rate
        error_source = None

        # Check for scenario-induced errors
        for service in self.config.services:
            modifications = self._apply_scenario_modifications(service.name)

            # Check for service unavailability
            if "unavailable_rate" in modifications and random.random() < modifications["unavailable_rate"]:
                trace_has_error = True
                error_source = service.name
                break

            # Check for overridden error rates
            if "error_rate_override" in modifications and random.random() < modifications["error_rate_override"]:
                trace_has_error = True
                error_source = service.name
                break

        # If no scenario-specific error and base error rate triggered, pick random service
        if trace_has_error and not error_source:
            error_source = secrets.choice(self.config.services).name
        
        self._generate_span_recursive(
            service_name=entry_point.name,
            parent_span_id=None,
            trace_id=trace_id,
            spans_by_service=spans_by_service,
            start_time_ns=time.time_ns(),
            error_source=error_source,
            trigger_kind="SERVER",
            visited_services=set(),
            recursion_depth=0
        )

        return spans_by_service

    def _generate_span_recursive(
        self,
        service_name: str,
        parent_span_id: Optional[str],
        trace_id: str,
        spans_by_service: Dict[str, List[Dict[str, Any]]],
        start_time_ns: int,
        error_source: Optional[str],
        trigger_kind: str,
        visited_services: set,
        recursion_depth: int,
        trigger_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, bool]:
        """
        Recursively generates spans for a service and its dependencies.
        Returns a tuple of (end_time_nanoseconds, did_error_occur).
        """
        if service_name in visited_services or recursion_depth > 20:
            return start_time_ns, False

        service = self.services_map.get(service_name)
        if not service:
            return start_time_ns, False

        # Add current service to the visited set for this path
        current_path_visited = visited_services.copy()
        current_path_visited.add(service_name)

        span_id = self._generate_id(8)
        
        # --- Select an operation if available for the CURRENT service ---
        operation = None
        if service_name in self.service_operations_map and self.service_operations_map[service_name]:
            operation = secrets.choice(list(self.service_operations_map[service_name].values()))

        # --- Latency Calculation ---
        # Start with a base processing time
        own_processing_time_ns = secrets.randbelow(20_000_000) + 5_000_000
        # Add latency from the operation, if defined
        if operation and operation.latency:
            own_processing_time_ns += self._get_latency_ns(operation.latency, service_name, operation.name)

        # Apply scenario modifications even if no operation-specific latency
        else:
            scenario_latency_ns = self._get_latency_ns(None, service_name)
            own_processing_time_ns += scenario_latency_ns

        # Determine the span name
        span_name = ""
        if operation:
            span_name = operation.span_name
        else:
            if trigger_kind == 'SERVER':
                span_name = f"{service.name} process"
            elif trigger_kind == 'CONSUMER':
                queue_name = trigger_context.get('queue_name', 'unknown_queue') if trigger_context else 'unknown_queue'
                span_name = f"{queue_name} process"
            else:
                span_name = service.name

        attributes = {}
        # For root spans, explicitly set the transaction name attribute for better APM integration.
        if trigger_kind == "SERVER":
            attributes["transaction.name"] = span_name
        
        # --- Add messaging attributes for CONSUMER spans ---
        if trigger_kind == "CONSUMER" and trigger_context:
            queue_name = trigger_context.get('queue_name', 'unknown_queue')
            queue_system = trigger_context.get('queue_system', 'kafka') # Assume kafka if not specified
            attributes['messaging.system'] = queue_system
            attributes['messaging.destination.name'] = queue_name
            attributes['messaging.operation'] = 'process'
            attributes['network.transport'] = 'tcp'
            attributes['messaging.consumer.id'] = f"{service.name}-consumer-group"
            if queue_system == 'kafka':
                attributes['messaging.kafka.destination.partition'] = str(secrets.randbelow(3))
                attributes['messaging.kafka.message.offset'] = str(secrets.randbelow(100000))
        
        # --- Add business data attributes from operation ---
        if operation:
            business_attributes = self._generate_business_data_attributes(operation)
            attributes.update(business_attributes)

        # --- Add contextual attributes from active scenarios ---
        is_error = (error_source == service_name)
        contextual_attrs = self._get_contextual_attributes(service_name, is_failure=is_error)
        attributes.update(contextual_attrs)

        service_span = {
            "traceId": trace_id,
            "spanId": span_id,
            "parentSpanId": parent_span_id,
            "name": span_name,
            "kind": trigger_kind,
            "startTimeUnixNano": str(start_time_ns),
            "attributes": attributes,
        }

        child_start_time_ns = start_time_ns + secrets.randbelow(3_000_000) + 1_000_000
        downstream_error = False
        latest_child_end_time_ns = child_start_time_ns

        for dep in service.depends_on:
            child_span_id = self._generate_id(8)
            
            if isinstance(dep, ServiceDependency):
                if dep.via:
                    producer_span = self._create_producer_span(service, dep, trace_id, span_id, child_span_id, child_start_time_ns)
                    spans_by_service[service.name].append(producer_span)
                    
                    queue_delay_ns = secrets.randbelow(10_000_000) + 5_000_000
                    consumer_start_time = int(producer_span["endTimeUnixNano"]) + queue_delay_ns

                    queue_system = producer_span.get("attributes", {}).get("messaging.system", "kafka")

                    end_time, error_in_branch = self._generate_span_recursive(
                        service_name=dep.service,
                        parent_span_id=child_span_id,
                        trace_id=trace_id,
                        spans_by_service=spans_by_service,
                        start_time_ns=consumer_start_time,
                        error_source=error_source,
                        trigger_kind="CONSUMER",
                        visited_services=current_path_visited,
                        recursion_depth=recursion_depth + 1,
                        trigger_context={'queue_name': dep.via, 'queue_system': queue_system}
                    )
                    if error_in_branch:
                        downstream_error = True
                    latest_child_end_time_ns = max(latest_child_end_time_ns, end_time, int(producer_span["endTimeUnixNano"]))
                else:
                    client_span, downstream_start_time = self._create_client_span(service, dep, trace_id, span_id, child_span_id, child_start_time_ns)
                    
                    # Initialize status_code with default success value
                    status_code = 200
                    
                    end_time, error_in_branch = self._generate_span_recursive(
                        service_name=dep.service,
                        parent_span_id=child_span_id,
                        trace_id=trace_id,
                        spans_by_service=spans_by_service,
                        start_time_ns=downstream_start_time,
                        error_source=error_source,
                        trigger_kind="SERVER",
                        visited_services=current_path_visited,
                        recursion_depth=recursion_depth + 1
                    )
                    if error_in_branch:
                        downstream_error = True
                        client_span["status"]["code"] = "STATUS_CODE_ERROR"
                        if "http.request.method" in client_span["attributes"]:
                             client_span["attributes"]["http.response.status_code"] = 500
                             status_code = 500
                        elif "rpc.system" in client_span["attributes"]:
                             client_span["attributes"]["rpc.grpc.status_code"] = 13
                    
                    # Add transaction result for HTTP spans
                    if "http.request.method" in client_span["attributes"]:
                        client_span["attributes"]["transaction.result"] = self._get_transaction_result(status_code)

                    client_span["endTimeUnixNano"] = str(end_time) # Update client span end time
                    spans_by_service[service.name].append(client_span)
                    latest_child_end_time_ns = max(latest_child_end_time_ns, end_time)
            elif isinstance(dep, (DbDependency, CacheDependency)):
                db_span, db_end_time = self._create_db_span(service, dep, trace_id, span_id, child_span_id, child_start_time_ns, operation)
                spans_by_service[service.name].append(db_span)
                latest_child_end_time_ns = max(latest_child_end_time_ns, db_end_time)

        is_error_source = (error_source == service.name)
        total_error = is_error_source or downstream_error
        
        service_span_end_time = max(latest_child_end_time_ns, start_time_ns + own_processing_time_ns)
        service_span["endTimeUnixNano"] = str(service_span_end_time)
        service_span["status"] = {"code": "STATUS_CODE_ERROR"} if total_error else {"code": "STATUS_CODE_OK"}
        
        # --- Add final HTTP attributes to SERVER span ---
        if trigger_kind == "SERVER":
            try:
                parts = service_span["name"].split()
                if len(parts) >= 2 and parts[0] in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
                    method = parts[0]
                    path = " ".join(parts[1:])
                else: # Fallback for non-standard span names
                    method = 'GET'
                    path = '/'
            except Exception:
                method = 'GET'
                path = '/'
            
            status_code = 500 if total_error else 200
            
            service_span["attributes"]['http.request.method'] = method
            service_span["attributes"]['url.path'] = path
            service_span["attributes"]['http.response.status_code'] = status_code
            service_span["attributes"]['transaction.result'] = self._get_transaction_result(status_code)

        spans_by_service[service.name].append(service_span)

        return service_span_end_time, total_error

    def _create_producer_span(self, service: Service, dep: ServiceDependency, trace_id, parent_id, child_id, start_time):
        duration = secrets.randbelow(5_000_000) + 1_000_000
        end_time = start_time + duration
        queue = self.mq_map.get(dep.via) if dep.via else None
        
        destination_name = queue.name if queue else dep.via

        attributes = {
            "messaging.system": queue.type if queue else "unknown",
            "messaging.destination.name": destination_name,
            "messaging.operation": "publish",
            "server.address": queue.name if queue else None,
            "network.transport": "tcp",
            "messaging.kafka.destination.partition": str(secrets.randbelow(3)), # Simulate 3 partitions
        }
        attributes = {k: v for k,v in attributes.items() if v is not None}

        return {
            "traceId": trace_id, "spanId": child_id, "parentSpanId": parent_id,
            "name": f"{destination_name} publish", "kind": "PRODUCER",
            "startTimeUnixNano": str(start_time), "endTimeUnixNano": str(end_time),
            "status": {"code": "STATUS_CODE_OK"}, "attributes": attributes
        }

    def _create_client_span(self, service: Service, dep: ServiceDependency, trace_id, parent_id, child_id, start_time):
        # Base duration is now just for the network hop, as recursive call determines total time
        network_hop_duration = secrets.randbelow(2_000_000) + 500_000
        # Add specific dependency latency if configured
        network_hop_duration += self._get_latency_ns(dep.latency, service.name)

        downstream_start_time = start_time + network_hop_duration
        # The end time is now determined by the recursive call, so we set it later.
        # This is a placeholder, it will be updated after the recursive call returns.
        end_time = downstream_start_time 

        attributes = {
            'net.peer.name': dep.service,
            'user_agent.original': f"otel-demo-generator/{self._get_service_language(service)}"
        }
        protocol = (dep.protocol or 'http').lower()

        if protocol in ('http', 'https'):
            method = secrets.choice(['GET', 'POST', 'PUT', 'DELETE'])
            path = f"/{service.name.lower()}/{secrets.token_hex(4)}"
            attributes['http.request.method'] = method
            attributes['http.response.status_code'] = 200 # default, will be overwritten on error
            attributes['url.path'] = path
            scheme = 'https' if protocol == 'https' else 'http'
            attributes['url.full'] = f"{scheme}://{dep.service}{path}"
            attributes['server.address'] = dep.service
            span_name = f"HTTP {method}"
        elif protocol == 'grpc':
            attributes['rpc.system'] = 'grpc'
            attributes['rpc.service'] = dep.service.capitalize().replace('-', '') + "Service"
            attributes['rpc.method'] = 'Process'
            attributes['rpc.grpc.status_code'] = 0
            span_name = f"GRPC {attributes['rpc.service']}/{attributes['rpc.method']}"
        else:
            span_name = f"CALL {dep.service}"

        return ({
            "traceId": trace_id, "spanId": child_id, "parentSpanId": parent_id,
            "name": span_name, "kind": "CLIENT",
            "startTimeUnixNano": str(start_time), "endTimeUnixNano": str(end_time),
            "status": {"code": "STATUS_CODE_OK"}, "attributes": attributes
        }, downstream_start_time)

    def _create_db_span(self, service: Service, dep: Union[DbDependency, CacheDependency], trace_id, parent_id, child_id, start_time, operation: Optional[Operation]):
        duration = secrets.randbelow(30_000_000) + 5_000_000  # 5-35ms for db query
        duration += self._get_latency_ns(dep.latency, service.name)

        # Apply database scenario modifications
        modifications = self._apply_scenario_modifications(service.name)
        if "db_delay_ms" in modifications:
            duration += modifications["db_delay_ms"] * 1_000_000
        end_time = start_time + duration
        
        if isinstance(dep, DbDependency):
            db_name = dep.db
        elif isinstance(dep, CacheDependency):
            db_name = dep.cache
        else:
            # Should not happen given the call site's check
            return {}, start_time 

        db_instance = self.db_map.get(db_name)
        
        attributes = {}
        span_name = f"QUERY {db_name}" if isinstance(dep, DbDependency) else f"GET {db_name}"

        # --- Use realistic queries from config ---
        query = None
        # 1. Prefer query from the specific operation
        if operation and operation.db_queries:
            query = secrets.choice(operation.db_queries)
        # 2. Fallback to query from the dependency definition
        elif dep.example_queries:
            query = secrets.choice(dep.example_queries)

        if db_instance:
            attributes["db.system"] = db_instance.type
            attributes["db.name"] = db_instance.name
            attributes["net.peer.name"] = db_name
            table_name = service.name.replace('-service', '').lower() + 's'

            if db_instance.type in ('postgres', 'mysql', 'mariadb', 'mssql'):
                final_query = query or f"SELECT * FROM {table_name} WHERE id = ?"
                attributes["db.statement"] = final_query
                
                # Infer operation from query
                inferred_op = final_query.strip().upper().split()[0]
                if inferred_op in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    attributes["db.operation"] = inferred_op
                    span_name = f"{inferred_op} {db_name}"
                else: # Fallback for complex queries like CTEs or non-standard SQL
                    attributes["db.operation"] = "query"
                    span_name = f"QUERY {db_name}"

            elif db_instance.type == 'redis':
                final_query = query or f"GET user_session:{secrets.token_hex(8)}"
                attributes["db.statement"] = final_query
                inferred_op = final_query.strip().upper().split()[0]
                attributes["db.operation"] = inferred_op if inferred_op else "GET"
                span_name = f"{attributes['db.operation']} {db_name}"
            elif db_instance.type == 'mongodb':
                final_query = query or f"db.{table_name}.findOne({{ \"_id\": ObjectId(\"...\") }})"
                attributes["db.statement"] = final_query
                # A simple heuristic for MongoDB query types
                if "find" in final_query:
                    attributes["db.operation"] = "find"
                elif "insert" in final_query:
                    attributes["db.operation"] = "insert"
                elif "update" in final_query:
                    attributes["db.operation"] = "update"
                else:
                    attributes["db.operation"] = "query"
                span_name = f"{attributes['db.operation'].upper()} {db_name}"
        
        return ({
            "traceId": trace_id, "spanId": child_id, "parentSpanId": parent_id,
            "name": span_name, "kind": "CLIENT",
            "startTimeUnixNano": str(start_time), "endTimeUnixNano": str(end_time),
            "status": {"code": "STATUS_CODE_OK"}, "attributes": attributes
        }, end_time)



def main_test():
    """Example usage for standalone testing of the generator."""
    sample_config = {
        "services": [
            {
                "name": "frontend",
                "language": "javascript",
                "depends_on": []
            }
        ],
        "telemetry": {
            "trace_rate": 1,
            "error_rate": 0.1,
            "metrics_interval": 5,
            "include_logs": True
        }
    }
    generator = None
    try:
        scenario_config = ScenarioConfig(**sample_config)
        generator = TelemetryGenerator(config=scenario_config, otlp_endpoint="http://localhost:4318")
        generator.start()
        print("Generator started for testing. Running for 15 seconds.")
        time.sleep(15)
    except Exception as e:
        print(f"Error during testing setup: {e}")
    finally:
        if generator:
            generator.stop()

def test_k8s_log_generation():
    """Tests the generation of K8s logs payload by printing it."""
    print("\n--- Running K8s Log Generation Test ---")
    sample_config = {
        "services": [
            {
                "name": "api-gateway",
                "language": "go",
                "role": "frontend",
                "depends_on": [
                    {"service": "orders-service", "protocol": "grpc"}
                ]
            },
            {
                "name": "orders-service",
                "language": "java",
                "role": "backend",
                "depends_on": [
                    {"db": "orders-db"}
                ]
            }
        ],
        "databases": [
            {"name": "orders-db", "type": "postgres"}
        ],
        "telemetry": {
            "trace_rate": 1,
            "error_rate": 0,
            "metrics_interval": 10,
            "include_logs": True
        }
    }
    generator = None
    try:
        scenario_config = ScenarioConfig(**sample_config)
        # OTLP endpoint can be None for a dry run
        generator = TelemetryGenerator(config=scenario_config, otlp_endpoint=None)
        
        # Generate and print the k8s logs payload
        logs_payload_json = generator.generate_and_send_k8s_logs(dry_run=True)
        
        if logs_payload_json:
            print("Successfully generated K8s logs payload:")
            print(logs_payload_json)
        else:
            print("K8s logs payload generation did not produce output.")

    except Exception as e:
        print(f"Error during K8s log generation test: {e}")
    finally:
        if generator and generator.is_running():
            generator.stop()


if __name__ == "__main__":
    main_test()
    test_k8s_log_generation() 
