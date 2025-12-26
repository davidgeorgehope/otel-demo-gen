"""
Storage system metrics generator.
Generates IOPS, latency, capacity metrics for SAN/NAS/Cloud storage.
"""
import secrets
import random
import time
import uuid
from typing import Dict, List, Any, Optional

from config_schema import ScenarioConfig, StorageSystem
from correlation_manager import CorrelationManager
from base_infra_generator import BaseInfrastructureGenerator


class StorageMetricsGenerator(BaseInfrastructureGenerator):
    """
    Generates storage system metrics for SAN, NAS, and cloud storage.
    """

    # Storage type configurations
    STORAGE_CONFIGS = {
        "san": {
            "vendor_default": "dell_emc",
            "protocols": ["FC", "iSCSI"],
            "typical_iops": (10000, 100000),
            "typical_latency_ms": (0.5, 5.0),
        },
        "nas": {
            "vendor_default": "netapp",
            "protocols": ["NFS", "SMB"],
            "typical_iops": (5000, 50000),
            "typical_latency_ms": (1.0, 10.0),
        },
        "s3": {
            "vendor_default": "aws",
            "protocols": ["HTTPS"],
            "typical_iops": (1000, 10000),
            "typical_latency_ms": (10.0, 100.0),
        },
        "azure_blob": {
            "vendor_default": "microsoft",
            "protocols": ["HTTPS"],
            "typical_iops": (1000, 10000),
            "typical_latency_ms": (10.0, 100.0),
        },
        "nfs": {
            "vendor_default": "generic",
            "protocols": ["NFSv4"],
            "typical_iops": (5000, 30000),
            "typical_latency_ms": (1.0, 15.0),
        },
        "iscsi": {
            "vendor_default": "generic",
            "protocols": ["iSCSI"],
            "typical_iops": (8000, 80000),
            "typical_latency_ms": (0.5, 8.0),
        },
    }

    # Vendor-specific models
    VENDOR_MODELS = {
        "netapp": ["FAS8700", "AFF A400", "ONTAP Select"],
        "dell_emc": ["PowerStore 500", "Unity XT 480", "VNX5400"],
        "pure": ["FlashArray//X70", "FlashArray//C40"],
        "hpe": ["Primera 630", "Nimble AF40", "3PAR 8440"],
        "aws": ["S3 Standard", "S3 Intelligent-Tiering", "EBS gp3"],
        "microsoft": ["Premium Blob", "Standard Blob", "Azure Files"],
        "generic": ["Generic NAS", "Generic iSCSI Target"],
    }

    def __init__(self, config: ScenarioConfig, correlation_manager: Optional[CorrelationManager] = None):
        super().__init__(config, correlation_manager)

        # Get storage systems from infrastructure config
        self.storage_systems: List[StorageSystem] = []
        if config.infrastructure and config.infrastructure.storage_systems:
            self.storage_systems = config.infrastructure.storage_systems

        self._storage_data = self._initialize_storage_data()
        self._counters = self._initialize_counters()

    def _initialize_storage_data(self) -> Dict[str, Dict[str, Any]]:
        """Initialize static storage system data."""
        storage_data = {}

        for storage in self.storage_systems:
            storage_type = storage.type.lower()
            config = self.STORAGE_CONFIGS.get(storage_type, self.STORAGE_CONFIGS["san"])

            vendor = (storage.vendor or config["vendor_default"]).lower()
            models = self.VENDOR_MODELS.get(vendor, self.VENDOR_MODELS["generic"])

            # Generate LUNs/volumes
            volumes = [
                f"vol_{storage.name}_{i}" for i in range(1, random.randint(3, 8))
            ]

            storage_data[storage.name] = {
                "storage_id": str(uuid.uuid4()),
                "storage_type": storage_type,
                "vendor": vendor,
                "model": random.choice(models),
                "capacity_tb": storage.capacity_tb,
                "capacity_bytes": int(storage.capacity_tb * 1024 * 1024 * 1024 * 1024),
                "protocols": config["protocols"],
                "typical_iops": config["typical_iops"],
                "typical_latency_ms": config["typical_latency_ms"],
                "volumes": volumes,
                "connected_services": storage.connected_services,
                "ip_address": f"10.{random.randint(1, 50)}.{random.randint(1, 254)}.{random.randint(1, 254)}",
                "firmware_version": f"{random.randint(8, 12)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
            }

        return storage_data

    def _initialize_counters(self) -> Dict[str, Dict[str, Any]]:
        """Initialize counters for storage systems."""
        counters = {}

        for storage in self.storage_systems:
            storage_info = self._storage_data.get(storage.name, {})
            capacity_bytes = storage_info.get("capacity_bytes", 10 * 1024**4)

            counters[storage.name] = {
                "read_bytes": random.randint(1_000_000_000_000, 10_000_000_000_000),
                "write_bytes": random.randint(1_000_000_000_000, 10_000_000_000_000),
                "read_ops": random.randint(100_000_000, 1_000_000_000),
                "write_ops": random.randint(100_000_000, 1_000_000_000),
                "used_bytes": int(capacity_bytes * random.uniform(0.3, 0.7)),
            }

            # Per-volume counters
            for volume in storage_info.get("volumes", []):
                counters[f"{storage.name}:{volume}"] = {
                    "read_bytes": random.randint(100_000_000_000, 1_000_000_000_000),
                    "write_bytes": random.randint(100_000_000_000, 1_000_000_000_000),
                    "read_ops": random.randint(10_000_000, 100_000_000),
                    "write_ops": random.randint(10_000_000, 100_000_000),
                }

        return counters

    def generate_storage_resource_attributes(self, storage: StorageSystem) -> Dict[str, Any]:
        """Generate OTel resource attributes for a storage system."""
        storage_info = self._storage_data.get(storage.name, {})

        attrs = {
            "service.name": storage.name,
            "service.type": "storage",
            "service.instance.id": storage_info.get("storage_id", ""),

            "storage.id": storage_info.get("storage_id", ""),
            "storage.name": storage.name,
            "storage.type": storage.type,
            "storage.vendor": storage_info.get("vendor", ""),
            "storage.model": storage_info.get("model", ""),
            "storage.firmware_version": storage_info.get("firmware_version", ""),
            "storage.ip_address": storage_info.get("ip_address", ""),
            "storage.capacity_tb": storage.capacity_tb,

            "data_stream.type": "metrics",
            "data_stream.dataset": "storage",
            "data_stream.namespace": "default",
        }

        # Add correlation attributes if affected
        if self.correlation_manager:
            correlation_attrs = self.correlation_manager.get_attributes_for_component(storage.name)
            attrs.update(correlation_attrs)

        return attrs

    def generate_storage_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics payload for all storage systems."""
        if not self.storage_systems:
            return {"resourceMetrics": []}

        resource_metrics = []
        current_time_ns = str(time.time_ns())

        for storage in self.storage_systems:
            storage_info = self._storage_data.get(storage.name, {})
            storage_counters = self._counters.get(storage.name, {})

            # Check for incident effects
            effect = None
            if self.correlation_manager:
                effect = self.correlation_manager.get_effect_for_component(storage.name)

            # Generate storage metrics
            metrics = self._generate_storage_metrics(
                current_time_ns, storage, storage_info, storage_counters, effect
            )

            resource_attrs = self._format_attributes(self.generate_storage_resource_attributes(storage))

            resource_metrics.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": self.SCHEMA_URL,
                },
                "scopeMetrics": [{
                    "scope": {
                        "name": "otel-demo-gen/storage-metrics-receiver",
                        "version": "1.0.0",
                    },
                    "metrics": metrics,
                }],
            })

        return {"resourceMetrics": resource_metrics}

    def _generate_storage_metrics(
        self,
        current_time_ns: str,
        storage: StorageSystem,
        storage_info: Dict[str, Any],
        storage_counters: Dict[str, Any],
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate metrics for a single storage system."""
        metrics = []

        # Apply incident effects
        latency_multiplier = 1.0
        iops_reduction = 1.0
        error_increase = 0

        if effect:
            effect_type = effect.get("effect", "")
            params = effect.get("parameters", {})

            if effect_type == "storage_latency_spike":
                latency_multiplier = params.get("latency_multiplier", 5.0)
            elif effect_type == "storage_degraded":
                iops_reduction = params.get("iops_reduction", 0.5)
                latency_multiplier = params.get("latency_multiplier", 2.0)
            elif effect_type == "storage_errors":
                error_increase = params.get("error_rate", 0.05)

        typical_iops = storage_info.get("typical_iops", (10000, 100000))
        typical_latency = storage_info.get("typical_latency_ms", (0.5, 5.0))
        capacity_bytes = storage_info.get("capacity_bytes", 10 * 1024**4)

        # Current IOPS
        read_iops = int(random.uniform(*typical_iops) * iops_reduction)
        write_iops = int(random.uniform(*typical_iops) * 0.7 * iops_reduction)

        # Update counters
        read_bytes_increment = read_iops * random.randint(4096, 65536)
        write_bytes_increment = write_iops * random.randint(4096, 65536)

        storage_counters["read_bytes"] = storage_counters.get("read_bytes", 0) + read_bytes_increment
        storage_counters["write_bytes"] = storage_counters.get("write_bytes", 0) + write_bytes_increment
        storage_counters["read_ops"] = storage_counters.get("read_ops", 0) + read_iops
        storage_counters["write_ops"] = storage_counters.get("write_ops", 0) + write_iops

        # Slowly increase used space
        if random.random() < 0.1:
            storage_counters["used_bytes"] = min(
                int(capacity_bytes * 0.95),
                storage_counters.get("used_bytes", 0) + random.randint(1_000_000_000, 10_000_000_000)
            )

        used_bytes = storage_counters.get("used_bytes", 0)

        # IOPS metrics
        metrics.extend([
            self._create_gauge_metric("storage.iops.read", "{operation}/s", [{
                "timeUnixNano": current_time_ns,
                "asDouble": float(read_iops),
            }]),
            self._create_gauge_metric("storage.iops.write", "{operation}/s", [{
                "timeUnixNano": current_time_ns,
                "asDouble": float(write_iops),
            }]),
            self._create_gauge_metric("storage.iops.total", "{operation}/s", [{
                "timeUnixNano": current_time_ns,
                "asDouble": float(read_iops + write_iops),
            }]),
        ])

        # Throughput metrics
        read_throughput = read_iops * random.randint(4096, 65536)
        write_throughput = write_iops * random.randint(4096, 65536)

        metrics.extend([
            self._create_gauge_metric("storage.throughput.read", "By/s", [{
                "timeUnixNano": current_time_ns,
                "asDouble": float(read_throughput),
            }]),
            self._create_gauge_metric("storage.throughput.write", "By/s", [{
                "timeUnixNano": current_time_ns,
                "asDouble": float(write_throughput),
            }]),
        ])

        # Cumulative I/O bytes
        metrics.extend([
            self._create_sum_metric("storage.io.bytes", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(storage_counters["read_bytes"]),
                "attributes": [{"key": "disk.io.direction", "value": {"stringValue": "read"}}],
            }]),
            self._create_sum_metric("storage.io.bytes", "By", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(storage_counters["write_bytes"]),
                "attributes": [{"key": "disk.io.direction", "value": {"stringValue": "write"}}],
            }]),
        ])

        # Cumulative I/O operations
        metrics.extend([
            self._create_sum_metric("storage.io.operations", "{operation}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(storage_counters["read_ops"]),
                "attributes": [{"key": "disk.io.direction", "value": {"stringValue": "read"}}],
            }]),
            self._create_sum_metric("storage.io.operations", "{operation}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(storage_counters["write_ops"]),
                "attributes": [{"key": "disk.io.direction", "value": {"stringValue": "write"}}],
            }]),
        ])

        # Latency metrics
        read_latency = random.uniform(*typical_latency) * latency_multiplier
        write_latency = random.uniform(*typical_latency) * latency_multiplier * 1.2

        metrics.extend([
            self._create_gauge_metric("storage.latency.read", "ms", [{
                "timeUnixNano": current_time_ns,
                "asDouble": read_latency,
            }]),
            self._create_gauge_metric("storage.latency.write", "ms", [{
                "timeUnixNano": current_time_ns,
                "asDouble": write_latency,
            }]),
            self._create_gauge_metric("storage.latency.avg", "ms", [{
                "timeUnixNano": current_time_ns,
                "asDouble": (read_latency + write_latency) / 2,
            }]),
        ])

        # Capacity metrics
        metrics.extend([
            self._create_gauge_metric("storage.capacity.total", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(capacity_bytes),
            }]),
            self._create_gauge_metric("storage.capacity.used", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(used_bytes),
            }]),
            self._create_gauge_metric("storage.capacity.free", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(capacity_bytes - used_bytes),
            }]),
            self._create_gauge_metric("storage.capacity.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": used_bytes / capacity_bytes if capacity_bytes > 0 else 0,
            }]),
        ])

        # Queue depth
        queue_depth = random.randint(1, 64)
        if effect and effect.get("effect") == "storage_latency_spike":
            queue_depth = random.randint(64, 256)

        metrics.append(self._create_gauge_metric("storage.queue.depth", "{request}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(queue_depth),
        }]))

        # Error metrics
        error_count = 0
        if error_increase > 0 or random.random() < 0.01:
            error_count = random.randint(1, 10) if error_increase > 0 else random.randint(0, 1)

        metrics.append(self._create_gauge_metric("storage.errors", "{error}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(error_count),
        }]))

        # Health status
        health_status = 1  # 1 = healthy
        if effect:
            if effect.get("effect") in ["storage_degraded", "storage_errors"]:
                health_status = 0

        metrics.append(self._create_gauge_metric("storage.health", "1", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(health_status),
        }]))

        # Per-volume metrics
        for volume in storage_info.get("volumes", []):
            volume_counters = self._counters.get(f"{storage.name}:{volume}", {})

            # Update volume counters
            vol_read_ops = int(read_iops / len(storage_info.get("volumes", [1])))
            vol_write_ops = int(write_iops / len(storage_info.get("volumes", [1])))

            volume_counters["read_ops"] = volume_counters.get("read_ops", 0) + vol_read_ops
            volume_counters["write_ops"] = volume_counters.get("write_ops", 0) + vol_write_ops

            vol_attrs = [{"key": "storage.volume.name", "value": {"stringValue": volume}}]

            # Volume IOPS
            metrics.append({
                "name": "storage.volume.iops",
                "unit": "{operation}/s",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asDouble": float(vol_read_ops + vol_write_ops),
                        "attributes": vol_attrs,
                    }],
                },
            })

            # Volume latency
            metrics.append({
                "name": "storage.volume.latency",
                "unit": "ms",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asDouble": random.uniform(*typical_latency) * latency_multiplier,
                        "attributes": vol_attrs,
                    }],
                },
            })

        # Protocol-specific metrics
        if storage.type.lower() in ["san", "iscsi"]:
            # FC/iSCSI specific
            metrics.extend([
                self._create_gauge_metric("storage.fc.port.rx_frames", "{frame}/s", [{
                    "timeUnixNano": current_time_ns,
                    "asDouble": random.uniform(10000, 100000),
                }]),
                self._create_gauge_metric("storage.fc.port.tx_frames", "{frame}/s", [{
                    "timeUnixNano": current_time_ns,
                    "asDouble": random.uniform(10000, 100000),
                }]),
            ])

        return metrics

    # _create_gauge_metric, _create_sum_metric, and _format_attributes
    # are now inherited from BaseInfrastructureGenerator
