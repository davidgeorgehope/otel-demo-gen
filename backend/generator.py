import threading
import time
import secrets
import random
import os
import requests
import json
import httpx
import yaml
import uuid
from typing import Dict, List, Any, Tuple, Union, Optional
from datetime import datetime, timezone

from config_schema import ScenarioConfig, Service, ServiceDependency, DbDependency, CacheDependency, LatencyConfig, Operation, BusinessDataField


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
        "nodejs": {"name": "node.js", "version": "18.12.1"},
        "go": {"name": "go", "version": "1.21.0"},
        "ruby": {"name": "ruby", "version": "3.2.2"},
        "dotnet": {"name": ".NET", "version": "7.0.0"},
        "javascript": {"name": "node.js", "version": "18.12.1"},
        "typescript": {"name": "node.js", "version": "18.12.1"},
    }

    def __init__(self, config: ScenarioConfig, otlp_endpoint: str, api_key: Optional[str] = None):
        self.config = config
        self.api_key = api_key
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._k8s_thread: Optional[threading.Thread] = None  # New: K8s metrics thread
        
        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            self.headers["Authorization"] = f"ApiKey {self.api_key}"

        self.client = httpx.Client(headers=self.headers, http2=True)

        self.services_map = {s.name: s for s in self.config.services}
        self.db_map = {db.name: db for db in self.config.databases}
        self.mq_map = {mq.name: mq for mq in self.config.message_queues}
        
        # Initialize K8s pod data FIRST (needed for resource attributes)
        self._k8s_pod_data = self._initialize_k8s_pod_data()
        
        # Pre-generate resource attributes for each service (after k8s data is ready)
        self.service_resource_attributes = {
            s.name: self._generate_resource_attributes(s) for s in self.config.services
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
        self._error_counters = {s.name: 0 for s in self.config.services}
        self._runtime_counters = {s.name: 0 for s in self.config.services}

        # K8s-specific counters
        self._k8s_counters = {
            s.name: {
                'network_rx_bytes': random.randint(50000000, 100000000),
                'network_tx_bytes': random.randint(70000000, 120000000),
                'restart_count': 0
            } for s in self.config.services
        }

    def _initialize_k8s_pod_data(self) -> Dict[str, Dict[str, Any]]:
        """Initialize static k8s pod data for each service."""
        cluster_name = f"otel-demo-cluster-{secrets.token_hex(3)}"
        node_names = [f"gke-{cluster_name}-pool-{i}-{secrets.token_hex(4)}" for i in range(1, 4)]
        
        pod_data = {}
        for service in self.config.services:
            pod_name = f"{service.name}-{secrets.token_hex(4)}-{secrets.token_hex(3)}"
            node_name = secrets.choice(node_names)
            
            # Generate realistic pod start time (within last 7 days)
            start_time_offset = random.randint(0, 7 * 24 * 3600)  # 0-7 days ago
            start_time = datetime.now(timezone.utc).timestamp() - start_time_offset
            
            pod_data[service.name] = {
                'pod_name': pod_name,
                'pod_uid': str(uuid.uuid4()),
                'pod_ip': f"10.{random.randint(100, 120)}.{random.randint(1, 10)}.{random.randint(2, 250)}",
                'pod_start_time': datetime.fromtimestamp(start_time, timezone.utc).isoformat().replace('+00:00', 'Z'),
                'namespace': random.choice(['default', 'production', 'staging', f'{service.name}-ns']),
                'node_name': node_name,
                'cluster_name': cluster_name,
                'deployment_name': f"{service.name}-deployment",
                'replicaset_name': f"{service.name}-{secrets.token_hex(4)}",
                'host_ip': f"10.128.{random.randint(10, 50)}.{random.randint(100, 200)}",
                'zone': random.choice(['us-central1-a', 'us-central1-b', 'us-central1-c']),
            }
        
        return pod_data

    def _generate_k8s_resource_attributes(self, service: Service) -> Dict[str, Any]:
        """Generate k8s-specific resource attributes matching OTEL collector expectations."""
        pod_data = self._k8s_pod_data[service.name]
        
        # Core k8s attributes that the k8sattributes processor expects
        # These MUST match the extract.metadata configuration in the collector
        k8s_attributes = {
            "k8s.namespace.name": pod_data['namespace'],
            "k8s.deployment.name": pod_data['deployment_name'],
            "k8s.replicaset.name": pod_data['replicaset_name'],
            "k8s.node.name": pod_data['node_name'],
            "k8s.pod.name": pod_data['pod_name'],
            "k8s.pod.ip": pod_data['pod_ip'],
            "k8s.pod.uid": pod_data['pod_uid'],
            "k8s.pod.start_time": pod_data['pod_start_time'],
            "k8s.cluster.name": pod_data['cluster_name'],  # Expected by resource detection processors
        }
        
        # Service attributes - these are critical for APM integration
        service_attributes = {
            "service.name": service.name,
            "service.version": "1.2.3",
            "service.namespace": pod_data['namespace'],
            "service.instance.id": f"{service.name}-{pod_data['pod_name']}",
        }
        
        # Host attributes for resource detection processor compatibility
        host_attributes = {
            "host.name": pod_data['node_name'],
            "host.id": str(random.randint(6000000000000000000, 7000000000000000000)),
            "host.ip": pod_data['host_ip'],  # Single IP, not array
            "host.architecture": "amd64",
            "os.type": "linux",
        }
        
        # Cloud provider attributes for resource detection
        cloud_attributes = {
            "cloud.provider": "gcp",
            "cloud.region": "us-central1",
            "cloud.availability_zone": pod_data['zone'],
            "cloud.account.id": "otel-demo-project",
            "cloud.instance.id": str(random.randint(6000000000000000000, 7000000000000000000)),
        }
        
        # Telemetry SDK attributes
        telemetry_attributes = {
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.language": service.language,
            "telemetry.sdk.version": "1.24.0"
        }
        
        # Combine all attributes with k8s attributes taking precedence
        return {
            **host_attributes,
            **cloud_attributes,
            **telemetry_attributes,
            **service_attributes,
            **k8s_attributes,  # These should come last to override any conflicts
        }

    def _generate_k8s_telemetry(self):
        """The main loop for the k8s metrics generator thread."""
        # For demo purposes, send K8s metrics more frequently
        k8s_metrics_interval = 10  # Send every 10 seconds instead of 30
        
        print("Kubernetes metrics generation loop started.")
        while not self._stop_event.is_set():
            self.generate_and_send_k8s_metrics()
            self.generate_and_send_k8s_events()  # Also send K8s events
            
            # Wait for the interval or until stop event is set
            self._stop_event.wait(k8s_metrics_interval)
        
        print("Kubernetes metrics generation loop finished.")

    def generate_and_send_k8s_metrics(self):
        """Generates and sends Kubernetes pod metrics."""
        if not self.collector_url:
            print("Warning: OTLP endpoint not configured. Cannot send k8s metrics.")
            return
            
        k8s_metrics_payload = self.generate_k8s_metrics_payload()
        if k8s_metrics_payload.get("resourceMetrics"):
            self._send_payload(f"{self.collector_url}v1/metrics", k8s_metrics_payload, "k8s-metrics")

    def generate_and_send_k8s_events(self):
        """Generates and sends Kubernetes event logs."""
        if not self.collector_url:
            print("Warning: OTLP endpoint not configured. Cannot send k8s events.")
            return
            
        # Generate events occasionally (not every cycle to avoid spam)
        if random.random() < 0.3:  # 30% chance per cycle
            k8s_events_payload = self.generate_k8s_events_payload()
            if k8s_events_payload.get("resourceLogs"):
                self._send_payload(f"{self.collector_url}v1/logs", k8s_events_payload, "k8s-events")

    def generate_k8s_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate comprehensive OTLP metrics payload for Kubernetes resources."""
        resource_metrics = []
        current_time_ns = str(time.time_ns())
        
        # Generate pod metrics for each service
        for service in self.config.services:
            k8s_counters = self._k8s_counters[service.name]
            
            # Update network counters with realistic increments
            k8s_counters['network_rx_bytes'] += random.randint(10000, 100000)
            k8s_counters['network_tx_bytes'] += random.randint(15000, 120000)
            
            # Occasionally simulate pod restarts
            if random.random() < 0.002:  # 0.2% chance (increased for demo)
                k8s_counters['restart_count'] += 1
            
            # POD-LEVEL METRICS
            pod_metrics = []
            
            # Pod CPU usage metrics
            pod_metrics.append(self._create_gauge_metric(
                "k8s.pod.cpu.usage", 
                "ns", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(100000000, 2000000000))
                }]
            ))
            
            pod_metrics.append(self._create_gauge_metric(
                "k8s.pod.cpu_limit_utilization", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asDouble": random.uniform(0.05, 0.85)
                }]
            ))
            
            pod_metrics.append(self._create_gauge_metric(
                "k8s.pod.cpu.node.utilization", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asDouble": random.uniform(0.01, 0.15)
                }]
            ))
            
            # Pod memory usage metrics
            pod_metrics.append(self._create_gauge_metric(
                "k8s.pod.memory.usage", 
                "By", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(100000000, 800000000))
                }]
            ))
            
            pod_metrics.append(self._create_gauge_metric(
                "k8s.pod.memory_limit_utilization", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asDouble": random.uniform(0.1, 0.7)
                }]
            ))
            
            pod_metrics.append(self._create_gauge_metric(
                "k8s.pod.memory.node.utilization", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asDouble": random.uniform(0.001, 0.05)
                }]
            ))
            
            # Pod network metrics
            pod_metrics.append(self._create_sum_metric(
                "k8s.pod.network.rx", 
                "By", 
                True, 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(k8s_counters['network_rx_bytes'])
                }]
            ))
            
            pod_metrics.append(self._create_sum_metric(
                "k8s.pod.network.tx", 
                "By", 
                True, 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(k8s_counters['network_tx_bytes'])
                }]
            ))
            
            # Pod filesystem usage
            pod_metrics.append(self._create_gauge_metric(
                "k8s.pod.filesystem.usage", 
                "By", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(100000000, 500000000))
                }]
            ))
            
            # CONTAINER-LEVEL METRICS (missing from original)
            container_id = f"containerd://{secrets.token_hex(32)}"
            
            # Container CPU limit and request metrics
            pod_metrics.append({
                "name": "k8s.container.cpu_limit",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asDouble": random.uniform(0.5, 2.0),
                        "attributes": [
                            {"key": "container.name", "value": {"stringValue": f"{service.name}-container"}},
                            {"key": "container.id", "value": {"stringValue": container_id}}
                        ]
                    }]
                }
            })
            
            pod_metrics.append({
                "name": "k8s.container.cpu_request",
                "unit": "1", 
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asDouble": random.uniform(0.1, 1.0),
                        "attributes": [
                            {"key": "container.name", "value": {"stringValue": f"{service.name}-container"}},
                            {"key": "container.id", "value": {"stringValue": container_id}}
                        ]
                    }]
                }
            })
            
            # Container termination reason (for restart analysis)
            termination_reasons = ["Completed", "Error", "OOMKilled", "ContainerCannotRun"]
            if random.random() < 0.05:  # 5% chance of termination
                reason = secrets.choice(termination_reasons)
                pod_metrics.append({
                    "name": "k8s.container.status.last_terminated_reason",
                    "unit": "1",
                    "gauge": {
                        "dataPoints": [{
                            "timeUnixNano": current_time_ns,
                            "asInt": "1",
                            "attributes": [
                                {"key": "container.name", "value": {"stringValue": f"{service.name}-container"}},
                                {"key": "k8s.container.status.last_terminated_reason", "value": {"stringValue": reason}}
                            ]
                        }]
                    }
                })
            
            # Container restart metrics with reasons
            restart_reasons = ["CrashLoopBackOff", "OOMKilled", "Error", "Completed"]
            for reason in restart_reasons:
                restart_count = 1 if random.random() < 0.001 else 0
                if restart_count > 0:  # Only add if there's actually a restart
                    pod_metrics.append({
                        "name": "k8s.container.restarts",
                        "unit": "1",
                        "sum": {
                            "isMonotonic": True,
                            "aggregationTemporality": 2,
                            "dataPoints": [{
                                "timeUnixNano": current_time_ns,
                                "asInt": str(restart_count),
                                "attributes": [
                                    {"key": "container.name", "value": {"stringValue": f"{service.name}-container"}},
                                    {"key": "container.id", "value": {"stringValue": container_id}},
                                    {"key": "k8s.container.restart_reason", "value": {"stringValue": reason}}
                                ]
                            }]
                        }
                    })
            
            # Pod status metrics  
            pod_status_reasons = ["Running", "Pending", "Succeeded", "Failed"]
            for reason in pod_status_reasons:
                status_count = 1 if reason == "Running" else (1 if random.random() < 0.1 else 0)
                if status_count > 0:  # Only add if status is active
                    pod_metrics.append({
                        "name": "k8s.pod.status_reason",
                        "unit": "1", 
                        "gauge": {
                            "dataPoints": [{
                                "timeUnixNano": current_time_ns,
                                "asInt": str(status_count),
                                "attributes": [
                                    {"key": "k8s.pod.status_reason", "value": {"stringValue": reason}}
                                ]
                            }]
                        }
                    })
            
            # Create pod resource metrics with container attributes
            pod_resource_attrs = self._format_attributes({
                **self._generate_k8s_resource_attributes(service),
                "container.id": container_id,  # Add container ID to resource attributes
                "k8s.container.name": f"{service.name}-container"
            })
            
            resource_metrics.append({
                "resource": {"attributes": pod_resource_attrs},
                "scopeMetrics": [{
                    "scope": {
                        "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/kubeletstatsreceiver", 
                        "version": "1.0.0"
                    }, 
                    "metrics": pod_metrics
                }]
            })
        
        # Generate cluster-level metrics (one set per cluster)
        cluster_metrics = self._generate_cluster_level_metrics(current_time_ns)
        if cluster_metrics:
            resource_metrics.extend(cluster_metrics)
            
        return {"resourceMetrics": resource_metrics}

    def _generate_cluster_level_metrics(self, current_time_ns: str) -> List[Dict[str, Any]]:
        """Generate deployment, replicaset, and node level metrics."""
        cluster_resources = []
        
        # Get unique clusters, nodes, and namespaces
        clusters = set()
        nodes = set()
        namespaces = set()
        
        for service in self.config.services:
            pod_data = self._k8s_pod_data[service.name]
            clusters.add(pod_data['cluster_name'])
            nodes.add(pod_data['node_name'])
            namespaces.add(pod_data['namespace'])
        
        # Generate NODE-LEVEL METRICS
        for node_name in nodes:
            node_metrics = []
            
            # Node CPU metrics
            node_metrics.append(self._create_gauge_metric(
                "k8s.node.cpu.usage", 
                "ns", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(5000000000, 15000000000))
                }]
            ))
            
            # Node allocatable CPU (what the node can allocate to pods)
            node_metrics.append(self._create_gauge_metric(
                "k8s.node.allocatable_cpu", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asDouble": random.uniform(2.0, 8.0)  # 2-8 CPU cores
                }]
            ))
            
            # Node memory metrics
            node_metrics.append(self._create_gauge_metric(
                "k8s.node.memory.usage", 
                "By", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(2000000000, 8000000000))  # 2-8GB
                }]
            ))
            
            # Node memory working set (active memory)
            node_metrics.append(self._create_gauge_metric(
                "k8s.node.memory.working_set", 
                "By", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(1500000000, 6000000000))  # 1.5-6GB
                }]
            ))
            
            # Node allocatable memory
            node_metrics.append(self._create_gauge_metric(
                "k8s.node.allocatable_memory", 
                "By", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(8000000000, 16000000000))  # 8-16GB
                }]
            ))
            
            # Node filesystem metrics
            node_metrics.append(self._create_gauge_metric(
                "k8s.node.filesystem.usage", 
                "By", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(20000000000, 80000000000))  # 20-80GB
                }]
            ))
            
            node_metrics.append(self._create_gauge_metric(
                "k8s.node.filesystem.capacity", 
                "By", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(100000000000, 200000000000))  # 100-200GB
                }]
            ))
            
            # Node condition - Ready state
            node_metrics.append(self._create_gauge_metric(
                "k8s.node.condition_ready", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": "1"  # 1 = Ready, 0 = Not Ready
                }]
            ))
            
            node_metrics.append(self._create_gauge_metric(
                "k8s.node.uptime", 
                "s", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(86400, 2592000))  # 1 day to 30 days
                }]
            ))
            
            # Node resource attributes
            node_attrs = self._format_attributes({
                "k8s.node.name": node_name,
                "k8s.cluster.name": list(clusters)[0],  # Use first cluster
                "host.name": node_name,
                "cloud.provider": "gcp",
                "cloud.region": "us-central1"
            })
            
            cluster_resources.append({
                "resource": {"attributes": node_attrs},
                "scopeMetrics": [{
                    "scope": {
                        "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/k8sclusterreceiver", 
                        "version": "1.0.0"
                    }, 
                    "metrics": node_metrics
                }]
            })
        
        # Generate DEPLOYMENT-LEVEL METRICS
        for service in self.config.services:
            pod_data = self._k8s_pod_data[service.name]
            deployment_metrics = []
            
            # Deployment replica metrics
            deployment_metrics.append(self._create_gauge_metric(
                "k8s.deployment.replicas_desired", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(1, 5))
                }]
            ))
            
            deployment_metrics.append(self._create_gauge_metric(
                "k8s.deployment.replicas_available", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(1, 5))
                }]
            ))
            
            # Deployment resource attributes
            deployment_attrs = self._format_attributes({
                "k8s.deployment.name": pod_data['deployment_name'],
                "k8s.namespace.name": pod_data['namespace'],
                "k8s.cluster.name": pod_data['cluster_name']
            })
            
            cluster_resources.append({
                "resource": {"attributes": deployment_attrs},
                "scopeMetrics": [{
                    "scope": {
                        "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/k8sclusterreceiver", 
                        "version": "1.0.0"
                    }, 
                    "metrics": deployment_metrics
                }]
            })
            
            # Generate REPLICASET-LEVEL METRICS  
            replicaset_metrics = []
            
            replicaset_metrics.append(self._create_gauge_metric(
                "k8s.replicaset.replicas_desired", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(1, 3))
                }]
            ))
            
            replicaset_metrics.append(self._create_gauge_metric(
                "k8s.replicaset.replicas_ready", 
                "1", 
                [{
                    "timeUnixNano": current_time_ns, 
                    "asInt": str(random.randint(1, 3))
                }]
            ))
            
            # ReplicaSet resource attributes
            replicaset_attrs = self._format_attributes({
                "k8s.replicaset.name": pod_data['replicaset_name'],
                "k8s.deployment.name": pod_data['deployment_name'],
                "k8s.namespace.name": pod_data['namespace'],
                "k8s.cluster.name": pod_data['cluster_name']
            })
            
            cluster_resources.append({
                "resource": {"attributes": replicaset_attrs},
                "scopeMetrics": [{
                    "scope": {
                        "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/k8sclusterreceiver", 
                        "version": "1.0.0"
                    }, 
                    "metrics": replicaset_metrics
                }]
            })
        
        return cluster_resources

    def _generate_resource_attributes(self, service: Service) -> Dict[str, Any]:
        """Generates resource attributes for regular metrics compatible with collector processors."""
        lang = service.language.lower()
        runtime_info = self.RUNTIME_INFO.get(lang, {"name": lang, "version": "1.0.0"})
        
        # Get k8s pod data for this service to maintain consistency
        pod_data = self._k8s_pod_data[service.name]

        return {
            # Core service attributes
            "service.name": service.name,
            "service.namespace": pod_data['namespace'],
            "service.version": "1.2.3",
            "service.instance.id": f"{service.name}-{pod_data['pod_name']}",
            
            # Telemetry SDK attributes
            "telemetry.sdk.language": service.language,
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.24.0",
            
            # Runtime attributes
            "process.runtime.name": runtime_info["name"],
            "process.runtime.version": runtime_info["version"],
            
            # Cloud and host attributes to match GCP/GKE setup
            "cloud.provider": "gcp",
            "cloud.region": "us-central1",
            "cloud.availability_zone": pod_data['zone'],
            "deployment.environment": "production",
            "host.name": pod_data['node_name'],
            "os.type": "linux",
            
            # Basic k8s attributes for regular app metrics
            "k8s.cluster.name": pod_data['cluster_name'],
            "k8s.namespace.name": pod_data['namespace'],
            "k8s.pod.name": pod_data['pod_name'],
            "k8s.node.name": pod_data['node_name']
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
            
            # Debug: Log payload structure for metrics
            if signal_name == "k8s-metrics" and payload.get("resourceMetrics"):
                resource_count = len(payload["resourceMetrics"])
                if resource_count > 0:
                    metric_count = len(payload["resourceMetrics"][0].get("scopeMetrics", [{}])[0].get("metrics", []))
                    scope_name = payload["resourceMetrics"][0].get("scopeMetrics", [{}])[0].get("scope", {}).get("name", "unknown")
                    print(f"  📊 Sent {metric_count} k8s metrics from {resource_count} resources with scope: {scope_name}")
            
            # Debug: Log payload structure for K8s events
            if signal_name == "k8s-events" and payload.get("resourceLogs"):
                resource_count = len(payload["resourceLogs"])
                total_events = sum(len(rl.get("scopeLogs", [{}])[0].get("logRecords", [])) for rl in payload["resourceLogs"])
                if total_events > 0:
                    print(f"  📝 Sent {total_events} k8s events from {resource_count} resources")
            
        except httpx.RequestError as e:
            print(f"❌ Error sending {signal_name} to collector: {e}")
        except Exception as e:
            print(f"❌ An unexpected error occurred while sending {signal_name}: {e}")

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
                val_dict = {"intValue": value}
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

    def _get_latency_ns(self, latency_config: Optional['LatencyConfig']) -> int:
        """Calculates a latency in nanoseconds based on a LatencyConfig."""
        if latency_config and random.random() < latency_config.probability:
            return random.randint(latency_config.min_ms, latency_config.max_ms) * 1_000_000
        return 0

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
                self.service_resource_attributes.get(service_name, {"service.name": service_name})
            )

            otlp_spans = []
            for span in spans:
                otlp_spans.append({
                    "traceId": span["traceId"],
                    "spanId": span["spanId"],
                    "parentSpanId": span.get("parentSpanId", ""),
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
                "resource": {"attributes": resource_attrs},
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
                self.service_resource_attributes.get(service_name, {"service.name": service_name})
            )

            log_records = []
            for span in spans:
                info_log = {
                    "timeUnixNano": span["endTimeUnixNano"],
                    "severityText": "INFO",
                    "severityNumber": self.SEVERITY_NUMBER_MAP["INFO"],
                    "body": {"stringValue": f"Operation '{span['name']}' handled."},
                    "traceId": span["traceId"],
                    "spanId": span["spanId"],
                }
                log_records.append(info_log)

                if span["status"]["code"] == "STATUS_CODE_ERROR":
                    error_log = {
                        "timeUnixNano": span["endTimeUnixNano"],
                        "severityText": "ERROR",
                        "severityNumber": self.SEVERITY_NUMBER_MAP["ERROR"],
                        "body": {"stringValue": f"Operation '{span['name']}' failed unexpectedly."},
                        "traceId": span["traceId"],
                        "spanId": span["spanId"],
                        "attributes": self._format_attributes({"exception.type": "RuntimeException", "exception.message": "An artificial error occurred"}),
                    }
                    log_records.append(error_log)
            
            if not log_records:
                continue

            scope_logs = [{
                "scope": {"name": "otel-demo-generator"},
                "logRecords": log_records,
            }]

            resource_logs.append({
                "resource": {"attributes": resource_attrs},
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

            # --- Standard Metrics ---
            metrics.append(self._create_gauge_metric("system.cpu.utilization", "%", [
                {"timeUnixNano": current_time_ns, "asDouble": random.uniform(0.1, 0.9)}
            ]))
            metrics.append(self._create_gauge_metric("process.memory.usage", "By", [
                {"timeUnixNano": current_time_ns, "asInt": str(random.randint(200_000_000, 800_000_000))}
            ]))

            self._request_counters[service.name] += random.randint(5, 20)
            metrics.append(self._create_sum_metric("http.server.request.count", "requests", True, [
                {"timeUnixNano": current_time_ns, "asInt": str(self._request_counters[service.name])}
            ]))

            if random.random() < self.config.telemetry.error_rate:
                self._error_counters[service.name] += 1
            metrics.append(self._create_sum_metric("http.server.request.error.count", "errors", True, [
                {"timeUnixNano": current_time_ns, "asInt": str(self._error_counters[service.name])}
            ]))

            # --- Runtime-Specific Metrics ---
            lang = service.language.lower()
            if lang == "java":
                self._runtime_counters[service.name] += random.randint(0, 2)
                metrics.append(self._create_sum_metric("jvm.gc.collection_count", "collections", True, [
                    {"timeUnixNano": current_time_ns, "asInt": str(self._runtime_counters[service.name])}
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
                    {"timeUnixNano": current_time_ns, "asInt": str(self._runtime_counters[service.name])}
                 ]))
            
            resource_attrs = self._format_attributes(
                self.service_resource_attributes.get(service.name, {"service.name": service.name})
            )
            scope_metrics = [{"scope": {"name": "otel-demo-generator"}, "metrics": metrics}]
            resource_metrics.append({
                "resource": {"attributes": resource_attrs},
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
        trace_has_error = random.random() < self.config.telemetry.error_rate
        
        # If an error occurs, pick a random service to be the initial point of failure.
        error_source = secrets.choice(self.config.services).name if trace_has_error else None
        
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
        parent_span_id: str | None,
        trace_id: str,
        spans_by_service: Dict[str, List[Dict[str, Any]]],
        start_time_ns: int,
        error_source: str | None,
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
            own_processing_time_ns += self._get_latency_ns(operation.latency)

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
        network_hop_duration += self._get_latency_ns(dep.latency)

        downstream_start_time = start_time + network_hop_duration
        # The end time is now determined by the recursive call, so we set it later.
        # This is a placeholder, it will be updated after the recursive call returns.
        end_time = downstream_start_time 

        attributes = {
            'net.peer.name': dep.service,
            'user_agent.original': f"otel-demo-generator/{service.language}"
        }
        protocol = dep.protocol or 'http'

        if protocol == 'http':
            method = secrets.choice(['GET', 'POST', 'PUT', 'DELETE'])
            path = f"/{service.name.lower()}/{secrets.token_hex(4)}"
            attributes['http.request.method'] = method
            attributes['http.response.status_code'] = 200 # default, will be overwritten on error
            attributes['url.path'] = path
            attributes['url.full'] = f"http://{dep.service}{path}"
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
        duration += self._get_latency_ns(dep.latency)
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

    def generate_k8s_events_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP logs payload for Kubernetes events."""
        resource_logs = []
        current_time_ns = str(time.time_ns())
        
        # K8s event types and their typical reasons
        event_scenarios = [
            {
                "type": "Warning",
                "reason": "FailedScheduling", 
                "message": "0/3 nodes are available: 3 Insufficient memory.",
                "object_kind": "Pod",
                "weight": 0.1  # Less frequent
            },
            {
                "type": "Warning", 
                "reason": "Unhealthy",
                "message": "Readiness probe failed: HTTP probe failed with statuscode: 503",
                "object_kind": "Pod",
                "weight": 0.15
            },
            {
                "type": "Warning",
                "reason": "BackOff", 
                "message": "Back-off restarting failed container",
                "object_kind": "Pod",
                "weight": 0.1
            },
            {
                "type": "Warning",
                "reason": "FailedMount",
                "message": "Unable to attach or mount volumes: unmounted volumes=[config], unattached volumes=[config default-token]",
                "object_kind": "Pod", 
                "weight": 0.05
            },
            {
                "type": "Normal",
                "reason": "Scheduled",
                "message": "Successfully assigned default/{pod_name} to {node_name}",
                "object_kind": "Pod",
                "weight": 0.2
            },
            {
                "type": "Normal",
                "reason": "Pulling",
                "message": "Pulling image \"{service_name}:latest\"",
                "object_kind": "Pod",
                "weight": 0.15
            },
            {
                "type": "Normal", 
                "reason": "Pulled",
                "message": "Successfully pulled image \"{service_name}:latest\"",
                "object_kind": "Pod",
                "weight": 0.15
            },
            {
                "type": "Normal",
                "reason": "Created",
                "message": "Created container {service_name}",
                "object_kind": "Pod",
                "weight": 0.1
            }
        ]
        
        # Generate events for each service
        for service in self.config.services:
            pod_data = self._k8s_pod_data[service.name]
            
            # Randomly select 1-3 events for this service
            num_events = random.choices([0, 1, 2, 3], weights=[0.4, 0.3, 0.2, 0.1])[0]
            
            if num_events == 0:
                continue
                
            selected_events = random.choices(
                event_scenarios, 
                weights=[e["weight"] for e in event_scenarios],
                k=num_events
            )
            
            log_records = []
            
            for event in selected_events:
                # Format message with actual service/pod data
                message = event["message"].format(
                    service_name=service.name,
                    pod_name=pod_data['pod_name'],
                    node_name=pod_data['node_name']
                )
                
                # Create event log record
                event_time_ns = str(int(current_time_ns) - random.randint(0, 3600000000000))  # Within last hour
                
                log_record = {
                    "timeUnixNano": event_time_ns,
                    "severityText": "INFO" if event["type"] == "Normal" else "WARN",
                    "severityNumber": 9 if event["type"] == "Normal" else 13,
                    "body": {"stringValue": message},
                    "attributes": [
                        {"key": "k8s.event.type", "value": {"stringValue": event["type"]}},
                        {"key": "k8s.event.reason", "value": {"stringValue": event["reason"]}}, 
                        {"key": "k8s.event.object.kind", "value": {"stringValue": event["object_kind"]}},
                        {"key": "k8s.event.object.name", "value": {"stringValue": pod_data['pod_name']}},
                        {"key": "k8s.event.object.namespace", "value": {"stringValue": pod_data['namespace']}},
                        {"key": "k8s.event.object.uid", "value": {"stringValue": pod_data['pod_uid']}},
                        {"key": "k8s.event.count", "value": {"intValue": random.randint(1, 5)}},
                        {"key": "k8s.event.first_time", "value": {"stringValue": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}},
                        {"key": "k8s.event.last_time", "value": {"stringValue": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}},
                        {"key": "k8s.event.source.component", "value": {"stringValue": random.choice(["kubelet", "scheduler", "controller-manager", "deployment-controller"])}},
                        # Additional fields for better filtering
                        {"key": "log.level", "value": {"stringValue": "INFO" if event["type"] == "Normal" else "WARN"}},
                        {"key": "event.dataset", "value": {"stringValue": "kubernetes.events"}},
                        {"key": "event.module", "value": {"stringValue": "kubernetes"}},
                    ]
                }
                
                log_records.append(log_record)
            
            if log_records:
                # Resource attributes for K8s events (cluster-level)
                event_resource_attrs = self._format_attributes({
                    "k8s.cluster.name": pod_data['cluster_name'],
                    "k8s.namespace.name": pod_data['namespace'],
                    "cloud.provider": "gcp",
                    "cloud.region": "us-central1",
                    "event.dataset": "kubernetes.events",
                    "data_stream.type": "logs",
                    "data_stream.dataset": "kubernetes.events",
                    "data_stream.namespace": "default"
                })
                
                resource_logs.append({
                    "resource": {"attributes": event_resource_attrs},
                    "scopeLogs": [{
                        "scope": {
                            "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/k8sobjectsreceiver",
                            "version": "1.0.0"
                        },
                        "logRecords": log_records
                    }]
                })
        
        return {"resourceLogs": resource_logs}

def main_test():
    """Example usage for standalone testing of the generator."""
    yaml_content = """
services:
  - name: frontend
    language: javascript
    depends_on: []
telemetry:
  trace_rate: 1
  error_rate: 0.1
  metrics_interval: 5
  include_logs: true
"""
    generator = None
    try:
        config_data = yaml.safe_load(yaml_content)
        scenario_config = ScenarioConfig(**config_data)
        generator = TelemetryGenerator(config=scenario_config, otlp_endpoint="http://localhost:4318")
        generator.start()
        print("Generator started for testing. Running for 15 seconds.")
        time.sleep(15)
    except (yaml.YAMLError, Exception) as e:
        print(f"Error during testing setup: {e}")
    finally:
        if generator:
            generator.stop()

if __name__ == "__main__":
    main_test() 