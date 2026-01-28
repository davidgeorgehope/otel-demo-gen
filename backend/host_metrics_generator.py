"""
Host metrics generator that produces metrics compatible with Elastic's Infrastructure UI.
Mimics the output format of OTel Collector's hostmetricsreceiver.
"""
import secrets
import random
import time
import uuid
from typing import Dict, List, Any, Optional

from config_schema import ScenarioConfig


class HostMetricsGenerator:
    """
    Generates host-level metrics in the exact format that Elastic's Infrastructure UI expects.
    This mimics the OTel Collector's hostmetricsreceiver output.
    """

    SCHEMA_URL = "https://opentelemetry.io/schemas/1.9.0"
    SCRAPER_VERSION = "9.0.0"

    # Scraper scope names - must match exactly what hostmetricsreceiver produces
    SCRAPERS = {
        "load": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/hostmetricsreceiver/internal/scraper/loadscraper",
        "cpu": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/hostmetricsreceiver/internal/scraper/cpuscraper",
        "memory": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/hostmetricsreceiver/internal/scraper/memoryscraper",
        "disk": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/hostmetricsreceiver/internal/scraper/diskscraper",
        "filesystem": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/hostmetricsreceiver/internal/scraper/filesystemscraper",
        "network": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/hostmetricsreceiver/internal/scraper/networkscraper",
        "processes": "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/hostmetricsreceiver/internal/scraper/processesscraper",
    }

    # Cloud/platform configurations
    CLOUD_CONFIGS = {
        "aws_eks": {
            "provider": "aws",
            "platform": "aws_eks",
            "instance_types": ["m5.xlarge", "m5.2xlarge", "m5.4xlarge", "c5.2xlarge", "r5.xlarge"],
            "cpu_model": "Intel(R) Xeon(R) Platinum 8175M CPU @ 2.50GHz",
            "os_description": "Amazon Linux 2",
        },
        "azure_aks": {
            "provider": "azure",
            "platform": "azure_aks",
            "instance_types": ["Standard_D4s_v3", "Standard_D8s_v3", "Standard_E4s_v3"],
            "cpu_model": "Intel(R) Xeon(R) Platinum 8272CL CPU @ 2.60GHz",
            "os_description": "Ubuntu 22.04.5 LTS",
        },
        "gcp_gke": {
            "provider": "gcp",
            "platform": "gcp_gke",
            "instance_types": ["n2-standard-4", "n2-standard-8", "e2-standard-4"],
            "cpu_model": "Intel(R) Xeon(R) CPU @ 2.20GHz",
            "os_description": "Container-Optimized OS from Google",
        },
        "openshift": {
            "provider": "openshift",
            "platform": "openshift",
            "instance_types": ["bare-metal", "vsphere-vm", "kvm-vm"],
            "cpu_model": "Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz",
            "os_description": "Red Hat Enterprise Linux CoreOS 415.92",
        },
        "on_prem": {
            "provider": "on_prem",
            "platform": "kubernetes",
            "instance_types": ["bare-metal", "vsphere-vm", "kvm-vm"],
            "cpu_model": "Intel(R) Xeon(R) E5-2680 v4 @ 2.40GHz",
            "os_description": "Ubuntu 22.04.4 LTS",
        },
    }

    def __init__(self, config: ScenarioConfig, k8s_node_data: Optional[Dict[str, Dict[str, Any]]] = None):
        self.config = config

        # Use provided k8s node data or initialize our own
        if k8s_node_data:
            self._hosts = self._initialize_from_k8s_data(k8s_node_data)
        else:
            self._hosts = self._initialize_hosts()

        # Initialize counters for cumulative metrics
        self._counters = self._initialize_counters()

        # Track start time for consistent start_timestamp
        self._start_timestamp = time.time_ns()

    def _initialize_from_k8s_data(self, k8s_node_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Initialize hosts from K8s node data."""
        hosts = {}

        # Extract unique nodes from k8s data
        seen_nodes = set()
        for service_name, pod_data in k8s_node_data.items():
            node_name = pod_data.get('node_name')
            if node_name and node_name not in seen_nodes:
                seen_nodes.add(node_name)

                # Determine cloud platform from pod data
                cloud_platform = pod_data.get('cloud_platform', 'aws_eks')
                cloud_config = self.CLOUD_CONFIGS.get(cloud_platform, self.CLOUD_CONFIGS['aws_eks'])

                hosts[node_name] = self._create_host_data(
                    node_name=node_name,
                    cloud_config=cloud_config,
                    cloud_provider=pod_data.get('cloud_provider', 'aws'),
                    cloud_region=pod_data.get('cloud_region', 'us-east-1'),
                    cloud_zone=pod_data.get('zone', 'us-east-1a'),
                    cluster_name=pod_data.get('cluster_name', 'demo-cluster'),
                    os_description=pod_data.get('os_description'),
                )

        return hosts

    def _initialize_hosts(self) -> Dict[str, Dict[str, Any]]:
        """Initialize hosts from config if no k8s data provided."""
        hosts = {}

        # Determine cloud platform from config or choose randomly
        cloud_platform = "azure_aks"  # Default to AKS for the user's use case
        cloud_config = self.CLOUD_CONFIGS[cloud_platform]

        # Generate 2-3 nodes
        num_nodes = random.randint(2, 3)
        for i in range(num_nodes):
            node_name = f"aks-agentpool-{secrets.token_hex(4)}-vmss000000{i}"
            hosts[node_name] = self._create_host_data(
                node_name=node_name,
                cloud_config=cloud_config,
                cloud_provider="azure",
                cloud_region="eastus",
                cloud_zone=f"eastus-{i + 1}",
                cluster_name=f"otel-demo-aks-cluster-{secrets.token_hex(3)}",
            )

        return hosts

    def _create_host_data(
        self,
        node_name: str,
        cloud_config: Dict[str, Any],
        cloud_provider: str,
        cloud_region: str,
        cloud_zone: str,
        cluster_name: str,
        os_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create host data structure for a node."""
        instance_id = f"i-{secrets.token_hex(8)}" if cloud_provider == "aws" else str(uuid.uuid4())

        # Generate multiple IPs like real hosts have
        base_ip = f"10.{random.randint(0, 255)}.{random.randint(0, 255)}"
        ips = [
            f"{base_ip}.{random.randint(1, 254)}",
            f"{base_ip}.{random.randint(1, 254)}",
        ]
        # Add some IPv6 link-local addresses
        for _ in range(3):
            ips.append(f"fe80::{secrets.token_hex(2)}:{secrets.token_hex(2)}ff:fe{secrets.token_hex(2)}:{secrets.token_hex(2)}")

        # Generate MAC addresses
        macs = [
            "-".join([secrets.token_hex(1).upper() for _ in range(6)])
            for _ in range(3)
        ]

        return {
            "host_name": node_name,
            "host_id": instance_id,
            "host_arch": "amd64",
            "host_type": random.choice(cloud_config["instance_types"]),
            "host_ips": ips,
            "host_macs": macs,
            "host_cpu_model": cloud_config["cpu_model"],
            "host_cpu_vendor": "GenuineIntel",
            "host_cpu_family": "6",
            "host_cpu_model_id": str(random.randint(80, 100)),
            "host_cpu_stepping": str(random.randint(1, 10)),
            "host_cpu_cache_l2_size": random.choice([32768, 33792, 65536]),
            "host_image_id": f"ami-{secrets.token_hex(8)}" if cloud_provider == "aws" else f"image-{secrets.token_hex(8)}",
            "os_type": "linux",
            "os_description": os_description or f"{cloud_config['os_description']} (Linux {node_name} 5.10.{random.randint(100, 250)}-{random.randint(100, 300)}.amzn2.x86_64 #1 SMP x86_64)",
            "cloud_provider": cloud_provider,
            "cloud_platform": cloud_config["platform"],
            "cloud_region": cloud_region,
            "cloud_zone": cloud_zone,
            "cloud_account_id": f"{random.randint(100000000000, 999999999999)}",
            "cloud_instance_id": instance_id,
            "k8s_cluster_name": cluster_name,
            # Resource limits (8 vCPUs, 32GB typical for m5.2xlarge)
            "cpu_count": random.choice([4, 8, 16]),
            "memory_total_bytes": random.choice([16, 32, 64]) * 1024 * 1024 * 1024,
            "disk_total_bytes": random.choice([100, 200, 500]) * 1024 * 1024 * 1024,
            # Network devices
            "network_devices": ["eth0", "eth1"],
            # Disk devices
            "disk_devices": ["nvme0n1", "nvme0n1p1", "nvme0n1p128"],
            # Filesystem mounts
            "filesystems": [
                {"device": "/dev/nvme0n1p1", "mountpoint": "/", "type": "xfs"},
                {"device": "/dev/nvme0n1p128", "mountpoint": "/boot/efi", "type": "vfat"},
            ],
        }

    def _initialize_counters(self) -> Dict[str, Dict[str, Any]]:
        """Initialize cumulative counters for each host."""
        counters = {}
        for host_name in self._hosts:
            counters[host_name] = {
                "cpu_time_user": random.randint(10_000_000_000_000, 100_000_000_000_000),
                "cpu_time_system": random.randint(1_000_000_000_000, 10_000_000_000_000),
                "cpu_time_idle": random.randint(100_000_000_000_000, 500_000_000_000_000),
                "cpu_time_iowait": random.randint(100_000_000_000, 1_000_000_000_000),
                "disk_read_bytes": {},
                "disk_write_bytes": {},
                "disk_read_ops": {},
                "disk_write_ops": {},
                "network_rx_bytes": {},
                "network_tx_bytes": {},
            }
            # Initialize per-device counters
            host_data = self._hosts[host_name]
            for device in host_data.get("disk_devices", []):
                counters[host_name]["disk_read_bytes"][device] = random.randint(1_000_000_000, 100_000_000_000)
                counters[host_name]["disk_write_bytes"][device] = random.randint(1_000_000_000, 100_000_000_000)
                counters[host_name]["disk_read_ops"][device] = random.randint(1_000_000, 50_000_000)
                counters[host_name]["disk_write_ops"][device] = random.randint(1_000_000, 50_000_000)
            for device in host_data.get("network_devices", []):
                counters[host_name]["network_rx_bytes"][device] = random.randint(10_000_000_000, 1_000_000_000_000)
                counters[host_name]["network_tx_bytes"][device] = random.randint(10_000_000_000, 1_000_000_000_000)
        return counters

    def _format_resource_attributes(self, host_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format resource attributes in OTLP format."""
        attrs = [
            {"key": "host.name", "value": {"stringValue": host_data["host_name"]}},
            {"key": "host.id", "value": {"stringValue": host_data["host_id"]}},
            {"key": "host.arch", "value": {"stringValue": host_data["host_arch"]}},
            {"key": "host.type", "value": {"stringValue": host_data["host_type"]}},
            {"key": "host.image.id", "value": {"stringValue": host_data["host_image_id"]}},
            # CPU info
            {"key": "host.cpu.model.name", "value": {"stringValue": host_data["host_cpu_model"]}},
            {"key": "host.cpu.vendor.id", "value": {"stringValue": host_data["host_cpu_vendor"]}},
            {"key": "host.cpu.family", "value": {"stringValue": host_data["host_cpu_family"]}},
            {"key": "host.cpu.model.id", "value": {"stringValue": host_data["host_cpu_model_id"]}},
            {"key": "host.cpu.stepping", "value": {"stringValue": host_data["host_cpu_stepping"]}},
            {"key": "host.cpu.cache.l2.size", "value": {"intValue": str(host_data["host_cpu_cache_l2_size"])}},
            # OS
            {"key": "os.type", "value": {"stringValue": host_data["os_type"]}},
            {"key": "os.description", "value": {"stringValue": host_data["os_description"]}},
            # Cloud
            {"key": "cloud.provider", "value": {"stringValue": host_data["cloud_provider"]}},
            {"key": "cloud.platform", "value": {"stringValue": host_data["cloud_platform"]}},
            {"key": "cloud.region", "value": {"stringValue": host_data["cloud_region"]}},
            {"key": "cloud.availability_zone", "value": {"stringValue": host_data["cloud_zone"]}},
            {"key": "cloud.account.id", "value": {"stringValue": host_data["cloud_account_id"]}},
            {"key": "cloud.instance.id", "value": {"stringValue": host_data["cloud_instance_id"]}},
            # K8s
            {"key": "k8s.cluster.name", "value": {"stringValue": host_data["k8s_cluster_name"]}},
        ]

        # Add IP array
        attrs.append({
            "key": "host.ip",
            "value": {"arrayValue": {"values": [{"stringValue": ip} for ip in host_data["host_ips"]]}}
        })

        # Add MAC array
        attrs.append({
            "key": "host.mac",
            "value": {"arrayValue": {"values": [{"stringValue": mac} for mac in host_data["host_macs"]]}}
        })

        return attrs

    def generate_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics payload for all hosts."""
        resource_metrics = []
        current_time_ns = str(time.time_ns())
        start_time_ns = str(self._start_timestamp)

        for host_name, host_data in self._hosts.items():
            counters = self._counters[host_name]
            resource_attrs = self._format_resource_attributes(host_data)

            # Generate metrics grouped by scraper (scope)
            # Each scraper produces its own resourceMetrics entry

            # 1. Load metrics (load averages)
            resource_metrics.append(self._create_resource_metrics(
                resource_attrs,
                self.SCRAPERS["load"],
                self._generate_load_metrics(current_time_ns, host_data),
            ))

            # 2. CPU metrics
            resource_metrics.append(self._create_resource_metrics(
                resource_attrs,
                self.SCRAPERS["cpu"],
                self._generate_cpu_metrics(current_time_ns, start_time_ns, host_data, counters),
            ))

            # 3. Memory metrics
            resource_metrics.append(self._create_resource_metrics(
                resource_attrs,
                self.SCRAPERS["memory"],
                self._generate_memory_metrics(current_time_ns, host_data),
            ))

            # 4. Disk metrics
            resource_metrics.append(self._create_resource_metrics(
                resource_attrs,
                self.SCRAPERS["disk"],
                self._generate_disk_metrics(current_time_ns, start_time_ns, host_data, counters),
            ))

            # 5. Filesystem metrics
            resource_metrics.append(self._create_resource_metrics(
                resource_attrs,
                self.SCRAPERS["filesystem"],
                self._generate_filesystem_metrics(current_time_ns, host_data),
            ))

            # 6. Network metrics
            resource_metrics.append(self._create_resource_metrics(
                resource_attrs,
                self.SCRAPERS["network"],
                self._generate_network_metrics(current_time_ns, start_time_ns, host_data, counters),
            ))

            # 7. Processes metrics
            resource_metrics.append(self._create_resource_metrics(
                resource_attrs,
                self.SCRAPERS["processes"],
                self._generate_processes_metrics(current_time_ns),
            ))

        return {"resourceMetrics": resource_metrics}

    def _create_resource_metrics(
        self,
        resource_attrs: List[Dict[str, Any]],
        scope_name: str,
        metrics: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a resourceMetrics entry."""
        return {
            "resource": {
                "attributes": resource_attrs,
                "schemaUrl": self.SCHEMA_URL,
            },
            "scopeMetrics": [{
                "scope": {
                    "name": scope_name,
                    "version": self.SCRAPER_VERSION,
                },
                "metrics": metrics,
            }],
        }

    def _generate_load_metrics(self, time_ns: str, host_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate system load average metrics."""
        # Realistic load averages based on CPU count
        cpu_count = host_data["cpu_count"]
        base_load = random.uniform(0.5, 2.0)

        return [
        # CPU logical count - REQUIRED for Normalized Load calculation
        {
            "name": "system.cpu.logical.count",
            "unit": "{cpu}",
            "gauge": {
                "dataPoints": [{
                    "timeUnixNano": time_ns,
                    "asInt": str(cpu_count),
                }]
            }
        }, {
            "name": "system.cpu.load_average.1m",
            "unit": "{thread}",
            "gauge": {
                "dataPoints": [{
                    "timeUnixNano": time_ns,
                    "asDouble": base_load + random.uniform(-0.2, 0.2),
                }]
            }
        }, {
            "name": "system.cpu.load_average.5m",
            "unit": "{thread}",
            "gauge": {
                "dataPoints": [{
                    "timeUnixNano": time_ns,
                    "asDouble": base_load + random.uniform(-0.1, 0.1),
                }]
            }
        }, {
            "name": "system.cpu.load_average.15m",
            "unit": "{thread}",
            "gauge": {
                "dataPoints": [{
                    "timeUnixNano": time_ns,
                    "asDouble": base_load + random.uniform(-0.05, 0.05),
                }]
            }
        }]

    def _generate_cpu_metrics(
        self,
        time_ns: str,
        start_time_ns: str,
        host_data: Dict[str, Any],
        counters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate CPU time and utilization metrics."""
        metrics = []

        # Update counters
        counters["cpu_time_user"] += random.randint(100_000_000, 1_000_000_000)
        counters["cpu_time_system"] += random.randint(10_000_000, 100_000_000)
        counters["cpu_time_idle"] += random.randint(1_000_000_000, 5_000_000_000)
        counters["cpu_time_iowait"] += random.randint(1_000_000, 10_000_000)

        cpu_states = [
            ("user", counters["cpu_time_user"]),
            ("system", counters["cpu_time_system"]),
            ("idle", counters["cpu_time_idle"]),
            ("iowait", counters["cpu_time_iowait"]),
        ]

        for state, value in cpu_states:
            metrics.append({
                "name": "system.cpu.time",
                "unit": "s",
                "sum": {
                    "dataPoints": [{
                        "startTimeUnixNano": start_time_ns,
                        "timeUnixNano": time_ns,
                        "asDouble": value / 1_000_000_000,  # Convert to seconds
                        "attributes": [
                            {"key": "cpu", "value": {"stringValue": "cpu0"}},
                            {"key": "state", "value": {"stringValue": state}},
                        ],
                    }],
                    "aggregationTemporality": 2,  # CUMULATIVE
                    "isMonotonic": True,
                }
            })

        # CPU utilization (gauge) - need all states that sum to ~1.0
        # Generate realistic utilization breakdown
        # Note: Elastic uses "wait" not "iowait" for CPU Usage calculation
        user_util = random.uniform(0.15, 0.35)
        system_util = random.uniform(0.05, 0.15)
        wait_util = random.uniform(0.0, 0.05)  # "wait" state for Elastic
        nice_util = random.uniform(0.0, 0.02)
        softirq_util = random.uniform(0.0, 0.01)
        steal_util = 0.0
        irq_util = 0.0
        idle_util = 1.0 - user_util - system_util - wait_util - nice_util - softirq_util

        cpu_util_states = [
            ("user", user_util),
            ("system", system_util),
            ("idle", idle_util),
            ("wait", wait_util),  # Elastic expects "wait" not "iowait"
            ("nice", nice_util),
            ("softirq", softirq_util),
            ("steal", steal_util),
            ("irq", irq_util),
        ]

        for state, util_value in cpu_util_states:
            metrics.append({
                "name": "system.cpu.utilization",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": time_ns,
                        "asDouble": util_value,
                        "attributes": [
                            {"key": "cpu", "value": {"stringValue": "cpu0"}},
                            {"key": "state", "value": {"stringValue": state}},
                        ],
                    }]
                }
            })

        return metrics

    def _generate_memory_metrics(self, time_ns: str, host_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate memory usage metrics."""
        total_bytes = host_data["memory_total_bytes"]

        # Generate realistic memory breakdown that sums correctly
        # Typical server: 40-60% used, 15-25% cached, 2-5% buffered, rest free
        used_pct = random.uniform(0.40, 0.60)
        cached_pct = random.uniform(0.15, 0.25)
        buffered_pct = random.uniform(0.02, 0.05)
        free_pct = 1.0 - used_pct - cached_pct - buffered_pct

        used_bytes = int(total_bytes * used_pct)
        cached_bytes = int(total_bytes * cached_pct)
        buffered_bytes = int(total_bytes * buffered_pct)
        free_bytes = int(total_bytes * free_pct)

        metrics = []
        memory_states = [
            ("used", used_bytes),
            ("free", free_bytes),
            ("cached", cached_bytes),
            ("buffered", buffered_bytes),
        ]

        for state, value in memory_states:
            metrics.append({
                "name": "system.memory.usage",
                "unit": "By",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": time_ns,
                        "asInt": str(value),
                        "attributes": [
                            {"key": "state", "value": {"stringValue": state}},
                        ],
                    }]
                }
            })

        # Memory utilization WITH state attributes
        # Elastic Memory Usage formula needs: used + buffered + slab_reclaimable + slab_unreclaimable
        slab_reclaimable_pct = random.uniform(0.01, 0.03)
        slab_unreclaimable_pct = random.uniform(0.005, 0.015)

        memory_util_states = [
            ("used", used_pct),
            ("free", free_pct),
            ("cached", cached_pct),
            ("buffered", buffered_pct),
            ("slab_reclaimable", slab_reclaimable_pct),
            ("slab_unreclaimable", slab_unreclaimable_pct),
        ]

        for state, util_value in memory_util_states:
            metrics.append({
                "name": "system.memory.utilization",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": time_ns,
                        "asDouble": util_value,
                        "attributes": [
                            {"key": "state", "value": {"stringValue": state}},
                        ],
                    }]
                }
            })

        return metrics

    def _generate_disk_metrics(
        self,
        time_ns: str,
        start_time_ns: str,
        host_data: Dict[str, Any],
        counters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate disk I/O metrics."""
        metrics = []

        for device in host_data.get("disk_devices", []):
            # Update counters
            counters["disk_read_bytes"][device] += random.randint(1_000_000, 50_000_000)
            counters["disk_write_bytes"][device] += random.randint(1_000_000, 50_000_000)
            counters["disk_read_ops"][device] += random.randint(100, 5000)
            counters["disk_write_ops"][device] += random.randint(100, 5000)

            # Disk I/O bytes
            for direction, value in [
                ("read", counters["disk_read_bytes"][device]),
                ("write", counters["disk_write_bytes"][device]),
            ]:
                metrics.append({
                    "name": "system.disk.io",
                    "unit": "By",
                    "sum": {
                        "dataPoints": [{
                            "startTimeUnixNano": start_time_ns,
                            "timeUnixNano": time_ns,
                            "asInt": str(value),
                            "attributes": [
                                {"key": "device", "value": {"stringValue": device}},
                                {"key": "direction", "value": {"stringValue": direction}},
                            ],
                        }],
                        "aggregationTemporality": 2,
                        "isMonotonic": True,
                    }
                })

            # Disk operations
            for direction, value in [
                ("read", counters["disk_read_ops"][device]),
                ("write", counters["disk_write_ops"][device]),
            ]:
                metrics.append({
                    "name": "system.disk.operations",
                    "unit": "{operation}",
                    "sum": {
                        "dataPoints": [{
                            "startTimeUnixNano": start_time_ns,
                            "timeUnixNano": time_ns,
                            "asInt": str(value),
                            "attributes": [
                                {"key": "device", "value": {"stringValue": device}},
                                {"key": "direction", "value": {"stringValue": direction}},
                            ],
                        }],
                        "aggregationTemporality": 2,
                        "isMonotonic": True,
                    }
                })

        return metrics

    def _generate_filesystem_metrics(self, time_ns: str, host_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate filesystem usage metrics."""
        metrics = []
        total_bytes = host_data["disk_total_bytes"]

        for fs in host_data.get("filesystems", []):
            # Allocate portion of total disk to this filesystem
            fs_total = total_bytes // len(host_data["filesystems"])
            fs_used = int(fs_total * random.uniform(0.3, 0.7))
            fs_free = fs_total - fs_used

            for state, value in [("used", fs_used), ("free", fs_free)]:
                metrics.append({
                    "name": "system.filesystem.usage",
                    "unit": "By",
                    "gauge": {
                        "dataPoints": [{
                            "timeUnixNano": time_ns,
                            "asInt": str(value),
                            "attributes": [
                                {"key": "device", "value": {"stringValue": fs["device"]}},
                                {"key": "mountpoint", "value": {"stringValue": fs["mountpoint"]}},
                                {"key": "type", "value": {"stringValue": fs["type"]}},
                                {"key": "state", "value": {"stringValue": state}},
                            ],
                        }]
                    }
                })

            # Filesystem utilization
            metrics.append({
                "name": "system.filesystem.utilization",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": time_ns,
                        "asDouble": fs_used / fs_total,
                        "attributes": [
                            {"key": "device", "value": {"stringValue": fs["device"]}},
                            {"key": "mountpoint", "value": {"stringValue": fs["mountpoint"]}},
                            {"key": "type", "value": {"stringValue": fs["type"]}},
                        ],
                    }]
                }
            })

        return metrics

    def _generate_network_metrics(
        self,
        time_ns: str,
        start_time_ns: str,
        host_data: Dict[str, Any],
        counters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate network I/O metrics."""
        metrics = []

        for device in host_data.get("network_devices", []):
            # Update counters
            counters["network_rx_bytes"][device] += random.randint(1_000_000, 100_000_000)
            counters["network_tx_bytes"][device] += random.randint(1_000_000, 100_000_000)

            for direction, value in [
                ("receive", counters["network_rx_bytes"][device]),
                ("transmit", counters["network_tx_bytes"][device]),
            ]:
                metrics.append({
                    "name": "system.network.io",
                    "unit": "By",
                    "sum": {
                        "dataPoints": [{
                            "startTimeUnixNano": start_time_ns,
                            "timeUnixNano": time_ns,
                            "asInt": str(value),
                            "attributes": [
                                {"key": "device", "value": {"stringValue": device}},
                                {"key": "direction", "value": {"stringValue": direction}},
                            ],
                        }],
                        "aggregationTemporality": 2,
                        "isMonotonic": True,
                    }
                })

        return metrics

    def _generate_processes_metrics(self, time_ns: str) -> List[Dict[str, Any]]:
        """Generate process count metrics."""
        return [{
            "name": "system.processes.count",
            "unit": "{process}",
            "gauge": {
                "dataPoints": [{
                    "timeUnixNano": time_ns,
                    "asInt": str(random.randint(100, 300)),
                    "attributes": [
                        {"key": "status", "value": {"stringValue": "running"}},
                    ],
                }]
            }
        }, {
            "name": "system.processes.count",
            "unit": "{process}",
            "gauge": {
                "dataPoints": [{
                    "timeUnixNano": time_ns,
                    "asInt": str(random.randint(5, 20)),
                    "attributes": [
                        {"key": "status", "value": {"stringValue": "sleeping"}},
                    ],
                }]
            }
        }]

    def get_host_names(self) -> List[str]:
        """Return list of host names being generated."""
        return list(self._hosts.keys())
