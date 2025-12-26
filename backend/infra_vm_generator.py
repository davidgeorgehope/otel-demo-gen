"""
VM and Hypervisor telemetry generator.
Generates metrics for ESXi, Hyper-V, KVM virtual machines following OTel system.* conventions.

Reference: https://opentelemetry.io/docs/specs/semconv/system/system-metrics/
"""
import secrets
import random
import time
import uuid
from typing import Dict, List, Any, Optional

from config_schema import ScenarioConfig, VirtualMachine
from correlation_manager import CorrelationManager
from base_infra_generator import BaseInfrastructureGenerator


class VMHypervisorGenerator(BaseInfrastructureGenerator):
    """
    Generates VM/Hypervisor metrics following OTel system.* and process.* conventions.
    Supports ESXi, Hyper-V, KVM, and Proxmox hypervisors.
    """

    # Hypervisor-specific configurations
    HYPERVISOR_CONFIGS = {
        "esxi": {
            "os_type": "vmkernel",
            "os_description": "VMware ESXi 8.0 Update 2",
            "host_prefix": "esxi-",
            "management_agent": "vpxa",
        },
        "hyperv": {
            "os_type": "windows",
            "os_description": "Microsoft Windows Server 2022 Datacenter",
            "host_prefix": "hyperv-",
            "management_agent": "vmms",
        },
        "kvm": {
            "os_type": "linux",
            "os_description": "Ubuntu 22.04.3 LTS",
            "host_prefix": "kvm-",
            "management_agent": "libvirtd",
        },
        "proxmox": {
            "os_type": "linux",
            "os_description": "Proxmox VE 8.1",
            "host_prefix": "pve-",
            "management_agent": "pveproxy",
        },
    }

    def __init__(self, config: ScenarioConfig, correlation_manager: Optional[CorrelationManager] = None):
        super().__init__(config, correlation_manager)

        # Get VMs from infrastructure config
        self.vms: List[VirtualMachine] = []
        if config.infrastructure and config.infrastructure.virtual_machines:
            self.vms = config.infrastructure.virtual_machines

        self._vm_data = self._initialize_vm_data()
        self._host_data = self._initialize_host_data()
        self._counters = self._initialize_counters()

    def _initialize_vm_data(self) -> Dict[str, Dict[str, Any]]:
        """Initialize static VM data for consistency."""
        vm_data = {}

        for vm in self.vms:
            hypervisor_type = vm.hypervisor_type.lower()
            config = self.HYPERVISOR_CONFIGS.get(hypervisor_type, self.HYPERVISOR_CONFIGS["kvm"])

            vm_data[vm.name] = {
                "vm_id": str(uuid.uuid4()),
                "hypervisor_type": hypervisor_type,
                "host_name": vm.host_name,
                "vcpus": vm.vcpus,
                "memory_gb": vm.memory_gb,
                "disk_gb": vm.disk_gb,
                "hosted_services": vm.hosted_services,
                "ip_address": f"10.{random.randint(100, 200)}.{random.randint(1, 254)}.{random.randint(1, 254)}",
                "mac_address": ":".join([secrets.token_hex(1) for _ in range(6)]),
                "os_type": random.choice(["linux", "windows"]),
                "power_state": "running",
                "created_at": time.time() - random.randint(86400, 86400 * 90),  # 1-90 days ago
            }

        return vm_data

    def _initialize_host_data(self) -> Dict[str, Dict[str, Any]]:
        """Initialize hypervisor host data."""
        # Group VMs by host
        hosts = {}
        for vm in self.vms:
            host_name = vm.host_name
            if host_name not in hosts:
                hypervisor_type = vm.hypervisor_type.lower()
                config = self.HYPERVISOR_CONFIGS.get(hypervisor_type, self.HYPERVISOR_CONFIGS["kvm"])

                hosts[host_name] = {
                    "host_id": str(uuid.uuid4()),
                    "hypervisor_type": hypervisor_type,
                    "os_type": config["os_type"],
                    "os_description": config["os_description"],
                    "physical_cpus": random.choice([16, 24, 32, 48, 64]),
                    "physical_memory_gb": random.choice([128, 256, 384, 512]),
                    "ip_address": f"10.{random.randint(1, 50)}.{random.randint(1, 254)}.{random.randint(1, 254)}",
                    "vms": [],
                }
            hosts[host_name]["vms"].append(vm.name)

        return hosts

    def _initialize_counters(self) -> Dict[str, Dict[str, Any]]:
        """Initialize counters for VMs and hosts."""
        counters = {}

        # VM counters
        for vm in self.vms:
            counters[vm.name] = {
                "cpu_time_ns": random.randint(1_000_000_000_000, 10_000_000_000_000),
                "disk_read_bytes": random.randint(1_000_000_000, 100_000_000_000),
                "disk_write_bytes": random.randint(1_000_000_000, 100_000_000_000),
                "disk_read_ops": random.randint(1_000_000, 50_000_000),
                "disk_write_ops": random.randint(1_000_000, 50_000_000),
                "network_rx_bytes": random.randint(1_000_000_000, 100_000_000_000),
                "network_tx_bytes": random.randint(1_000_000_000, 100_000_000_000),
            }

        # Host counters
        for host_name in self._host_data:
            counters[f"host:{host_name}"] = {
                "cpu_time_ns": random.randint(10_000_000_000_000, 100_000_000_000_000),
                "disk_read_bytes": random.randint(10_000_000_000, 1_000_000_000_000),
                "disk_write_bytes": random.randint(10_000_000_000, 1_000_000_000_000),
            }

        return counters

    def generate_vm_resource_attributes(self, vm: VirtualMachine) -> Dict[str, Any]:
        """Generate OTel resource attributes for a VM."""
        vm_info = self._vm_data.get(vm.name, {})

        attrs = {
            # Service attributes (for hosted services)
            "service.name": vm.name,
            "service.instance.id": vm_info.get("vm_id", str(uuid.uuid4())),

            # Host attributes (VM is the host from perspective of apps running on it)
            "host.id": vm_info.get("vm_id", ""),
            "host.name": vm.name,
            "host.type": "vm",
            "host.ip": vm_info.get("ip_address", ""),
            "host.mac": vm_info.get("mac_address", ""),

            # OS attributes
            "os.type": vm_info.get("os_type", "linux"),

            # VM-specific attributes
            "vm.id": vm_info.get("vm_id", ""),
            "vm.name": vm.name,
            "vm.hypervisor.type": vm.hypervisor_type,
            "vm.hypervisor.host": vm.host_name,
            "vm.vcpus": vm.vcpus,
            "vm.memory_gb": vm.memory_gb,
            "vm.power_state": vm_info.get("power_state", "running"),

            # Data stream for Elastic
            "data_stream.type": "metrics",
            "data_stream.dataset": "system.vm",
            "data_stream.namespace": "default",
        }

        # Add correlation attributes if affected by incident
        if self.correlation_manager:
            correlation_attrs = self.correlation_manager.get_attributes_for_component(vm.name)
            attrs.update(correlation_attrs)

        return attrs

    def generate_host_resource_attributes(self, host_name: str) -> Dict[str, Any]:
        """Generate OTel resource attributes for a hypervisor host."""
        host_info = self._host_data.get(host_name, {})

        attrs = {
            "host.id": host_info.get("host_id", ""),
            "host.name": host_name,
            "host.type": "hypervisor",
            "host.ip": host_info.get("ip_address", ""),

            "os.type": host_info.get("os_type", "linux"),
            "os.description": host_info.get("os_description", ""),

            "hypervisor.type": host_info.get("hypervisor_type", "kvm"),
            "hypervisor.physical_cpus": host_info.get("physical_cpus", 16),
            "hypervisor.physical_memory_gb": host_info.get("physical_memory_gb", 128),
            "hypervisor.vm_count": len(host_info.get("vms", [])),

            "data_stream.type": "metrics",
            "data_stream.dataset": "system.hypervisor",
            "data_stream.namespace": "default",
        }

        # Add correlation attributes if host is affected
        if self.correlation_manager:
            correlation_attrs = self.correlation_manager.get_attributes_for_component(host_name)
            attrs.update(correlation_attrs)

        return attrs

    def generate_vm_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics payload for all VMs."""
        if not self.vms:
            return {"resourceMetrics": []}

        resource_metrics = []
        current_time_ns = str(time.time_ns())

        for vm in self.vms:
            vm_info = self._vm_data.get(vm.name, {})
            vm_counters = self._counters.get(vm.name, {})

            # Check for incident effects
            effect = None
            if self.correlation_manager:
                effect = self.correlation_manager.get_effect_for_component(vm.name)

            # Also check if the host is affected (cascades to VMs)
            host_effect = None
            if self.correlation_manager:
                host_effect = self.correlation_manager.get_effect_for_component(vm.host_name)

            # Generate VM metrics
            metrics = self._generate_vm_metrics(
                current_time_ns, vm, vm_info, vm_counters, effect or host_effect
            )

            resource_attrs = self._format_attributes(self.generate_vm_resource_attributes(vm))

            resource_metrics.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": self.SCHEMA_URL,
                },
                "scopeMetrics": [{
                    "scope": {
                        "name": "otel-demo-gen/vm-metrics-receiver",
                        "version": "1.0.0",
                    },
                    "metrics": metrics,
                }],
            })

        return {"resourceMetrics": resource_metrics}

    def generate_hypervisor_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics payload for hypervisor hosts."""
        if not self._host_data:
            return {"resourceMetrics": []}

        resource_metrics = []
        current_time_ns = str(time.time_ns())

        for host_name, host_info in self._host_data.items():
            host_counters = self._counters.get(f"host:{host_name}", {})

            # Check for incident effects
            effect = None
            if self.correlation_manager:
                effect = self.correlation_manager.get_effect_for_component(host_name)

            # Generate host metrics
            metrics = self._generate_host_metrics(
                current_time_ns, host_name, host_info, host_counters, effect
            )

            resource_attrs = self._format_attributes(self.generate_host_resource_attributes(host_name))

            resource_metrics.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": self.SCHEMA_URL,
                },
                "scopeMetrics": [{
                    "scope": {
                        "name": "otel-demo-gen/hypervisor-metrics-receiver",
                        "version": "1.0.0",
                    },
                    "metrics": metrics,
                }],
            })

        return {"resourceMetrics": resource_metrics}

    def _generate_vm_metrics(
        self,
        current_time_ns: str,
        vm: VirtualMachine,
        vm_info: Dict[str, Any],
        vm_counters: Dict[str, Any],
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate metrics for a single VM."""
        metrics = []

        # Apply incident effects
        cpu_multiplier = 1.0
        memory_multiplier = 1.0
        io_multiplier = 1.0

        if effect:
            effect_type = effect.get("effect", "")
            params = effect.get("parameters", {})

            if effect_type == "vm_host_overload":
                cpu_multiplier = params.get("cpu_multiplier", 1.5)
                memory_multiplier = params.get("memory_multiplier", 1.3)
            elif effect_type == "memory_pressure":
                memory_multiplier = params.get("memory_percentage", 95) / 50.0
            elif effect_type == "cpu_spike":
                cpu_multiplier = params.get("cpu_percentage", 90) / 40.0
            elif effect_type == "storage_latency":
                io_multiplier = params.get("latency_multiplier", 3.0)

        # CPU metrics
        cpu_utilization = min(1.0, random.uniform(0.1, 0.5) * cpu_multiplier)
        cpu_time_increment = int(random.randint(100_000_000, 1_000_000_000) * cpu_multiplier)
        vm_counters["cpu_time_ns"] = vm_counters.get("cpu_time_ns", 0) + cpu_time_increment

        metrics.extend([
            self._create_gauge_metric("system.cpu.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": cpu_utilization,
                "attributes": [{"key": "cpu.mode", "value": {"stringValue": "user"}}],
            }]),
            self._create_sum_metric("system.cpu.time", "s", True, [{
                "timeUnixNano": current_time_ns,
                "asDouble": vm_counters["cpu_time_ns"] / 1_000_000_000,
                "attributes": [{"key": "cpu.mode", "value": {"stringValue": "user"}}],
            }]),
            self._create_gauge_metric("vm.vcpu.count", "{vcpu}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(vm.vcpus),
            }]),
        ])

        # Memory metrics
        memory_bytes = vm.memory_gb * 1024 * 1024 * 1024
        memory_used = int(memory_bytes * min(0.95, random.uniform(0.3, 0.6) * memory_multiplier))

        metrics.extend([
            self._create_gauge_metric("system.memory.usage", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(memory_used),
                "attributes": [{"key": "system.memory.state", "value": {"stringValue": "used"}}],
            }]),
            self._create_gauge_metric("system.memory.usage", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(memory_bytes - memory_used),
                "attributes": [{"key": "system.memory.state", "value": {"stringValue": "free"}}],
            }]),
            self._create_gauge_metric("system.memory.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": memory_used / memory_bytes,
            }]),
            self._create_gauge_metric("vm.memory.limit", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(memory_bytes),
            }]),
        ])

        # Disk I/O metrics
        disk_read_increment = int(random.randint(1_000_000, 50_000_000) * io_multiplier)
        disk_write_increment = int(random.randint(1_000_000, 50_000_000) * io_multiplier)
        vm_counters["disk_read_bytes"] = vm_counters.get("disk_read_bytes", 0) + disk_read_increment
        vm_counters["disk_write_bytes"] = vm_counters.get("disk_write_bytes", 0) + disk_write_increment
        vm_counters["disk_read_ops"] = vm_counters.get("disk_read_ops", 0) + random.randint(100, 5000)
        vm_counters["disk_write_ops"] = vm_counters.get("disk_write_ops", 0) + random.randint(100, 5000)

        metrics.extend([
            self._create_sum_metric("system.disk.io", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(vm_counters["disk_read_bytes"]),
                "attributes": [{"key": "disk.io.direction", "value": {"stringValue": "read"}}],
            }]),
            self._create_sum_metric("system.disk.io", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(vm_counters["disk_write_bytes"]),
                "attributes": [{"key": "disk.io.direction", "value": {"stringValue": "write"}}],
            }]),
            self._create_sum_metric("system.disk.operations", "{operation}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(vm_counters["disk_read_ops"]),
                "attributes": [{"key": "disk.io.direction", "value": {"stringValue": "read"}}],
            }]),
            self._create_sum_metric("system.disk.operations", "{operation}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(vm_counters["disk_write_ops"]),
                "attributes": [{"key": "disk.io.direction", "value": {"stringValue": "write"}}],
            }]),
        ])

        # Disk capacity metrics
        disk_bytes = vm.disk_gb * 1024 * 1024 * 1024
        disk_used = int(disk_bytes * random.uniform(0.3, 0.7))

        metrics.extend([
            self._create_gauge_metric("system.filesystem.usage", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(disk_used),
                "attributes": [
                    {"key": "system.filesystem.state", "value": {"stringValue": "used"}},
                    {"key": "system.device", "value": {"stringValue": "/dev/sda1"}},
                ],
            }]),
            self._create_gauge_metric("system.filesystem.usage", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(disk_bytes - disk_used),
                "attributes": [
                    {"key": "system.filesystem.state", "value": {"stringValue": "free"}},
                    {"key": "system.device", "value": {"stringValue": "/dev/sda1"}},
                ],
            }]),
        ])

        # Network I/O metrics
        network_rx_increment = random.randint(100_000, 10_000_000)
        network_tx_increment = random.randint(100_000, 10_000_000)
        vm_counters["network_rx_bytes"] = vm_counters.get("network_rx_bytes", 0) + network_rx_increment
        vm_counters["network_tx_bytes"] = vm_counters.get("network_tx_bytes", 0) + network_tx_increment

        metrics.extend([
            self._create_sum_metric("system.network.io", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(vm_counters["network_rx_bytes"]),
                "attributes": [
                    {"key": "network.io.direction", "value": {"stringValue": "receive"}},
                    {"key": "system.device", "value": {"stringValue": "eth0"}},
                ],
            }]),
            self._create_sum_metric("system.network.io", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(vm_counters["network_tx_bytes"]),
                "attributes": [
                    {"key": "network.io.direction", "value": {"stringValue": "transmit"}},
                    {"key": "system.device", "value": {"stringValue": "eth0"}},
                ],
            }]),
        ])

        # VM-specific power state and uptime
        uptime_seconds = int(time.time() - vm_info.get("created_at", time.time() - 86400))
        metrics.extend([
            self._create_gauge_metric("vm.uptime", "s", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(uptime_seconds),
            }]),
            self._create_gauge_metric("vm.power_state", "1", [{
                "timeUnixNano": current_time_ns,
                "asInt": "1" if vm_info.get("power_state") == "running" else "0",
            }]),
        ])

        return metrics

    def _generate_host_metrics(
        self,
        current_time_ns: str,
        host_name: str,
        host_info: Dict[str, Any],
        host_counters: Dict[str, Any],
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate metrics for a hypervisor host."""
        metrics = []

        # Apply incident effects
        cpu_pressure = 1.0
        memory_pressure = 1.0

        if effect:
            effect_type = effect.get("effect", "")
            params = effect.get("parameters", {})

            if effect_type == "vm_host_overload":
                cpu_pressure = params.get("cpu_multiplier", 1.5)
                memory_pressure = params.get("memory_multiplier", 1.3)
            elif effect_type == "memory_pressure":
                memory_pressure = params.get("memory_percentage", 95) / 50.0

        physical_cpus = host_info.get("physical_cpus", 16)
        physical_memory_gb = host_info.get("physical_memory_gb", 128)
        vm_count = len(host_info.get("vms", []))

        # Calculate overcommit ratios
        total_vcpus = sum(
            self._vm_data[vm_name].get("vcpus", 4)
            for vm_name in host_info.get("vms", [])
            if vm_name in self._vm_data
        )
        total_vm_memory_gb = sum(
            self._vm_data[vm_name].get("memory_gb", 16)
            for vm_name in host_info.get("vms", [])
            if vm_name in self._vm_data
        )

        cpu_overcommit = total_vcpus / physical_cpus if physical_cpus > 0 else 0
        memory_overcommit = total_vm_memory_gb / physical_memory_gb if physical_memory_gb > 0 else 0

        # Host CPU metrics
        host_cpu_utilization = min(0.95, random.uniform(0.2, 0.5) * cpu_pressure)
        metrics.extend([
            self._create_gauge_metric("system.cpu.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": host_cpu_utilization,
            }]),
            self._create_gauge_metric("hypervisor.cpu.count", "{cpu}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(physical_cpus),
            }]),
            self._create_gauge_metric("hypervisor.cpu.overcommit", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": cpu_overcommit,
            }]),
        ])

        # Host memory metrics
        memory_bytes = physical_memory_gb * 1024 * 1024 * 1024
        memory_used = int(memory_bytes * min(0.95, random.uniform(0.4, 0.7) * memory_pressure))

        metrics.extend([
            self._create_gauge_metric("system.memory.usage", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(memory_used),
                "attributes": [{"key": "system.memory.state", "value": {"stringValue": "used"}}],
            }]),
            self._create_gauge_metric("system.memory.limit", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(memory_bytes),
            }]),
            self._create_gauge_metric("hypervisor.memory.overcommit", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": memory_overcommit,
            }]),
        ])

        # VM count
        metrics.append(self._create_gauge_metric("hypervisor.vm.count", "{vm}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(vm_count),
        }]))

        # VMs by power state
        metrics.extend([
            self._create_gauge_metric("hypervisor.vm.running", "{vm}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(vm_count),  # Assume all running
            }]),
            self._create_gauge_metric("hypervisor.vm.stopped", "{vm}", [{
                "timeUnixNano": current_time_ns,
                "asInt": "0",
            }]),
        ])

        return metrics

    # _create_gauge_metric, _create_sum_metric, and _format_attributes
    # are now inherited from BaseInfrastructureGenerator
