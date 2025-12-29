"""
Load balancer telemetry generator.
Generates metrics for F5, HAProxy, AWS ALB, Azure LB style load balancers.
"""
import secrets
import random
import time
import uuid
from typing import Dict, List, Any, Optional

from config_schema import ScenarioConfig, LoadBalancer
from correlation_manager import CorrelationManager
from base_infra_generator import BaseInfrastructureGenerator


class LoadBalancerGenerator(BaseInfrastructureGenerator):
    """
    Generates load balancer metrics combining OTel conventions with cloud provider patterns.
    Supports F5, HAProxy, Nginx, AWS ALB, Azure LB, and GCP LB.
    """

    # Load balancer type configurations
    LB_CONFIGS = {
        "f5": {
            "vendor": "F5 Networks",
            "model": "BIG-IP",
            "virtual_server_prefix": "vs_",
            "pool_prefix": "pool_",
        },
        "haproxy": {
            "vendor": "HAProxy Technologies",
            "model": "HAProxy",
            "virtual_server_prefix": "frontend_",
            "pool_prefix": "backend_",
        },
        "nginx": {
            "vendor": "NGINX Inc",
            "model": "NGINX Plus",
            "virtual_server_prefix": "upstream_",
            "pool_prefix": "server_",
        },
        "aws_alb": {
            "vendor": "AWS",
            "model": "Application Load Balancer",
            "virtual_server_prefix": "arn:aws:elasticloadbalancing:",
            "pool_prefix": "targetgroup/",
        },
        "azure_lb": {
            "vendor": "Microsoft",
            "model": "Azure Load Balancer",
            "virtual_server_prefix": "/subscriptions/",
            "pool_prefix": "backendAddressPools/",
        },
        "gcp_lb": {
            "vendor": "Google",
            "model": "Cloud Load Balancing",
            "virtual_server_prefix": "projects/",
            "pool_prefix": "backendServices/",
        },
    }

    def __init__(self, config: ScenarioConfig, correlation_manager: Optional[CorrelationManager] = None):
        super().__init__(config, correlation_manager)

        # Get load balancers from infrastructure config
        self.load_balancers: List[LoadBalancer] = []
        if config.infrastructure and config.infrastructure.load_balancers:
            self.load_balancers = config.infrastructure.load_balancers

        self._lb_data = self._initialize_lb_data()
        self._counters = self._initialize_counters()

    def _initialize_lb_data(self) -> Dict[str, Dict[str, Any]]:
        """Initialize static load balancer data."""
        lb_data = {}

        for lb in self.load_balancers:
            lb_type = lb.type.lower()
            config = self.LB_CONFIGS.get(lb_type, self.LB_CONFIGS["haproxy"])

            # Generate virtual servers if not specified
            virtual_servers = lb.virtual_servers
            if not virtual_servers:
                virtual_servers = [
                    f"{config['virtual_server_prefix']}{lb.name}_{i}"
                    for i in range(1, 3)
                ]

            lb_data[lb.name] = {
                "lb_id": str(uuid.uuid4()),
                "lb_type": lb_type,
                "vendor": config["vendor"],
                "model": config["model"],
                "virtual_servers": virtual_servers,
                "backend_services": lb.backend_services,
                "health_check_path": lb.health_check_path or "/health",
                "ip_address": f"10.{random.randint(1, 50)}.{random.randint(1, 254)}.{random.randint(1, 254)}",
                "dns_name": f"{lb.name}.lb.example.com",
            }

        return lb_data

    def _initialize_counters(self) -> Dict[str, Dict[str, Any]]:
        """Initialize counters for load balancers."""
        counters = {}

        for lb in self.load_balancers:
            counters[lb.name] = {
                "request_count": random.randint(1_000_000, 100_000_000),
                "request_count_2xx": random.randint(900_000, 90_000_000),
                "request_count_4xx": random.randint(10_000, 1_000_000),
                "request_count_5xx": random.randint(1_000, 100_000),
                "connection_count": random.randint(100_000, 10_000_000),
                "bytes_in": random.randint(1_000_000_000, 100_000_000_000),
                "bytes_out": random.randint(1_000_000_000, 100_000_000_000),
            }

            # Per-backend counters
            lb_info = self._lb_data.get(lb.name, {})
            for backend in lb_info.get("backend_services", []):
                counters[f"{lb.name}:{backend}"] = {
                    "request_count": random.randint(100_000, 10_000_000),
                    "healthy": True,
                    "response_time_sum": random.randint(1000, 100000),
                    "response_time_count": random.randint(1000, 100000),
                }

        return counters

    def generate_lb_resource_attributes(self, lb: LoadBalancer) -> Dict[str, Any]:
        """Generate OTel resource attributes for a load balancer."""
        lb_info = self._lb_data.get(lb.name, {})

        attrs = {
            "service.name": lb.name,
            "service.type": "load_balancer",
            "service.instance.id": lb_info.get("lb_id", ""),

            "lb.id": lb_info.get("lb_id", ""),
            "lb.name": lb.name,
            "lb.type": lb.type,
            "lb.vendor": lb_info.get("vendor", ""),
            "lb.model": lb_info.get("model", ""),
            "lb.dns_name": lb_info.get("dns_name", ""),
            "lb.ip_address": lb_info.get("ip_address", ""),

            "data_stream.type": "metrics",
            "data_stream.dataset": "loadbalancer",
            "data_stream.namespace": "default",
        }

        # Add correlation attributes if affected
        if self.correlation_manager:
            correlation_attrs = self.correlation_manager.get_attributes_for_component(lb.name)
            attrs.update(correlation_attrs)

        return attrs

    def generate_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics payload for all load balancers (implements abstract method)."""
        return self.generate_lb_metrics_payload()

    def generate_lb_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics payload for all load balancers."""
        if not self.load_balancers:
            return {"resourceMetrics": []}

        resource_metrics = []
        current_time_ns = str(time.time_ns())

        for lb in self.load_balancers:
            lb_info = self._lb_data.get(lb.name, {})
            lb_counters = self._counters.get(lb.name, {})

            # Check for incident effects
            effect = None
            if self.correlation_manager:
                effect = self.correlation_manager.get_effect_for_component(lb.name)

            # Generate LB metrics
            metrics = self._generate_lb_metrics(
                current_time_ns, lb, lb_info, lb_counters, effect
            )

            resource_attrs = self._format_attributes(self.generate_lb_resource_attributes(lb))

            resource_metrics.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": self.SCHEMA_URL,
                },
                "scopeMetrics": [{
                    "scope": {
                        "name": "otel-demo-gen/loadbalancer-metrics-receiver",
                        "version": "1.0.0",
                    },
                    "metrics": metrics,
                }],
            })

        return {"resourceMetrics": resource_metrics}

    def _generate_lb_metrics(
        self,
        current_time_ns: str,
        lb: LoadBalancer,
        lb_info: Dict[str, Any],
        lb_counters: Dict[str, Any],
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate metrics for a single load balancer."""
        metrics = []

        # Apply incident effects
        error_multiplier = 1.0
        latency_multiplier = 1.0
        unhealthy_backends = 0

        if effect:
            effect_type = effect.get("effect", "")
            params = effect.get("parameters", {})

            if effect_type == "lb_backend_unhealthy":
                unhealthy_backends = params.get("unhealthy_count", 1)
            elif effect_type == "error_rate":
                error_multiplier = params.get("error_multiplier", 5.0)
            elif effect_type == "latency_spike":
                latency_multiplier = params.get("latency_multiplier", 3.0)

        backends = lb_info.get("backend_services", [])
        healthy_backends = max(0, len(backends) - unhealthy_backends)

        # Update request counters
        request_increment = random.randint(100, 10000)
        lb_counters["request_count"] = lb_counters.get("request_count", 0) + request_increment

        # Distribute by status code
        error_rate = min(0.5, 0.01 * error_multiplier)
        count_5xx = int(request_increment * error_rate)
        count_4xx = int(request_increment * 0.02)
        count_2xx = request_increment - count_5xx - count_4xx

        lb_counters["request_count_2xx"] = lb_counters.get("request_count_2xx", 0) + count_2xx
        lb_counters["request_count_4xx"] = lb_counters.get("request_count_4xx", 0) + count_4xx
        lb_counters["request_count_5xx"] = lb_counters.get("request_count_5xx", 0) + count_5xx

        # Connection counters
        connection_increment = random.randint(10, 500)
        lb_counters["connection_count"] = lb_counters.get("connection_count", 0) + connection_increment

        # Bytes in/out
        lb_counters["bytes_in"] = lb_counters.get("bytes_in", 0) + random.randint(100_000, 10_000_000)
        lb_counters["bytes_out"] = lb_counters.get("bytes_out", 0) + random.randint(100_000, 10_000_000)

        # Total request count
        metrics.append(self._create_sum_metric("lb.request.count", "{request}", True, [{
            "timeUnixNano": current_time_ns,
            "asInt": str(lb_counters["request_count"]),
        }]))

        # Request count by status code
        for status_class, count_key in [("2xx", "request_count_2xx"), ("4xx", "request_count_4xx"), ("5xx", "request_count_5xx")]:
            metrics.append({
                "name": "lb.request.count",
                "unit": "{request}",
                "sum": {
                    "isMonotonic": True,
                    "aggregationTemporality": 2,
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(lb_counters[count_key]),
                        "attributes": [
                            {"key": "http.status_class", "value": {"stringValue": status_class}},
                        ],
                    }],
                },
            })

        # Active connections
        active_connections = random.randint(100, 5000)
        metrics.append(self._create_gauge_metric("lb.connection.active", "{connection}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(active_connections),
        }]))

        # New connections per second
        metrics.append(self._create_gauge_metric("lb.connection.rate", "{connection}/s", [{
            "timeUnixNano": current_time_ns,
            "asDouble": random.uniform(10, 500),
        }]))

        # Total connections
        metrics.append(self._create_sum_metric("lb.connection.count", "{connection}", True, [{
            "timeUnixNano": current_time_ns,
            "asInt": str(lb_counters["connection_count"]),
        }]))

        # Bytes transferred
        metrics.extend([
            self._create_sum_metric("lb.bytes", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(lb_counters["bytes_in"]),
                "attributes": [{"key": "network.io.direction", "value": {"stringValue": "receive"}}],
            }]),
            self._create_sum_metric("lb.bytes", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(lb_counters["bytes_out"]),
                "attributes": [{"key": "network.io.direction", "value": {"stringValue": "transmit"}}],
            }]),
        ])

        # Backend health metrics
        metrics.extend([
            self._create_gauge_metric("lb.backend.healthy", "{backend}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(healthy_backends),
            }]),
            self._create_gauge_metric("lb.backend.unhealthy", "{backend}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(unhealthy_backends),
            }]),
            self._create_gauge_metric("lb.backend.total", "{backend}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(len(backends)),
            }]),
        ])

        # Response time (average)
        avg_response_time = random.uniform(10, 100) * latency_multiplier
        metrics.append(self._create_gauge_metric("lb.response_time.avg", "ms", [{
            "timeUnixNano": current_time_ns,
            "asDouble": avg_response_time,
        }]))

        # Response time percentiles
        for percentile, multiplier in [("p50", 0.8), ("p95", 1.5), ("p99", 2.5)]:
            metrics.append({
                "name": "lb.response_time",
                "unit": "ms",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asDouble": avg_response_time * multiplier,
                        "attributes": [
                            {"key": "percentile", "value": {"stringValue": percentile}},
                        ],
                    }],
                },
            })

        # Queue depth (for some LB types)
        if lb.type.lower() in ["haproxy", "f5"]:
            metrics.append(self._create_gauge_metric("lb.queue.depth", "{request}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(0, 50)),
            }]))

        # Per-backend metrics
        for backend in backends:
            backend_counters = self._counters.get(f"{lb.name}:{backend}", {})

            # Check if this backend should be marked unhealthy
            is_healthy = True
            if self.correlation_manager:
                backend_effect = self.correlation_manager.get_effect_for_component(backend)
                if backend_effect:
                    is_healthy = False

            # Override if we need unhealthy backends
            if unhealthy_backends > 0 and backends.index(backend) < unhealthy_backends:
                is_healthy = False

            backend_attrs = [
                {"key": "lb.backend.name", "value": {"stringValue": backend}},
            ]

            # Backend request count
            backend_request_increment = random.randint(10, 1000)
            backend_counters["request_count"] = backend_counters.get("request_count", 0) + backend_request_increment

            metrics.append({
                "name": "lb.backend.request.count",
                "unit": "{request}",
                "sum": {
                    "isMonotonic": True,
                    "aggregationTemporality": 2,
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(backend_counters["request_count"]),
                        "attributes": backend_attrs,
                    }],
                },
            })

            # Backend health status
            metrics.append({
                "name": "lb.backend.health",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": "1" if is_healthy else "0",
                        "attributes": backend_attrs,
                    }],
                },
            })

            # Backend response time
            backend_response_time = random.uniform(5, 50) * (latency_multiplier if not is_healthy else 1.0)
            metrics.append({
                "name": "lb.backend.response_time",
                "unit": "ms",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asDouble": backend_response_time * (3.0 if not is_healthy else 1.0),
                        "attributes": backend_attrs,
                    }],
                },
            })

            # Backend active connections
            metrics.append({
                "name": "lb.backend.connection.active",
                "unit": "{connection}",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(random.randint(1, 100) if is_healthy else 0),
                        "attributes": backend_attrs,
                    }],
                },
            })

        # SSL metrics (for ALBs and similar)
        if lb.type.lower() in ["aws_alb", "azure_lb", "nginx", "f5"]:
            metrics.extend([
                self._create_gauge_metric("lb.ssl.handshake.time", "ms", [{
                    "timeUnixNano": current_time_ns,
                    "asDouble": random.uniform(5, 30),
                }]),
                self._create_sum_metric("lb.ssl.handshake.count", "{handshake}", True, [{
                    "timeUnixNano": current_time_ns,
                    "asInt": str(random.randint(10000, 1000000)),
                }]),
            ])

        return metrics

    # _create_gauge_metric, _create_sum_metric, and _format_attributes
    # are now inherited from BaseInfrastructureGenerator
