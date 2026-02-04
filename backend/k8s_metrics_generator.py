import secrets
import random
import uuid
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from config_schema import ScenarioConfig, Service


class K8sMetricsGenerator:
    """
    Generates Kubernetes metrics with Prometheus-convention names via OTLP.
    Emulates kube-state-metrics, cAdvisor, and node-exporter metric sources
    for compatibility with Grafana Cloud K8s Monitoring dashboards.
    """

    CPU_MODES = ['user', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal', 'nice']

    def __init__(self, config: ScenarioConfig):
        self.config = config
        self.services_map = {s.name: s for s in self.config.services}

        # Initialize K8s pod data (shared with generator.py and host_metrics_generator.py)
        self._k8s_pod_data = self._initialize_k8s_pod_data()

        # Generate and store container IDs for consistency
        self._container_ids = {
            s.name: f"containerd://{secrets.token_hex(32)}"
            for s in self.config.services
        }

        # Cluster name (consistent across all pods)
        first_svc = self.config.services[0]
        self._cluster_name = self._k8s_pod_data[first_svc.name]['cluster_name']

        # Unique node names
        self._node_names = list(set(
            self._k8s_pod_data[s.name]['node_name'] for s in self.config.services
        ))

        # Per-service counters (restarts for kube-state-metrics)
        self._k8s_counters = {
            s.name: {
                'restart_count': 0,
            } for s in self.config.services
        }

        # Node hardware specs (consistent across calls)
        self._node_specs: Dict[str, Dict[str, Any]] = {}
        for node_name in self._node_names:
            num_cpus = random.choice([4, 8, 16])
            total_memory = random.choice([8, 16, 32, 64]) * (1024 ** 3)
            self._node_specs[node_name] = {
                'num_cpus': num_cpus,
                'total_memory_bytes': total_memory,
                'fs_size_bytes': random.randint(100, 500) * (1024 ** 3),
            }

        # Per-node cAdvisor counters (lazy init)
        self._cadvisor_counters: Dict[str, Dict[str, Any]] = {}

        # Per-node node-exporter counters (lazy init)
        self._node_exporter_counters: Dict[str, Dict[str, Any]] = {}

    def _initialize_k8s_pod_data(self) -> Dict[str, Dict[str, Any]]:
        """Initialize static k8s pod data for each service with realistic cloud platform."""
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

        configured_platform = getattr(self.config, 'cloud_platform', None)
        if configured_platform and configured_platform in cloud_platforms:
            cloud_config = cloud_platforms[configured_platform]
        else:
            cloud_config = secrets.choice(list(cloud_platforms.values()))

        cluster_name = f"otel-demo-{cloud_config['cluster_suffix']}-{secrets.token_hex(3)}"

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
            node_names = [
                f"{cloud_config['node_prefix']}{i}.{cluster_name}.example.com"
                for i in range(3)
            ]
        else:
            node_names = [
                f"{cloud_config['node_prefix']}{i:02d}.{cluster_name}.local"
                for i in range(3)
            ]

        pod_data = {}
        for service in self.config.services:
            pod_name = f"{service.name}-{secrets.token_hex(4)}-{secrets.token_hex(3)}"
            node_name = secrets.choice(node_names)

            start_time_offset = random.randint(0, 7 * 24 * 3600)
            start_time = datetime.now(timezone.utc).timestamp() - start_time_offset

            node_uid = str(uuid.uuid4())

            pod_data[service.name] = {
                'pod_name': pod_name,
                'pod_uid': str(uuid.uuid4()),
                'pod_ip': f"10.{random.randint(100, 120)}.{random.randint(1, 10)}.{random.randint(2, 250)}",
                'pod_start_time': datetime.fromtimestamp(start_time, timezone.utc).isoformat().replace('+00:00', 'Z'),
                'namespace': random.choice(['default', 'production', 'staging', f'{service.name}-ns']),

                'node_name': node_name,
                'node_uid': node_uid,
                'host_ip': f"10.{random.randint(10, 50)}.{random.randint(100, 200)}",

                'cluster_name': cluster_name,
                'deployment_name': f"{service.name}-deployment",
                'replicaset_name': f"{service.name}-{secrets.token_hex(4)}",

                'cloud_provider': cloud_config['provider'],
                'cloud_platform': cloud_config['platform'],
                'cloud_region': cloud_config['region'],
                'zone': secrets.choice(cloud_config['zones']),
                'os_description': cloud_config['os_description'],
                'kubelet_version': cloud_config['kubelet_version'],
            }

        return pod_data

    def _get_any_pod_on_node(self, node_name: str) -> Dict[str, Any]:
        """Get pod data for any service running on the given node."""
        for service in self.config.services:
            pd = self._k8s_pod_data[service.name]
            if pd['node_name'] == node_name:
                return pd
        return self._k8s_pod_data[self.config.services[0].name]

    def _get_cadvisor_counters(self, node_name: str) -> Dict[str, Any]:
        """Get or initialize persistent cAdvisor counters for a node."""
        if node_name not in self._cadvisor_counters:
            self._cadvisor_counters[node_name] = {
                'services': {},  # per-service counters initialized lazily
            }
        return self._cadvisor_counters[node_name]

    def _get_node_exporter_counters(self, node_name: str) -> Dict[str, Any]:
        """Get or initialize persistent node-exporter counters for a node."""
        if node_name not in self._node_exporter_counters:
            self._node_exporter_counters[node_name] = {
                'cpu_seconds': {},  # per-cpu-per-mode, initialized lazily
                'network_rx': random.randint(1000000000, 10000000000),
                'network_tx': random.randint(1000000000, 10000000000),
            }
        return self._node_exporter_counters[node_name]

    # ── Public API used by generator.py ──────────────────────────────────

    def generate_k8s_resource_attributes(self, service: Service) -> Dict[str, Any]:
        """Generate k8s-specific resource attributes for app telemetry (traces/metrics/logs).

        Used by generator.py for application-level telemetry, NOT for K8s
        infrastructure metrics (which use Prometheus-convention names).
        """
        pod_data = self._k8s_pod_data[service.name]
        container_id = self._container_ids[service.name]
        language_value = (service.language or "python").lower()

        return {
            "host.name": pod_data['node_name'],
            "host.id": str(random.randint(6000000000000000000, 7000000000000000000)),
            "host.ip": pod_data['host_ip'],
            "host.architecture": "amd64",
            "os.type": "linux",
            "os.description": pod_data['os_description'],
            "cloud.provider": pod_data['cloud_provider'],
            "cloud.platform": pod_data['cloud_platform'],
            "cloud.region": pod_data['cloud_region'],
            "cloud.availability_zone": pod_data['zone'],
            "cloud.account.id": f"otel-demo-{pod_data['cloud_provider']}-account",
            "cloud.instance.id": str(random.randint(6000000000000000000, 7000000000000000000)),
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.language": language_value,
            "telemetry.sdk.version": "1.24.0",
            "service.name": service.name,
            "service.version": "1.2.3",
            "service.namespace": pod_data['namespace'],
            "service.instance.id": f"{service.name}-{pod_data['pod_name']}",
            "deployment.environment": "production",
            "container.name": f"{service.name}-container",
            "container.id": container_id,
            "container.image.name": f"{service.name}:latest",
            "container.image.tag": "latest",
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
            "k8s.pod.label.app": service.name,
            "k8s.pod.label.version": "v1.2.3",
            "k8s.pod.label.component": service.role if hasattr(service, 'role') else "backend",
            "k8s.pod.label.managed-by": "helm",
            "k8s.pod.label.part-of": "otel-demo-app",
        }

    def generate_k8s_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics with Prometheus-convention names.

        Creates three metric sources as separate OTLP resources:
        1. kube-state-metrics (service.name → job label)
        2. cAdvisor per node (service.name → job label)
        3. node-exporter per node (service.name → job label)
        """
        resource_metrics = []
        current_time_ns = str(time.time_ns())

        # 1. kube-state-metrics — cluster-wide info/status metrics
        ksm_metrics = self._generate_ksm_metrics(current_time_ns)
        resource_metrics.append({
            "resource": {
                "attributes": self._format_attributes({
                    "service.name": "integrations/kubernetes/kube-state-metrics",
                    "service.instance.id": "kube-state-metrics:8080",
                })
            },
            "scopeMetrics": [{
                "scope": {"name": "kube-state-metrics", "version": "2.13.0"},
                "metrics": ksm_metrics,
            }]
        })

        # 2. cAdvisor — one resource per node with container metrics
        for node_name in self._node_names:
            pod_data = self._get_any_pod_on_node(node_name)
            cadvisor_metrics = self._generate_cadvisor_metrics(current_time_ns, node_name)
            resource_metrics.append({
                "resource": {
                    "attributes": self._format_attributes({
                        "service.name": "integrations/kubernetes/cadvisor",
                        "service.instance.id": f"{pod_data['host_ip']}:10250",
                    })
                },
                "scopeMetrics": [{
                    "scope": {"name": "cadvisor"},
                    "metrics": cadvisor_metrics,
                }]
            })

        # 3. node-exporter — one resource per node with host metrics
        for node_name in self._node_names:
            pod_data = self._get_any_pod_on_node(node_name)
            ne_metrics = self._generate_node_exporter_metrics(current_time_ns, node_name)
            resource_metrics.append({
                "resource": {
                    "attributes": self._format_attributes({
                        "service.name": "integrations/kubernetes/node-exporter",
                        "service.instance.id": f"{pod_data['host_ip']}:9100",
                    })
                },
                "scopeMetrics": [{
                    "scope": {"name": "node-exporter"},
                    "metrics": ne_metrics,
                }]
            })

        return {"resourceMetrics": resource_metrics}

    # ── kube-state-metrics ───────────────────────────────────────────────

    def _generate_ksm_metrics(self, ts: str) -> List[Dict[str, Any]]:
        """Generate kube-state-metrics style metrics (kube_* prefix)."""
        metrics: List[Dict[str, Any]] = []

        # ── Node metrics ──
        metrics.append(self._ksm_node_info(ts))
        metrics.append(self._ksm_node_status_condition(ts))
        metrics.extend(self._ksm_node_capacity_allocatable(ts))

        # ── Pod metrics ──
        metrics.append(self._ksm_pod_info(ts))
        metrics.append(self._ksm_pod_status_phase(ts))
        metrics.append(self._ksm_pod_container_info(ts))
        metrics.extend(self._ksm_pod_container_resources(ts))
        metrics.append(self._ksm_pod_container_status_restarts(ts))

        # ── Deployment metrics ──
        metrics.extend(self._ksm_deployment_metrics(ts))

        # ── Namespace metrics ──
        metrics.append(self._ksm_namespace_status_phase(ts))

        return metrics

    def _ksm_node_info(self, ts: str) -> Dict[str, Any]:
        dps = []
        for node_name in self._node_names:
            pd = self._get_any_pod_on_node(node_name)
            dps.append({
                "timeUnixNano": ts, "asDouble": 1.0,
                "attributes": self._format_attributes({
                    "cluster": self._cluster_name,
                    "node": node_name,
                    "kernel_version": "5.15.0-1051-aws",
                    "os_image": pd['os_description'],
                    "container_runtime_version": "containerd://1.7.11",
                    "kubelet_version": pd['kubelet_version'],
                    "internal_ip": pd['host_ip'],
                })
            })
        return self._create_gauge_metric("kube_node_info", "", dps)

    def _ksm_node_status_condition(self, ts: str) -> Dict[str, Any]:
        conditions = [
            ("Ready", 0.95), ("MemoryPressure", 0.05),
            ("DiskPressure", 0.03), ("PIDPressure", 0.02),
            ("NetworkUnavailable", 0.01),
        ]
        dps = []
        for node_name in self._node_names:
            for condition, prob_true in conditions:
                is_true = random.random() < prob_true if condition != "Ready" else random.random() < 0.95
                for status_val in ["true", "false", "unknown"]:
                    if status_val == "true":
                        val = 1.0 if is_true else 0.0
                    elif status_val == "false":
                        val = 0.0 if is_true else 1.0
                    else:
                        val = 0.0
                    dps.append({
                        "timeUnixNano": ts, "asDouble": val,
                        "attributes": self._format_attributes({
                            "cluster": self._cluster_name,
                            "node": node_name,
                            "condition": condition,
                            "status": status_val,
                        })
                    })
        return self._create_gauge_metric("kube_node_status_condition", "", dps)

    def _ksm_node_capacity_allocatable(self, ts: str) -> List[Dict[str, Any]]:
        cap_dps, alloc_dps = [], []
        for node_name in self._node_names:
            specs = self._node_specs[node_name]
            resources = [
                ("cpu", float(specs['num_cpus']), float(specs['num_cpus']) - 0.5, "core"),
                ("memory", float(specs['total_memory_bytes']),
                 float(specs['total_memory_bytes']) - 500 * 1024 * 1024, "byte"),
                ("pods", 110.0, 110.0, "integer"),
            ]
            for resource, cap_val, alloc_val, unit in resources:
                attrs = {"cluster": self._cluster_name, "node": node_name,
                         "resource": resource, "unit": unit}
                cap_dps.append({
                    "timeUnixNano": ts, "asDouble": cap_val,
                    "attributes": self._format_attributes(attrs),
                })
                alloc_dps.append({
                    "timeUnixNano": ts, "asDouble": alloc_val,
                    "attributes": self._format_attributes(attrs),
                })
        return [
            self._create_gauge_metric("kube_node_status_capacity", "", cap_dps),
            self._create_gauge_metric("kube_node_status_allocatable", "", alloc_dps),
        ]

    def _ksm_pod_info(self, ts: str) -> Dict[str, Any]:
        dps = []
        for svc in self.config.services:
            pd = self._k8s_pod_data[svc.name]
            dps.append({
                "timeUnixNano": ts, "asDouble": 1.0,
                "attributes": self._format_attributes({
                    "cluster": self._cluster_name,
                    "namespace": pd['namespace'],
                    "pod": pd['pod_name'],
                    "uid": pd['pod_uid'],
                    "node": pd['node_name'],
                    "host_ip": pd['host_ip'],
                    "pod_ip": pd['pod_ip'],
                    "created_by_kind": "ReplicaSet",
                    "created_by_name": pd['replicaset_name'],
                })
            })
        return self._create_gauge_metric("kube_pod_info", "", dps)

    def _ksm_pod_status_phase(self, ts: str) -> Dict[str, Any]:
        dps = []
        for svc in self.config.services:
            pd = self._k8s_pod_data[svc.name]
            for phase in ["Pending", "Running", "Succeeded", "Failed", "Unknown"]:
                dps.append({
                    "timeUnixNano": ts,
                    "asDouble": 1.0 if phase == "Running" else 0.0,
                    "attributes": self._format_attributes({
                        "cluster": self._cluster_name,
                        "namespace": pd['namespace'],
                        "pod": pd['pod_name'],
                        "uid": pd['pod_uid'],
                        "phase": phase,
                    })
                })
        return self._create_gauge_metric("kube_pod_status_phase", "", dps)

    def _ksm_pod_container_info(self, ts: str) -> Dict[str, Any]:
        dps = []
        for svc in self.config.services:
            pd = self._k8s_pod_data[svc.name]
            dps.append({
                "timeUnixNano": ts, "asDouble": 1.0,
                "attributes": self._format_attributes({
                    "cluster": self._cluster_name,
                    "namespace": pd['namespace'],
                    "pod": pd['pod_name'],
                    "uid": pd['pod_uid'],
                    "container": svc.name,
                    "container_id": self._container_ids[svc.name],
                    "image": f"{svc.name}:latest",
                    "image_spec": f"docker.io/library/{svc.name}:latest",
                })
            })
        return self._create_gauge_metric("kube_pod_container_info", "", dps)

    def _ksm_pod_container_resources(self, ts: str) -> List[Dict[str, Any]]:
        req_dps, lim_dps = [], []
        for svc in self.config.services:
            pd = self._k8s_pod_data[svc.name]
            base = {
                "cluster": self._cluster_name,
                "namespace": pd['namespace'],
                "pod": pd['pod_name'],
                "uid": pd['pod_uid'],
                "container": svc.name,
            }
            for resource, req_val, lim_val, unit in [
                ("cpu", random.uniform(0.1, 1.0), random.uniform(0.5, 2.0), "core"),
                ("memory", float(random.randint(128, 512) * 2 ** 20),
                 float(random.randint(256, 1024) * 2 ** 20), "byte"),
            ]:
                req_dps.append({
                    "timeUnixNano": ts, "asDouble": req_val,
                    "attributes": self._format_attributes({
                        **base, "resource": resource, "unit": unit,
                    }),
                })
                lim_dps.append({
                    "timeUnixNano": ts, "asDouble": lim_val,
                    "attributes": self._format_attributes({
                        **base, "resource": resource, "unit": unit,
                    }),
                })
        return [
            self._create_gauge_metric("kube_pod_container_resource_requests", "", req_dps),
            self._create_gauge_metric("kube_pod_container_resource_limits", "", lim_dps),
        ]

    def _ksm_pod_container_status_restarts(self, ts: str) -> Dict[str, Any]:
        dps = []
        for svc in self.config.services:
            pd = self._k8s_pod_data[svc.name]
            if random.random() < 0.002:
                self._k8s_counters[svc.name]['restart_count'] += 1
            dps.append({
                "timeUnixNano": ts,
                "asDouble": float(self._k8s_counters[svc.name]['restart_count']),
                "attributes": self._format_attributes({
                    "cluster": self._cluster_name,
                    "namespace": pd['namespace'],
                    "pod": pd['pod_name'],
                    "uid": pd['pod_uid'],
                    "container": svc.name,
                })
            })
        # Monotonic sum → Mimir adds _total suffix → kube_pod_container_status_restarts_total
        return self._create_sum_metric("kube_pod_container_status_restarts", "", True, dps)

    def _ksm_deployment_metrics(self, ts: str) -> List[Dict[str, Any]]:
        spec_dps, avail_dps = [], []
        for svc in self.config.services:
            pd = self._k8s_pod_data[svc.name]
            desired = random.randint(1, 5)
            available = desired if random.random() < 0.9 else max(0, desired - 1)
            attrs = {
                "cluster": self._cluster_name,
                "namespace": pd['namespace'],
                "deployment": pd['deployment_name'],
            }
            spec_dps.append({
                "timeUnixNano": ts, "asDouble": float(desired),
                "attributes": self._format_attributes(attrs),
            })
            avail_dps.append({
                "timeUnixNano": ts, "asDouble": float(available),
                "attributes": self._format_attributes(attrs),
            })
        return [
            self._create_gauge_metric("kube_deployment_spec_replicas", "", spec_dps),
            self._create_gauge_metric("kube_deployment_status_replicas_available", "", avail_dps),
        ]

    def _ksm_namespace_status_phase(self, ts: str) -> Dict[str, Any]:
        namespaces = list(set(
            self._k8s_pod_data[s.name]['namespace'] for s in self.config.services
        ))
        dps = []
        for ns in namespaces:
            for phase in ["Active", "Terminating"]:
                dps.append({
                    "timeUnixNano": ts,
                    "asDouble": 1.0 if phase == "Active" else 0.0,
                    "attributes": self._format_attributes({
                        "cluster": self._cluster_name,
                        "namespace": ns,
                        "phase": phase,
                    })
                })
        return self._create_gauge_metric("kube_namespace_status_phase", "", dps)

    # ── cAdvisor ─────────────────────────────────────────────────────────

    def _generate_cadvisor_metrics(self, ts: str, node_name: str) -> List[Dict[str, Any]]:
        """Generate cAdvisor-style metrics (container_* and machine_* prefix)."""
        metrics: List[Dict[str, Any]] = []
        counters = self._get_cadvisor_counters(node_name)
        specs = self._node_specs[node_name]

        services_on_node = [
            s for s in self.config.services
            if self._k8s_pod_data[s.name]['node_name'] == node_name
        ]

        cpu_dps, mem_ws_dps, mem_rss_dps, mem_usage_dps = [], [], [], []
        net_rx_dps, net_tx_dps = [], []
        fs_usage_dps, fs_limit_dps = [], []

        for svc in services_on_node:
            pd = self._k8s_pod_data[svc.name]

            # Lazy init per-service counters
            svc_c = counters['services'].setdefault(svc.name, {
                'cpu_seconds': random.uniform(100.0, 5000.0),
                'network_rx': random.randint(50000000, 500000000),
                'network_tx': random.randint(50000000, 500000000),
            })

            # Increment monotonic counters
            svc_c['cpu_seconds'] += random.uniform(0.05, 0.5)
            svc_c['network_rx'] += random.randint(10000, 500000)
            svc_c['network_tx'] += random.randint(10000, 500000)

            base = {
                "cluster": self._cluster_name,
                "namespace": pd['namespace'],
                "pod": pd['pod_name'],
                "container": svc.name,
                "node": node_name,
            }

            # CPU usage (counter)
            cpu_dps.append({
                "timeUnixNano": ts,
                "asDouble": svc_c['cpu_seconds'],
                "attributes": self._format_attributes(base),
            })

            # Memory gauges
            mem_usage = random.randint(100 * 2 ** 20, 800 * 2 ** 20)
            mem_ws = int(mem_usage * random.uniform(0.6, 0.9))
            mem_rss = int(mem_usage * random.uniform(0.5, 0.85))

            mem_usage_dps.append({
                "timeUnixNano": ts, "asDouble": float(mem_usage),
                "attributes": self._format_attributes(base),
            })
            mem_ws_dps.append({
                "timeUnixNano": ts, "asDouble": float(mem_ws),
                "attributes": self._format_attributes(base),
            })
            mem_rss_dps.append({
                "timeUnixNano": ts, "asDouble": float(mem_rss),
                "attributes": self._format_attributes(base),
            })

            # Network (per pod, no container dimension)
            net_base = {
                "cluster": self._cluster_name,
                "namespace": pd['namespace'],
                "pod": pd['pod_name'],
                "node": node_name,
                "interface": "eth0",
            }
            net_rx_dps.append({
                "timeUnixNano": ts, "asDouble": float(svc_c['network_rx']),
                "attributes": self._format_attributes(net_base),
            })
            net_tx_dps.append({
                "timeUnixNano": ts, "asDouble": float(svc_c['network_tx']),
                "attributes": self._format_attributes(net_base),
            })

            # Filesystem
            fs_base = {
                "cluster": self._cluster_name,
                "namespace": pd['namespace'],
                "pod": pd['pod_name'],
                "container": svc.name,
                "node": node_name,
                "device": "/dev/sda1",
            }
            fs_lim = random.randint(5 * 2 ** 30, 50 * 2 ** 30)
            fs_use = random.randint(int(fs_lim * 0.1), int(fs_lim * 0.7))
            fs_usage_dps.append({
                "timeUnixNano": ts, "asDouble": float(fs_use),
                "attributes": self._format_attributes(fs_base),
            })
            fs_limit_dps.append({
                "timeUnixNano": ts, "asDouble": float(fs_lim),
                "attributes": self._format_attributes(fs_base),
            })

        # Container CPU (counter → container_cpu_usage_seconds_total after Mimir)
        if cpu_dps:
            metrics.append(self._create_sum_metric(
                "container_cpu_usage_seconds", "", True, cpu_dps))

        # Container memory gauges
        if mem_usage_dps:
            metrics.append(self._create_gauge_metric(
                "container_memory_usage_bytes", "", mem_usage_dps))
        if mem_ws_dps:
            metrics.append(self._create_gauge_metric(
                "container_memory_working_set_bytes", "", mem_ws_dps))
        if mem_rss_dps:
            metrics.append(self._create_gauge_metric(
                "container_memory_rss", "", mem_rss_dps))

        # Container network (counters)
        if net_rx_dps:
            metrics.append(self._create_sum_metric(
                "container_network_receive_bytes", "", True, net_rx_dps))
        if net_tx_dps:
            metrics.append(self._create_sum_metric(
                "container_network_transmit_bytes", "", True, net_tx_dps))

        # Container filesystem
        if fs_usage_dps:
            metrics.append(self._create_gauge_metric(
                "container_fs_usage_bytes", "", fs_usage_dps))
        if fs_limit_dps:
            metrics.append(self._create_gauge_metric(
                "container_fs_limit_bytes", "", fs_limit_dps))

        # Machine-level metrics
        machine_attrs = self._format_attributes({
            "cluster": self._cluster_name,
            "node": node_name,
        })
        metrics.append(self._create_gauge_metric("machine_cpu_cores", "", [{
            "timeUnixNano": ts,
            "asDouble": float(specs['num_cpus']),
            "attributes": machine_attrs,
        }]))
        metrics.append(self._create_gauge_metric("machine_memory_bytes", "", [{
            "timeUnixNano": ts,
            "asDouble": float(specs['total_memory_bytes']),
            "attributes": machine_attrs,
        }]))

        return metrics

    # ── node-exporter ────────────────────────────────────────────────────

    def _generate_node_exporter_metrics(self, ts: str, node_name: str) -> List[Dict[str, Any]]:
        """Generate node-exporter-style metrics (node_* prefix)."""
        metrics: List[Dict[str, Any]] = []
        counters = self._get_node_exporter_counters(node_name)
        specs = self._node_specs[node_name]

        # ── node_cpu_seconds (counter → node_cpu_seconds_total) ──
        cpu_dps = []
        for cpu_idx in range(specs['num_cpus']):
            cpu_key = f"cpu{cpu_idx}"
            if cpu_key not in counters['cpu_seconds']:
                counters['cpu_seconds'][cpu_key] = {
                    'user': random.uniform(1000.0, 50000.0),
                    'system': random.uniform(500.0, 20000.0),
                    'idle': random.uniform(50000.0, 200000.0),
                    'iowait': random.uniform(10.0, 1000.0),
                    'irq': random.uniform(1.0, 100.0),
                    'softirq': random.uniform(5.0, 500.0),
                    'steal': random.uniform(0.0, 50.0),
                    'nice': random.uniform(0.0, 100.0),
                }

            cpu_data = counters['cpu_seconds'][cpu_key]
            cpu_data['user'] += random.uniform(0.1, 2.0)
            cpu_data['system'] += random.uniform(0.05, 1.0)
            cpu_data['idle'] += random.uniform(5.0, 9.0)
            cpu_data['iowait'] += random.uniform(0.0, 0.3)
            cpu_data['irq'] += random.uniform(0.0, 0.05)
            cpu_data['softirq'] += random.uniform(0.0, 0.1)
            cpu_data['steal'] += random.uniform(0.0, 0.02)
            cpu_data['nice'] += random.uniform(0.0, 0.05)

            for mode, val in cpu_data.items():
                cpu_dps.append({
                    "timeUnixNano": ts, "asDouble": val,
                    "attributes": self._format_attributes({
                        "cluster": self._cluster_name,
                        "cpu": str(cpu_idx),
                        "mode": mode,
                    })
                })

        metrics.append(self._create_sum_metric("node_cpu_seconds", "", True, cpu_dps))

        # ── Node memory gauges ──
        mem_total = specs['total_memory_bytes']
        mem_used = random.randint(int(mem_total * 0.3), int(mem_total * 0.8))
        mem_free = mem_total - mem_used
        mem_available = min(mem_free + random.randint(0, int(mem_total * 0.1)), mem_total)

        cluster_attrs = self._format_attributes({"cluster": self._cluster_name})
        for name, val in [
            ("node_memory_MemTotal_bytes", mem_total),
            ("node_memory_MemAvailable_bytes", mem_available),
            ("node_memory_MemFree_bytes", mem_free),
            ("node_memory_Buffers_bytes", random.randint(50 * 2 ** 20, 500 * 2 ** 20)),
            ("node_memory_Cached_bytes", random.randint(500 * 2 ** 20, 4 * 2 ** 30)),
        ]:
            metrics.append(self._create_gauge_metric(name, "", [{
                "timeUnixNano": ts, "asDouble": float(val),
                "attributes": cluster_attrs,
            }]))

        # ── Node filesystem gauges ──
        fs_size = specs['fs_size_bytes']
        fs_used = random.randint(int(fs_size * 0.2), int(fs_size * 0.7))
        fs_avail = fs_size - fs_used

        fs_attrs = self._format_attributes({
            "cluster": self._cluster_name,
            "mountpoint": "/",
            "fstype": "ext4",
            "device": "/dev/sda1",
        })
        metrics.append(self._create_gauge_metric("node_filesystem_size_bytes", "", [{
            "timeUnixNano": ts, "asDouble": float(fs_size), "attributes": fs_attrs,
        }]))
        metrics.append(self._create_gauge_metric("node_filesystem_avail_bytes", "", [{
            "timeUnixNano": ts, "asDouble": float(fs_avail), "attributes": fs_attrs,
        }]))

        # ── Node network (counters) ──
        counters['network_rx'] += random.randint(100000, 5000000)
        counters['network_tx'] += random.randint(100000, 5000000)

        net_attrs = self._format_attributes({
            "cluster": self._cluster_name,
            "device": "eth0",
        })
        metrics.append(self._create_sum_metric(
            "node_network_receive_bytes", "", True, [{
                "timeUnixNano": ts, "asDouble": float(counters['network_rx']),
                "attributes": net_attrs,
            }]))
        metrics.append(self._create_sum_metric(
            "node_network_transmit_bytes", "", True, [{
                "timeUnixNano": ts, "asDouble": float(counters['network_tx']),
                "attributes": net_attrs,
            }]))

        # ── node_uname_info ──
        pd = self._get_any_pod_on_node(node_name)
        metrics.append(self._create_gauge_metric("node_uname_info", "", [{
            "timeUnixNano": ts, "asDouble": 1.0,
            "attributes": self._format_attributes({
                "cluster": self._cluster_name,
                "sysname": "Linux",
                "release": "5.15.0-1051-aws",
                "version": "#56-Ubuntu SMP",
                "machine": "x86_64",
                "nodename": node_name,
            }),
        }]))

        return metrics

    # ── K8s Event Logs ───────────────────────────────────────────────────

    def generate_k8s_logs_payload(self) -> Dict[str, List[Any]]:
        resource_logs = []
        current_time_ns = str(time.time_ns())

        event_scenarios = [
            {"type": "Warning", "reason": "FailedScheduling",
             "message": "0/3 nodes are available: 3 Insufficient memory.",
             "object_kind": "Pod", "weight": 0.1},
            {"type": "Warning", "reason": "Unhealthy",
             "message": "Readiness probe failed: HTTP probe failed with statuscode: 503",
             "object_kind": "Pod", "weight": 0.15},
            {"type": "Warning", "reason": "Failed",
             "message": "Error: container failed to start",
             "object_kind": "Pod", "weight": 0.08},
            {"type": "Normal", "reason": "Scheduled",
             "message": "Successfully assigned {namespace}/{pod_name} to {node_name}",
             "object_kind": "Pod", "weight": 0.2},
            {"type": "Normal", "reason": "Pulled",
             "message": "Successfully pulled image \"{service_name}:latest\"",
             "object_kind": "Pod", "weight": 0.15},
            {"type": "Normal", "reason": "Created",
             "message": "Created container {service_name}",
             "object_kind": "Pod", "weight": 0.1},
            {"type": "Normal", "reason": "Started",
             "message": "Started container {service_name}",
             "object_kind": "Pod", "weight": 0.1},
            {"type": "Warning", "reason": "BackOff",
             "message": "Back-off restarting failed container",
             "object_kind": "Pod", "weight": 0.05},
            {"type": "Warning", "reason": "FailedMount",
             "message": "MountVolume.SetUp failed for volume \"pvc-123\" : mount failed: exit status 32",
             "object_kind": "Pod", "weight": 0.03},
            {"type": "Normal", "reason": "SuccessfulCreate",
             "message": "Created pod: {pod_name}",
             "object_kind": "ReplicaSet", "weight": 0.07},
            {"type": "Normal", "reason": "ScalingReplicaSet",
             "message": "Scaled up replica set {service_name}-{namespace} to 3",
             "object_kind": "Deployment", "weight": 0.05},
        ]

        for service in self.config.services:
            pod_data = self._k8s_pod_data[service.name]

            num_events = random.choices([0, 1, 2], weights=[0.5, 0.3, 0.2])[0]
            if num_events == 0:
                continue

            selected_events = random.choices(
                event_scenarios,
                weights=[e["weight"] for e in event_scenarios],
                k=num_events,
            )

            log_records = []
            for event in selected_events:
                message = event["message"].format(
                    service_name=service.name,
                    pod_name=pod_data['pod_name'],
                    node_name=pod_data['node_name'],
                    namespace=pod_data['namespace'],
                )

                event_time_ns = str(int(current_time_ns) - random.randint(0, 3600000000000))
                event_name = f"{pod_data['pod_name']}.{secrets.token_hex(8)}"

                log_body = f"{event['reason']}: {message}"

                log_records.append({
                    "timeUnixNano": event_time_ns,
                    "severityText": "INFO" if event["type"] == "Normal" else "WARN",
                    "severityNumber": 9 if event["type"] == "Normal" else 13,
                    "body": {"stringValue": log_body},
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
                    ],
                })

            if log_records:
                event_resource_attrs = self._format_attributes({
                    "k8s.cluster.name": pod_data['cluster_name'],
                    "cluster": pod_data['cluster_name'],
                    "k8s.namespace.name": pod_data['namespace'],
                    "k8s.pod.name": pod_data['pod_name'],
                    "k8s.node.name": pod_data['node_name'],
                    "service.name": service.name,
                    "deployment.environment": "production",
                    "cloud.provider": pod_data['cloud_provider'],
                    "cloud.platform": pod_data['cloud_platform'],
                    "cloud.region": pod_data['cloud_region'],
                })

                resource_logs.append({
                    "resource": {
                        "attributes": event_resource_attrs,
                    },
                    "scopeLogs": [{
                        "scope": {
                            "name": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/k8sobjectsreceiver",
                            "version": "8.16.0",
                        },
                        "logRecords": log_records,
                    }]
                })

        return {"resourceLogs": resource_logs}

    # ── Helpers ──────────────────────────────────────────────────────────

    def _create_gauge_metric(self, name: str, unit: str, data_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"name": name, "unit": unit, "gauge": {"dataPoints": data_points}}

    def _create_sum_metric(self, name: str, unit: str, is_monotonic: bool, data_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "name": name, "unit": unit,
            "sum": {
                "isMonotonic": is_monotonic,
                "aggregationTemporality": 2,
                "dataPoints": data_points,
            },
        }

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
