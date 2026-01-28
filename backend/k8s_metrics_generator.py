import secrets
import random
import uuid
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from config_schema import ScenarioConfig, Service


class K8sMetricsGenerator:
    """
    Generates Kubernetes-specific metrics and events following semantic conventions.
    Fixed for Elastic ingestion - addresses missing fields.
    """
    
    SCHEMA_URL = "https://opentelemetry.io/schemas/1.35.0"
    
    def __init__(self, config: ScenarioConfig):
        self.config = config
        self.services_map = {s.name: s for s in self.config.services}
        
        # Initialize K8s pod data
        self._k8s_pod_data = self._initialize_k8s_pod_data()
        
        # Generate and store container IDs for consistency
        self._container_ids = {
            s.name: f"containerd://{secrets.token_hex(32)}"
            for s in self.config.services
        }
        
        # K8s-specific counters
        self._k8s_counters = {
            s.name: {
                'network_rx_bytes': random.randint(50000000, 100000000),
                'network_tx_bytes': random.randint(70000000, 120000000),
                'restart_count': 0
            } for s in self.config.services
        }

    def _initialize_k8s_pod_data(self) -> Dict[str, Dict[str, Any]]:
        """Initialize static k8s pod data for each service with realistic cloud platform."""
        # Cloud/platform configurations
        cloud_platforms = {
            'aws_eks': {
                'provider': 'aws',
                'platform': 'aws_eks',
                'region': 'us-east-1',
                'zones': ['us-east-1a', 'us-east-1b', 'us-east-1c'],
                'node_prefix': 'ip-10-0-',
                'cluster_suffix': 'eks-cluster',
                'os_description': 'Amazon Linux 2',
                'kubelet_version': 'v1.29.10-eks-59bf375'
            },
            'gcp_gke': {
                'provider': 'gcp',
                'platform': 'gcp_gke',
                'region': 'us-central1',
                'zones': ['us-central1-a', 'us-central1-b', 'us-central1-c'],
                'node_prefix': 'gke-',
                'cluster_suffix': 'gke-cluster',
                'os_description': 'Container-Optimized OS',
                'kubelet_version': 'v1.29.8-gke.1031000'
            },
            'azure_aks': {
                'provider': 'azure',
                'platform': 'azure_aks',
                'region': 'eastus',
                'zones': ['eastus-1', 'eastus-2', 'eastus-3'],
                'node_prefix': 'aks-',
                'cluster_suffix': 'aks-cluster',
                'os_description': 'Ubuntu 22.04.5 LTS',
                'kubelet_version': 'v1.29.9'
            },
            'openshift': {
                'provider': 'openshift',
                'platform': 'openshift',
                'region': 'datacenter-1',
                'zones': ['rack-1', 'rack-2', 'rack-3'],
                'node_prefix': 'worker-',
                'cluster_suffix': 'ocp-cluster',
                'os_description': 'Red Hat Enterprise Linux CoreOS 415.92',
                'kubelet_version': 'v1.28.6+openshift'
            },
            'on_prem': {
                'provider': 'on_prem',
                'platform': 'kubernetes',
                'region': 'datacenter',
                'zones': ['zone-a', 'zone-b', 'zone-c'],
                'node_prefix': 'k8s-worker-',
                'cluster_suffix': 'k8s-cluster',
                'os_description': 'Ubuntu 22.04.4 LTS',
                'kubelet_version': 'v1.29.2'
            }
        }

        # Use configured cloud platform or select randomly
        configured_platform = getattr(self.config, 'cloud_platform', None)
        if configured_platform and configured_platform in cloud_platforms:
            cloud_config = cloud_platforms[configured_platform]
        else:
            cloud_config = secrets.choice(list(cloud_platforms.values()))
        
        cluster_name = f"otel-demo-{cloud_config['cluster_suffix']}-{secrets.token_hex(3)}"
        
        # Generate node names based on cloud platform
        if cloud_config['provider'] == 'aws':
            node_names = [
                f"{cloud_config['node_prefix']}{random.randint(10, 200)}-{random.randint(10, 200)}.{cloud_config['region']}.compute.internal"
                for _ in range(3)
            ]
        elif cloud_config['provider'] == 'gcp':
            node_names = [
                f"{cloud_config['node_prefix']}{cluster_name}-pool-{i}-{secrets.token_hex(4)}"
                for i in range(1, 4)
            ]
        elif cloud_config['provider'] == 'azure':
            node_names = [
                f"{cloud_config['node_prefix']}agentpool-{secrets.token_hex(4)}-vmss000000{i}"
                for i in range(3)
            ]
        elif cloud_config['provider'] == 'openshift':
            # OpenShift style: worker-0.ocp-cluster.example.com
            node_names = [
                f"{cloud_config['node_prefix']}{i}.{cluster_name}.example.com"
                for i in range(3)
            ]
        else:  # on_prem
            # On-prem style: k8s-worker-01.cluster.local
            node_names = [
                f"{cloud_config['node_prefix']}{i:02d}.{cluster_name}.local"
                for i in range(3)
            ]
        
        pod_data = {}
        for service in self.config.services:
            pod_name = f"{service.name}-{secrets.token_hex(4)}-{secrets.token_hex(3)}"
            node_name = secrets.choice(node_names)
            
            # Generate realistic pod start time (within last 7 days)
            start_time_offset = random.randint(0, 7 * 24 * 3600)
            start_time = datetime.now(timezone.utc).timestamp() - start_time_offset
            
            # Generate node UID
            node_uid = str(uuid.uuid4())
            
            pod_data[service.name] = {
                # Pod attributes
                'pod_name': pod_name,
                'pod_uid': str(uuid.uuid4()),
                'pod_ip': f"10.{random.randint(100, 120)}.{random.randint(1, 10)}.{random.randint(2, 250)}",
                'pod_start_time': datetime.fromtimestamp(start_time, timezone.utc).isoformat().replace('+00:00', 'Z'),
                'namespace': random.choice(['default', 'production', 'staging', f'{service.name}-ns']),
                
                # Node attributes
                'node_name': node_name,
                'node_uid': node_uid,
                'host_ip': f"10.{random.randint(10, 50)}.{random.randint(100, 200)}",
                
                # Cluster attributes
                'cluster_name': cluster_name,
                'deployment_name': f"{service.name}-deployment",
                'replicaset_name': f"{service.name}-{secrets.token_hex(4)}",
                
                # Cloud platform attributes
                'cloud_provider': cloud_config['provider'],
                'cloud_platform': cloud_config['platform'],
                'cloud_region': cloud_config['region'],
                'zone': secrets.choice(cloud_config['zones']),
                'os_description': cloud_config['os_description'],
                'kubelet_version': cloud_config['kubelet_version'],
            }
        
        return pod_data

    def generate_k8s_resource_attributes(self, service: Service) -> Dict[str, Any]:
        """Generate k8s-specific resource attributes with all semantic convention fields."""
        pod_data = self._k8s_pod_data[service.name]
        
        # Use stored container ID for this service
        container_id = self._container_ids[service.name]
        
        # Core k8s attributes
        k8s_attributes = {
            "k8s.namespace.name": pod_data['namespace'],
            "k8s.deployment.name": pod_data['deployment_name'],
            "k8s.replicaset.name": pod_data['replicaset_name'],
            "k8s.node.name": pod_data['node_name'],
            "k8s.node.uid": pod_data['node_uid'],
            "k8s.pod.name": pod_data['pod_name'],
            "k8s.pod.ip": pod_data['pod_ip'],
            "k8s.pod.uid": pod_data['pod_uid'],
            "k8s.pod.start_time": pod_data['pod_start_time'],
            "k8s.cluster.name": pod_data['cluster_name'],
            "k8s.kubelet.version": pod_data['kubelet_version'],
        }
        
        # CRITICAL FIX: Container attributes need to be at resource level for Elastic
        container_attributes = {
            "container.name": f"{service.name}-container",
            "container.id": container_id,  # This was missing at resource level
            "container.image.name": f"{service.name}:latest",
            "container.image.tag": "latest",
            "container.image.tags": ["latest", "v1.2.3"],  # Elasticsearch exporter maps this to container.image.tag
            "k8s.container.status.last_terminated_reason": random.choice([
                "Completed", "OOMKilled", "Error", "ContainerCannotRun"
            ]) if random.random() < 0.1 else "Completed",
        }
        
        # Service attributes
        service_attributes = {
            "service.name": service.name,
            "service.version": "1.2.3",
            "service.namespace": pod_data['namespace'],
            "service.instance.id": f"{service.name}-{pod_data['pod_name']}",
        }
        
        # Host attributes
        host_attributes = {
            "host.name": pod_data['node_name'],
            "host.id": str(random.randint(6000000000000000000, 7000000000000000000)),
            "host.ip": pod_data['host_ip'],
            "host.architecture": "amd64",
            "os.type": "linux",
            "os.description": pod_data['os_description'],
        }
        
        # Cloud provider attributes
        cloud_attributes = {
            "cloud.provider": pod_data['cloud_provider'],
            "cloud.platform": pod_data['cloud_platform'],
            "cloud.region": pod_data['cloud_region'],
            "cloud.availability_zone": pod_data['zone'],
            "cloud.account.id": f"otel-demo-{pod_data['cloud_provider']}-account",
            "cloud.instance.id": str(random.randint(6000000000000000000, 7000000000000000000)),
        }
        
        # Telemetry SDK attributes
        language_value = (service.language or "python").lower()
        telemetry_attributes = {
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.language": language_value,
            "telemetry.sdk.version": "1.24.0"
        }
        
        # Additional realistic K8s attributes
        k8s_labels = {
            "k8s.pod.label.app": service.name,
            "k8s.pod.label.version": "v1.2.3",
            "k8s.pod.label.component": service.role if hasattr(service, 'role') else "backend",
            "k8s.pod.label.managed-by": "helm",
            "k8s.pod.label.part-of": "otel-demo-app",
            "k8s.deployment.label.app": service.name,
            "k8s.deployment.label.version": "v1.2.3",
        }
        
        # Common K8s annotations
        k8s_annotations = {
            "k8s.pod.annotation.kubernetes.io/created-by": '{"kind":"SerializedReference","apiVersion":"v1","reference":{"kind":"ReplicaSet","namespace":"' + pod_data['namespace'] + '","name":"' + pod_data['replicaset_name'] + '"}}',
            "k8s.pod.annotation.prometheus.io/scrape": "true",
            "k8s.pod.annotation.prometheus.io/port": "8080",
            "k8s.pod.annotation.prometheus.io/path": "/metrics",
        }
        
        return {
            **host_attributes,
            **cloud_attributes,
            **telemetry_attributes,
            **service_attributes,
            **container_attributes,  # CRITICAL: This ensures container.id is at resource level
            **k8s_attributes,
            **k8s_labels,
            **k8s_annotations,
            
            # CRITICAL: Data stream attributes for Elastic routing
            "data_stream.type": "metrics",
            "data_stream.dataset": "kubernetes.container", 
            "data_stream.namespace": "default"
        }

    def generate_k8s_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate comprehensive OTLP metrics payload for Kubernetes resources."""
        resource_metrics = []
        current_time_ns = str(time.time_ns())
        
        # Generate pod metrics for each service
        for service in self.config.services:
            k8s_counters = self._k8s_counters[service.name]
            
            # Update network counters
            k8s_counters['network_rx_bytes'] += random.randint(10000, 100000)
            k8s_counters['network_tx_bytes'] += random.randint(15000, 120000)
            
            # Occasionally simulate pod restarts
            if random.random() < 0.002:
                k8s_counters['restart_count'] += 1
            
            # Generate pod metrics
            pod_metrics = self._generate_pod_metrics(current_time_ns, service, k8s_counters)
            
            # Create resource with schema URL
            resource_attrs = self._format_attributes(self.generate_k8s_resource_attributes(service))
            
            resource_metrics.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": "https://opentelemetry.io/schemas/1.35.0"
                },
                "scopeMetrics": [{
                    "scope": {
                        "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/kubeletstatsreceiver",
                        "version": "8.16.0"
                    },
                    "metrics": pod_metrics
                }]
            })
        
        # Generate cluster-level metrics
        cluster_metrics = self._generate_cluster_level_metrics(current_time_ns)
        if cluster_metrics:
            resource_metrics.extend(cluster_metrics)
            
        return {"resourceMetrics": resource_metrics}

    def _generate_pod_metrics(self, current_time_ns: str, service: Service, k8s_counters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate pod-level metrics."""
        pod_metrics = []
        
        # Pod CPU metrics
        pod_metrics.extend([
            self._create_gauge_metric("k8s.pod.cpu.usage", "ns", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(10000000, 500000000))
            }]),
            self._create_gauge_metric("k8s.pod.cpu_limit_utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(0.05, 0.85)
            }]),
            self._create_gauge_metric("k8s.pod.cpu.node.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(0.01, 0.15)
            }])
        ])
        
        # Pod memory metrics
        pod_metrics.extend([
            self._create_gauge_metric("k8s.pod.memory.usage", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(100000000, 800000000))
            }]),
            self._create_gauge_metric("k8s.pod.memory_limit_utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(0.1, 0.7)
            }]),
            self._create_gauge_metric("k8s.pod.memory.node.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(0.001, 0.05)
            }])
        ])

        # Pod working set memory at pod scope for "Top memory‑intensive nodes"
        pod_metrics.append(
            self._create_gauge_metric("k8s.pod.memory.working_set", "By", [{
                 "timeUnixNano": current_time_ns,
                 "asInt": str(random.randint(80_000_000, 600_000_000))
            }])
        )
        
        # Pod network metrics
        pod_metrics.extend([
            self._create_sum_metric("k8s.pod.network.rx", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(k8s_counters['network_rx_bytes'])
            }]),
            self._create_sum_metric("k8s.pod.network.tx", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(k8s_counters['network_tx_bytes'])
            }])
        ])
        
        # Pod filesystem usage
        pod_metrics.append(self._create_gauge_metric("k8s.pod.filesystem.usage", "By", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(random.randint(100000000, 500000000))
        }]))
        
        # Pod volume metrics
        pod_metrics.extend([
            {
                "name": "k8s.pod.volume.usage",
                "unit": "By",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(random.randint(10000000, 100000000)),
                        "attributes": [
                            {"key": "volume.name", "value": {"stringValue": f"{service.name}-data"}},
                            {"key": "volume.type", "value": {"stringValue": "persistentVolumeClaim"}}
                        ]
                    }]
                }
            },
            {
                "name": "k8s.pod.volume.capacity",
                "unit": "By",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(random.randint(1000000000, 10000000000)),
                        "attributes": [
                            {"key": "volume.name", "value": {"stringValue": f"{service.name}-data"}},
                            {"key": "volume.type", "value": {"stringValue": "persistentVolumeClaim"}}
                        ]
                    }]
                }
            }
        ])
        
        # Pod status metrics
        pod_metrics.extend([
            {
                "name": "k8s.pod.phase",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": "1",
                        "attributes": [
                            {"key": "pod.phase", "value": {"stringValue": "Running"}}
                        ]
                    }]
                }
            },
            self._create_gauge_metric("k8s.pod.ready", "1", [{
                "timeUnixNano": current_time_ns,
                "asInt": "1" if random.random() < 0.95 else "0"
            }])
        ])
        
        # Container metrics with attributes
        container_id = self._container_ids[service.name]
        container_metrics = self._generate_container_metrics(current_time_ns, service, container_id)
        pod_metrics.extend(container_metrics)
        
        return pod_metrics

    def _generate_container_metrics(self, current_time_ns: str, service: Service, container_id: str) -> List[Dict[str, Any]]:
        """Generate container-level metrics with proper OTLP format for Elastic."""
        container_metrics = []
        
        # Base attrs reused by every container datapoint
        base_attrs = [
            {"key": "container.name", "value": {"stringValue": f"{service.name}-container"}},
            {"key": "container.id", "value": {"stringValue": container_id}}
        ]

        # CPU usage (needed by Lens) 
        container_metrics.append(
            self._create_gauge_metric("k8s.container.cpu.usage", "ns", [{
                 "timeUnixNano": current_time_ns,
                 "asInt": str(random.randint(10_000_000, 600_000_000)),
                 "attributes": base_attrs
            }])
        )

        # CRITICAL FIX: Memory request/limit metrics must use gauge type
        # Elastic expects these as gauge metrics, not sum metrics
        container_metrics.extend([
            self._create_gauge_metric("k8s.container.memory_request", "By", [{
                 "timeUnixNano": current_time_ns,
                 "asInt": str(random.randint(128*2**20, 512*2**20)),  # 128MB to 512MB
                 "attributes": base_attrs
            }]),
            self._create_gauge_metric("k8s.container.memory_limit", "By", [{
                 "timeUnixNano": current_time_ns,
                 "asInt": str(random.randint(256*2**20, 1024*2**20)),  # 256MB to 1GB
                 "attributes": base_attrs
            }]),
            self._create_gauge_metric("k8s.container.cpu_limit", "{cpu}", [{
                 "timeUnixNano": current_time_ns,
                 "asDouble": random.uniform(0.5, 2.0),
                 "attributes": base_attrs
            }]),
            self._create_gauge_metric("k8s.container.cpu_request", "{cpu}", [{
                 "timeUnixNano": current_time_ns,
                 "asDouble": random.uniform(0.1, 1.0),
                 "attributes": base_attrs
            }])
        ])

        # Keep working set as gauge
        container_metrics.append(
            self._create_gauge_metric("k8s.container.memory.working_set", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(100000000, 400000000)),
                "attributes": base_attrs
            }])
        )
        
        # Container state and status metrics
        container_metrics.extend([
            {
                "name": "k8s.container.ready",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": "1" if random.random() < 0.95 else "0",
                        "attributes": base_attrs
                    }]
                }
            },
            {
                "name": "k8s.container.state_code",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": "2",  # 2 = running, 1 = waiting, 3 = terminated
                        "attributes": base_attrs + [
                            {"key": "container.state", "value": {"stringValue": "running"}}
                        ]
                    }]
                }
            }
        ])
        
        # CRITICAL FIX: Container restart metrics using proper name
        restart_count = self._k8s_counters[service.name]['restart_count']
        container_metrics.append(
            self._create_sum_metric("k8s.container.restarts", "{restart}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(restart_count),
                "attributes": base_attrs
            }])
        )
        
        return container_metrics

    def _generate_cluster_level_metrics(self, current_time_ns: str) -> List[Dict[str, Any]]:
        """Generate deployment, replicaset, and node level metrics."""
        cluster_resources = []
        
        # Get unique nodes for node-level metrics
        nodes = set()
        for service in self.config.services:
            pod_data = self._k8s_pod_data[service.name]
            nodes.add(pod_data['node_name'])
        
        # Generate node-level metrics
        for node_name in nodes:
            node_metrics = self._generate_node_metrics(current_time_ns)
            
            # Use first service's cloud config for node attributes
            first_service = self.config.services[0]
            pod_data = self._k8s_pod_data[first_service.name]
            container_id = self._container_ids[first_service.name]
            
            node_attrs = self._format_attributes({
                "k8s.node.name": node_name,
                "k8s.node.uid": pod_data['node_uid'],
                "k8s.cluster.name": pod_data['cluster_name'],
                "k8s.kubelet.version": pod_data['kubelet_version'],
                "host.name": node_name,
                "cloud.provider": pod_data['cloud_provider'],
                "cloud.platform": pod_data['cloud_platform'],
                "cloud.region": pod_data['cloud_region'],
                "os.type": "linux",
                "os.description": pod_data['os_description'],
                "container.id": container_id,
            })
            
            cluster_resources.append({
                "resource": {
                    "attributes": node_attrs,
                    "schemaUrl": "https://opentelemetry.io/schemas/1.35.0"
                },
                "scopeMetrics": [{
                    "scope": {
                        "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/k8sclusterreceiver",
                        "version": "8.16.0"
                    },
                    "metrics": node_metrics
                }]
            })
        
        # Generate deployment and replicaset metrics
        deployment_metrics = self._generate_deployment_metrics(current_time_ns)
        cluster_resources.extend(deployment_metrics)
        
        return cluster_resources

    def _generate_node_metrics(self, current_time_ns: str) -> List[Dict[str, Any]]:
        """Generate node-level metrics."""
        # CRITICAL FIX: Generate CPU values for realistic dashboard percentages (100s of %)
        # Target: cpu.usage / allocatable_cpu should yield 2-8 (200%-800%)
        allocatable_cores = random.uniform(2.0, 8.0)
        utilization_fraction = random.uniform(0.1, 0.8)
        
        # Scale to get hundreds of percent - further reduced scaling
        # Using much smaller scaling: 4 cores * 50% * 100 = 200ns → 200/4 = 50 (50%)
        cpu_usage_ns = int(allocatable_cores * utilization_fraction * 10)
        
        return [
            # CPU metrics - Fixed scaling
            self._create_gauge_metric("k8s.node.cpu.usage", "ns", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(cpu_usage_ns)
            }]),
            self._create_gauge_metric("k8s.node.allocatable_cpu", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": allocatable_cores
            }]),
            self._create_gauge_metric("k8s.node.cpu.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": utilization_fraction
            }]),
            
            # Memory metrics  
            self._create_gauge_metric("k8s.node.memory.usage", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(2000000000, 8000000000))
            }]),
            # CRITICAL FIX: Node memory working set
            self._create_gauge_metric("k8s.node.memory.working_set", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(1500000000, 6000000000))
            }]),
            self._create_gauge_metric("k8s.node.allocatable_memory", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(8000000000, 16000000000))
            }]),
            self._create_gauge_metric("k8s.node.memory.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(0.2, 0.7)
            }]),
            
            # Filesystem metrics
            self._create_gauge_metric("k8s.node.filesystem.usage", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(20000000000, 80000000000))
            }]),
            self._create_gauge_metric("k8s.node.filesystem.capacity", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(100000000000, 200000000000))
            }]),
            self._create_gauge_metric("k8s.node.filesystem.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(0.1, 0.6)
            }]),
            
            # Network metrics
            self._create_sum_metric("k8s.node.network.rx", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(1000000000, 10000000000))
            }]),
            self._create_sum_metric("k8s.node.network.tx", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(1000000000, 10000000000))
            }]),
            
            # Node conditions
            self._create_gauge_metric("k8s.node.condition_ready", "1", [{
                "timeUnixNano": current_time_ns,
                "asInt": "1"
            }]),
            self._create_gauge_metric("k8s.node.condition_memory_pressure", "1", [{
                "timeUnixNano": current_time_ns,
                "asInt": "1" if random.random() < 0.1 else "0"
            }]),
            self._create_gauge_metric("k8s.node.condition_disk_pressure", "1", [{
                "timeUnixNano": current_time_ns,
                "asInt": "1" if random.random() < 0.05 else "0"
            }]),
            self._create_gauge_metric("k8s.node.condition_network_unavailable", "1", [{
                "timeUnixNano": current_time_ns,
                "asInt": "1" if random.random() < 0.02 else "0"
            }])
        ]

    def _generate_deployment_metrics(self, current_time_ns: str) -> List[Dict[str, Any]]:
        """Generate deployment and replicaset metrics."""
        deployment_resources = []
        
        for service in self.config.services:
            pod_data = self._k8s_pod_data[service.name]
            container_id = self._container_ids[service.name]
            
            # Deployment metrics
            deployment_metrics = [
                self._create_gauge_metric("k8s.deployment.replicas_desired", "1", [{
                    "timeUnixNano": current_time_ns,
                    "asInt": str(random.randint(1, 5))
                }]),
                self._create_gauge_metric("k8s.deployment.replicas_available", "1", [{
                    "timeUnixNano": current_time_ns,
                    "asInt": str(random.randint(1, 5))
                }])
            ]
            
            deployment_attrs = self._format_attributes({
                "k8s.deployment.name": pod_data['deployment_name'],
                "k8s.namespace.name": pod_data['namespace'],
                "k8s.cluster.name": pod_data['cluster_name'],
                "cloud.provider": pod_data['cloud_provider'],
                "cloud.platform": pod_data['cloud_platform'],
                "container.id": container_id,
            })
            
            deployment_resources.append({
                "resource": {
                    "attributes": deployment_attrs,
                    "schemaUrl": "https://opentelemetry.io/schemas/1.35.0"
                },
                "scopeMetrics": [{
                    "scope": {
                        "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/k8sclusterreceiver",
                        "version": "8.16.0"
                    },
                    "metrics": deployment_metrics
                }]
            })
        
        return deployment_resources

    def generate_k8s_logs_payload(self) -> Dict[str, List[Any]]:
        resource_logs = []
        current_time_ns = str(time.time_ns())
        
        event_scenarios = [
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "0/3 nodes are available: 3 Insufficient memory.",
                "object_kind": "Pod",
                "weight": 0.1
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
                "reason": "Failed",
                "message": "Error: container failed to start",
                "object_kind": "Pod",
                "weight": 0.08
            },
            {
                "type": "Normal",
                "reason": "Scheduled",
                "message": "Successfully assigned {namespace}/{pod_name} to {node_name}",
                "object_kind": "Pod",
                "weight": 0.2
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
            },
            {
                "type": "Normal",
                "reason": "Started",
                "message": "Started container {service_name}",
                "object_kind": "Pod",
                "weight": 0.1
            },
            {
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off restarting failed container",
                "object_kind": "Pod",
                "weight": 0.05
            },
            {
                "type": "Warning",
                "reason": "FailedMount",
                "message": "MountVolume.SetUp failed for volume \"pvc-123\" : mount failed: exit status 32",
                "object_kind": "Pod",
                "weight": 0.03
            },
            {
                "type": "Normal",
                "reason": "SuccessfulCreate",
                "message": "Created pod: {pod_name}",
                "object_kind": "ReplicaSet",
                "weight": 0.07
            },
            {
                "type": "Normal",
                "reason": "ScalingReplicaSet",
                "message": "Scaled up replica set {service_name}-{namespace} to 3",
                "object_kind": "Deployment",
                "weight": 0.05
            }
        ]
        
        for service in self.config.services:
            pod_data = self._k8s_pod_data[service.name]
            
            # Generate 1-2 events per service
            num_events = random.choices([0, 1, 2], weights=[0.5, 0.3, 0.2])[0]
            
            if num_events == 0:
                continue
                
            selected_events = random.choices(
                event_scenarios,
                weights=[e["weight"] for e in event_scenarios],
                k=num_events
            )
            
            log_records = []
            for event in selected_events:
                message = event["message"].format(
                    service_name=service.name,
                    pod_name=pod_data['pod_name'],
                    node_name=pod_data['node_name'],
                    namespace=pod_data['namespace']
                )
                
                event_time_ns = str(int(current_time_ns) - random.randint(0, 3600000000000))
                
                # Convert event time to ISO format for K8s fields
                event_time_iso = datetime.fromtimestamp(
                    int(event_time_ns) / 1_000_000_000, 
                    timezone.utc
                ).isoformat().replace('+00:00', 'Z')
                
                # Generate event name and resource versions
                event_name = f"{pod_data['pod_name']}.{secrets.token_hex(8)}"
                resource_version = str(random.randint(1000000, 9999999))
                regarding_resource_version = str(random.randint(1000000, 9999999))
                
                # CRITICAL FIX: Restructure body for Elastic ingestion pipeline
                # Elastic expects the structured data at the top level of body
                # Create structured body matching real K8s event format
                structured_body = {
                    "object.apiVersion": "events.k8s.io/v1",
                    "object.deprecatedCount": random.randint(1, 10),
                    "object.deprecatedFirstTimestamp": event_time_iso,
                    "object.deprecatedLastTimestamp": event_time_iso,
                    "object.deprecatedSource.component": random.choice(["kubelet", "scheduler", "controller-manager", "kube-proxy"]),
                    "object.deprecatedSource.host": pod_data['node_name'],
                    "object.kind": "Event",
                    "object.metadata.creationTimestamp": event_time_iso,
                    "object.metadata.managedFields.apiVersion": "v1",
                    "object.metadata.managedFields.fieldsType": "FieldsV1",
                    "object.metadata.managedFields.manager": "kubelet",
                    "object.metadata.managedFields.operation": "Update",
                    "object.metadata.managedFields.time": event_time_iso,
                    "object.metadata.name": event_name,
                    "object.metadata.namespace": pod_data['namespace'],
                    "object.metadata.resourceVersion": resource_version,
                    "object.metadata.uid": str(uuid.uuid4()),
                    "object.note": message,
                    "object.reason": event["reason"],
                    "object.regarding.apiVersion": "v1",
                    "object.regarding.kind": event["object_kind"],
                    "object.regarding.name": pod_data['pod_name'],
                    "object.regarding.namespace": pod_data['namespace'],
                    "object.regarding.resourceVersion": regarding_resource_version,
                    "object.regarding.uid": pod_data['pod_uid'],
                    "object.reportingController": "kubelet",
                    "object.reportingInstance": pod_data['node_name'],
                    "object.type": event["type"],
                    "type": "MODIFIED"
                }
                
                log_record = {
                    "timeUnixNano": event_time_ns,
                    "severityText": "INFO" if event["type"] == "Normal" else "WARN",
                    "severityNumber": 9 if event["type"] == "Normal" else 13,
                    "body": {

                                    "kvlistValue": {                  # ✅ map ⇒ flat keys
                "values": self._format_attributes(structured_body)
            }
                    },
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": event_name}},
                        {"key": "event.domain", "value": {"stringValue": "k8s"}},
                        {"key": "k8s.event.type", "value": {"stringValue": event["type"]}},
                        {"key": "k8s.event.reason", "value": {"stringValue": event["reason"]}},
                        {"key": "k8s.event.object.kind", "value": {"stringValue": event["object_kind"]}},
                        {"key": "k8s.event.object.name", "value": {"stringValue": pod_data['pod_name']}},
                        {"key": "k8s.event.object.namespace", "value": {"stringValue": pod_data['namespace']}},
                        {"key": "k8s.event.object.uid", "value": {"stringValue": pod_data['pod_uid']}},
                        {"key": "k8s.event.count", "value": {"intValue": random.randint(1, 5)}},
                        {"key": "event.dataset", "value": {"stringValue": "generic"}},
                        {"key": "event.module", "value": {"stringValue": "kubernetes"}},
                    ]
                }
                
                log_records.append(log_record)
            
            if log_records:
                event_resource_attrs = self._format_attributes({
                    "k8s.cluster.name": pod_data['cluster_name'],
                    "k8s.namespace.name": pod_data['namespace'],
                    "cloud.provider": pod_data['cloud_provider'],
                    "cloud.platform": pod_data['cloud_platform'],
                    "cloud.region": pod_data['cloud_region'],
                    "data_stream.type": "logs",
                    "data_stream.dataset": "generic",
                    "data_stream.namespace": "default"
                })
                
                resource_logs.append({
                    "resource": {
                        "attributes": event_resource_attrs,
                        "schemaUrl": "https://opentelemetry.io/schemas/1.35.0"
                    },
                    "scopeLogs": [{
                        "scope": {
                            "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/k8sobjectsreceiver",
                            "version": "8.16.0"
                        },
                        "logRecords": log_records
                    }]
                })
        
        return {"resourceLogs": resource_logs}

    def _create_gauge_metric(self, name: str, unit: str, data_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a gauge metric."""
        return {"name": name, "unit": unit, "gauge": {"dataPoints": data_points}}

    def _create_sum_metric(self, name: str, unit: str, is_monotonic: bool, data_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a sum metric."""
        return {"name": name, "unit": unit, "sum": {"isMonotonic": is_monotonic, "aggregationTemporality": 2, "dataPoints": data_points}}

    def _format_attributes(self, attrs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert attributes dict to OTLP format."""
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

    def _format_nested_attributes(self, attrs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert nested attributes dict to OTLP format, preserving structure."""
        formatted = []
        for key, value in attrs.items():
            if isinstance(value, dict):
                # For nested dictionaries, create a kvlistValue
                val_dict = {
                    "kvlistValue": {
                        "values": self._format_nested_attributes(value)
                    }
                }
            elif isinstance(value, list):
                # For arrays, create arrayValue
                array_values = []
                for item in value:
                    if isinstance(item, dict):
                        array_values.append({
                            "kvlistValue": {
                                "values": self._format_nested_attributes(item)
                            }
                        })
                    elif isinstance(item, str):
                        array_values.append({"stringValue": item})
                    elif isinstance(item, bool):
                        array_values.append({"boolValue": item})
                    elif isinstance(item, int):
                        array_values.append({"intValue": item})
                    elif isinstance(item, float):
                        array_values.append({"doubleValue": item})
                    else:
                        array_values.append({"stringValue": str(item)})
                val_dict = {"arrayValue": {"values": array_values}}
            elif isinstance(value, str):
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
