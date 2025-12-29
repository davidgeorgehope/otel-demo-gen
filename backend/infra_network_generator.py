"""
Network device telemetry generator following OpenTelemetry hw.network.* semantic conventions.
Generates metrics for switches, routers, and firewalls.

Reference: https://opentelemetry.io/docs/specs/semconv/hardware/network/
"""
import secrets
import random
import time
from typing import Dict, List, Any, Optional

from config_schema import ScenarioConfig, NetworkDevice
from correlation_manager import CorrelationManager
from base_infra_generator import BaseInfrastructureGenerator


class NetworkDeviceGenerator(BaseInfrastructureGenerator):
    """
    Generates network device metrics following OTel hw.network.* semantic conventions.
    Supports switches, routers, and firewalls with realistic interface metrics.
    """

    # Vendor-specific interface naming patterns
    VENDOR_INTERFACE_PATTERNS = {
        "cisco": {
            "switch": ["Gi0/{}", "Gi1/{}", "Te0/{}", "Fa0/{}"],
            "router": ["Gi0/0/{}", "Se0/0/{}", "Fa0/0/{}"],
            "firewall": ["Ethernet0/{}", "Management0/{}"],
        },
        "juniper": {
            "switch": ["ge-0/0/{}", "xe-0/0/{}", "et-0/0/{}"],
            "router": ["ge-0/0/{}", "xe-0/0/{}", "so-0/0/{}"],
            "firewall": ["ge-0/0/{}", "reth{}"],
        },
        "arista": {
            "switch": ["Ethernet{}", "Management1"],
            "router": ["Ethernet{}", "Loopback0"],
            "firewall": ["Ethernet{}"],
        },
        "palo_alto": {
            "firewall": ["ethernet1/{}", "ethernet2/{}", "management"],
        },
        "fortinet": {
            "firewall": ["port{}", "wan1", "wan2", "dmz"],
        },
    }

    # Link speeds by interface type (in bytes/sec)
    LINK_SPEEDS = {
        "Gi": 125_000_000,      # 1 Gbps
        "Te": 1_250_000_000,    # 10 Gbps
        "Fa": 12_500_000,       # 100 Mbps
        "ge-": 125_000_000,     # 1 Gbps
        "xe-": 1_250_000_000,   # 10 Gbps
        "et-": 12_500_000_000,  # 100 Gbps
        "Ethernet": 1_250_000_000,  # Default 10G for Arista
        "ethernet": 125_000_000,    # 1G for firewalls
        "port": 125_000_000,
        "wan": 125_000_000,
        "default": 125_000_000,
    }

    def __init__(self, config: ScenarioConfig, correlation_manager: Optional[CorrelationManager] = None):
        super().__init__(config, correlation_manager)

        # Get network devices from infrastructure config
        self.devices: List[NetworkDevice] = []
        if config.infrastructure and config.infrastructure.network_devices:
            self.devices = config.infrastructure.network_devices

        self._device_data = self._initialize_device_data()
        self._counters = self._initialize_counters()

    def _initialize_device_data(self) -> Dict[str, Dict[str, Any]]:
        """Initialize static device data for consistency."""
        device_data = {}

        for device in self.devices:
            vendor = (device.vendor or "cisco").lower()
            device_type = device.type.lower()

            # Generate interfaces if not specified
            interfaces = device.interfaces
            if not interfaces:
                patterns = self.VENDOR_INTERFACE_PATTERNS.get(vendor, {}).get(
                    device_type,
                    self.VENDOR_INTERFACE_PATTERNS.get("cisco", {}).get("switch", ["Gi0/{}"])
                )
                interfaces = [
                    pattern.format(i) for pattern in patterns[:2] for i in range(1, 5)
                ]

            # Generate device identifiers
            hw_id = f"{device.type}_{device.name}_{secrets.token_hex(4)}"
            serial_number = f"{vendor.upper()[:3]}{secrets.token_hex(6).upper()}"

            device_data[device.name] = {
                "hw_id": hw_id,
                "serial_number": serial_number,
                "vendor": vendor,
                "model": device.model or f"{vendor.upper()}-{device_type.upper()}-{random.choice(['2960', '3850', 'SRX340', 'PA-440'])}",
                "interfaces": interfaces,
                "connected_services": device.connected_services,
                "management_ip": f"10.{random.randint(1, 10)}.{random.randint(1, 254)}.{random.randint(1, 254)}",
                "firmware_version": f"{random.randint(15, 17)}.{random.randint(1, 9)}.{random.randint(1, 5)}",
            }

        return device_data

    def _initialize_counters(self) -> Dict[str, Dict[str, Dict[str, int]]]:
        """Initialize counters for each interface on each device."""
        counters = {}

        for device in self.devices:
            device_info = self._device_data.get(device.name, {})
            interfaces = device_info.get("interfaces", [])

            counters[device.name] = {}
            for iface in interfaces:
                counters[device.name][iface] = {
                    "rx_bytes": random.randint(1_000_000_000, 100_000_000_000),
                    "tx_bytes": random.randint(1_000_000_000, 100_000_000_000),
                    "rx_packets": random.randint(10_000_000, 500_000_000),
                    "tx_packets": random.randint(10_000_000, 500_000_000),
                    "errors": random.randint(0, 100),
                    "drops": random.randint(0, 50),
                    "link_up": 1,  # 1 = up, 0 = down
                }

        return counters

    def _get_link_speed(self, interface_name: str) -> int:
        """Get link speed in bytes/sec based on interface naming."""
        for prefix, speed in self.LINK_SPEEDS.items():
            if interface_name.startswith(prefix):
                return speed
        return self.LINK_SPEEDS["default"]

    def generate_resource_attributes(self, device: NetworkDevice) -> Dict[str, Any]:
        """Generate OTel resource attributes for a network device."""
        device_info = self._device_data.get(device.name, {})

        attrs = {
            # Hardware attributes (required)
            "hw.id": device_info.get("hw_id", f"{device.type}_{device.name}"),
            "hw.type": "network",
            "hw.name": device.name,

            # Hardware attributes (recommended)
            "hw.vendor": device_info.get("vendor", device.vendor or "unknown"),
            "hw.model": device_info.get("model", device.model or "unknown"),
            "hw.serial_number": device_info.get("serial_number", ""),

            # Device-specific attributes
            "device.type": device.type,
            "device.management_ip": device_info.get("management_ip", ""),
            "device.firmware_version": device_info.get("firmware_version", ""),

            # Data stream for Elastic routing
            "data_stream.type": "metrics",
            "data_stream.dataset": "hardware.network",
            "data_stream.namespace": "default",
        }

        # Add correlation attributes if this device is affected by an incident
        if self.correlation_manager:
            correlation_attrs = self.correlation_manager.get_attributes_for_component(device.name)
            attrs.update(correlation_attrs)

        return attrs

    def generate_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics payload for all network devices (implements abstract method)."""
        return self.generate_network_metrics_payload()

    def generate_network_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics payload for all network devices."""
        if not self.devices:
            return {"resourceMetrics": []}

        resource_metrics = []
        current_time_ns = str(time.time_ns())

        for device in self.devices:
            device_info = self._device_data.get(device.name, {})
            device_counters = self._counters.get(device.name, {})

            # Check if device is affected by an incident
            effect = None
            if self.correlation_manager:
                effect = self.correlation_manager.get_effect_for_component(device.name)

            # Generate metrics for this device
            metrics = self._generate_device_metrics(
                current_time_ns, device, device_info, device_counters, effect
            )

            # Create resource with attributes
            resource_attrs = self._format_attributes(self.generate_resource_attributes(device))

            resource_metrics.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": self.SCHEMA_URL,
                },
                "scopeMetrics": [{
                    "scope": {
                        "name": "otel-demo-gen/network-device-receiver",
                        "version": "1.0.0",
                    },
                    "metrics": metrics,
                }],
            })

        return {"resourceMetrics": resource_metrics}

    def _generate_device_metrics(
        self,
        current_time_ns: str,
        device: NetworkDevice,
        device_info: Dict[str, Any],
        device_counters: Dict[str, Dict[str, int]],
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate metrics for a single network device."""
        metrics = []
        interfaces = device_info.get("interfaces", [])

        # Device-level metrics
        metrics.extend([
            # Device CPU utilization
            self._create_gauge_metric("hw.cpu.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(0.1, 0.6),
            }]),
            # Device memory utilization
            self._create_gauge_metric("hw.memory.utilization", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(0.2, 0.7),
            }]),
            # Device temperature
            self._create_gauge_metric("hw.temperature", "Cel", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(35.0, 55.0),
            }]),
            # Device status (1=ok, 0=degraded/failed)
            self._create_gauge_metric("hw.status", "1", [{
                "timeUnixNano": current_time_ns,
                "asInt": "1" if not effect else ("0" if effect.get("effect") == "unavailable" else "1"),
            }]),
        ])

        # Interface-level metrics
        for iface in interfaces:
            iface_counters = device_counters.get(iface, {})
            link_speed = self._get_link_speed(iface)

            # Update counters (simulate traffic)
            traffic_multiplier = 1.0
            error_multiplier = 1.0
            link_up = 1

            # Apply incident effects
            if effect:
                effect_type = effect.get("effect", "")
                params = effect.get("parameters", {})

                if effect_type == "interface_down":
                    affected_ifaces = params.get("interfaces", [])
                    if iface in affected_ifaces or not affected_ifaces:
                        link_up = 0
                        traffic_multiplier = 0.0
                elif effect_type == "high_errors":
                    error_multiplier = params.get("error_multiplier", 10.0)
                elif effect_type == "congestion":
                    traffic_multiplier = params.get("traffic_multiplier", 2.0)

            # Update byte counters
            rx_increment = int(random.randint(100_000, 10_000_000) * traffic_multiplier)
            tx_increment = int(random.randint(100_000, 10_000_000) * traffic_multiplier)
            iface_counters["rx_bytes"] = iface_counters.get("rx_bytes", 0) + rx_increment
            iface_counters["tx_bytes"] = iface_counters.get("tx_bytes", 0) + tx_increment

            # Update packet counters
            rx_packets = int(random.randint(1000, 50000) * traffic_multiplier)
            tx_packets = int(random.randint(1000, 50000) * traffic_multiplier)
            iface_counters["rx_packets"] = iface_counters.get("rx_packets", 0) + rx_packets
            iface_counters["tx_packets"] = iface_counters.get("tx_packets", 0) + tx_packets

            # Update error counters
            if random.random() < 0.1 * error_multiplier:
                iface_counters["errors"] = iface_counters.get("errors", 0) + int(random.randint(1, 5) * error_multiplier)
            if random.random() < 0.05 * error_multiplier:
                iface_counters["drops"] = iface_counters.get("drops", 0) + int(random.randint(1, 3) * error_multiplier)

            iface_counters["link_up"] = link_up

            # Calculate utilization
            utilization = min(1.0, (rx_increment + tx_increment) / link_speed) if link_up else 0.0

            # Interface attributes for metric data points
            iface_attrs = [
                {"key": "hw.name", "value": {"stringValue": iface}},
                {"key": "network.interface.name", "value": {"stringValue": iface}},
            ]

            # hw.network.io - bytes received/transmitted
            metrics.extend([
                {
                    "name": "hw.network.io",
                    "unit": "By",
                    "sum": {
                        "isMonotonic": True,
                        "aggregationTemporality": 2,
                        "dataPoints": [{
                            "timeUnixNano": current_time_ns,
                            "asInt": str(iface_counters["rx_bytes"]),
                            "attributes": iface_attrs + [
                                {"key": "network.io.direction", "value": {"stringValue": "receive"}},
                            ],
                        }],
                    },
                },
                {
                    "name": "hw.network.io",
                    "unit": "By",
                    "sum": {
                        "isMonotonic": True,
                        "aggregationTemporality": 2,
                        "dataPoints": [{
                            "timeUnixNano": current_time_ns,
                            "asInt": str(iface_counters["tx_bytes"]),
                            "attributes": iface_attrs + [
                                {"key": "network.io.direction", "value": {"stringValue": "transmit"}},
                            ],
                        }],
                    },
                },
            ])

            # hw.network.packets - packets received/transmitted
            metrics.extend([
                {
                    "name": "hw.network.packets",
                    "unit": "{packet}",
                    "sum": {
                        "isMonotonic": True,
                        "aggregationTemporality": 2,
                        "dataPoints": [{
                            "timeUnixNano": current_time_ns,
                            "asInt": str(iface_counters["rx_packets"]),
                            "attributes": iface_attrs + [
                                {"key": "network.io.direction", "value": {"stringValue": "receive"}},
                            ],
                        }],
                    },
                },
                {
                    "name": "hw.network.packets",
                    "unit": "{packet}",
                    "sum": {
                        "isMonotonic": True,
                        "aggregationTemporality": 2,
                        "dataPoints": [{
                            "timeUnixNano": current_time_ns,
                            "asInt": str(iface_counters["tx_packets"]),
                            "attributes": iface_attrs + [
                                {"key": "network.io.direction", "value": {"stringValue": "transmit"}},
                            ],
                        }],
                    },
                },
            ])

            # hw.network.up - link status
            metrics.append({
                "name": "hw.network.up",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(link_up),
                        "attributes": iface_attrs,
                    }],
                },
            })

            # hw.network.bandwidth.limit - link speed
            metrics.append({
                "name": "hw.network.bandwidth.limit",
                "unit": "By/s",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(link_speed),
                        "attributes": iface_attrs,
                    }],
                },
            })

            # hw.network.bandwidth.utilization - bandwidth usage fraction
            metrics.append({
                "name": "hw.network.bandwidth.utilization",
                "unit": "1",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asDouble": utilization,
                        "attributes": iface_attrs,
                    }],
                },
            })

            # hw.errors - error count
            metrics.append({
                "name": "hw.errors",
                "unit": "{error}",
                "sum": {
                    "isMonotonic": True,
                    "aggregationTemporality": 2,
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(iface_counters.get("errors", 0)),
                        "attributes": iface_attrs + [
                            {"key": "error.type", "value": {"stringValue": "crc"}},
                        ],
                    }],
                },
            })

            # Packet drops
            metrics.append({
                "name": "hw.network.drops",
                "unit": "{packet}",
                "sum": {
                    "isMonotonic": True,
                    "aggregationTemporality": 2,
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(iface_counters.get("drops", 0)),
                        "attributes": iface_attrs,
                    }],
                },
            })

        # Firewall-specific metrics
        if device.type == "firewall":
            metrics.extend(self._generate_firewall_metrics(current_time_ns, device, effect))

        # Router-specific metrics
        if device.type == "router":
            metrics.extend(self._generate_router_metrics(current_time_ns, device, effect))

        return metrics

    def _generate_firewall_metrics(
        self,
        current_time_ns: str,
        device: NetworkDevice,
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate firewall-specific metrics."""
        metrics = []

        # Active connections
        metrics.append(self._create_gauge_metric("firewall.connections.active", "{connection}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(random.randint(1000, 50000)),
        }]))

        # Connections per second
        metrics.append(self._create_gauge_metric("firewall.connections.rate", "{connection}/s", [{
            "timeUnixNano": current_time_ns,
            "asDouble": random.uniform(100, 5000),
        }]))

        # Blocked connections (higher if blocking scenario)
        blocked_rate = random.randint(10, 100)
        if effect and effect.get("effect") == "firewall_rule_block":
            blocked_rate *= 10

        metrics.append(self._create_gauge_metric("firewall.connections.blocked", "{connection}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(blocked_rate),
        }]))

        # Threat detection count
        metrics.append(self._create_gauge_metric("firewall.threats.detected", "{threat}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(random.randint(0, 10)),
        }]))

        # Session table utilization
        metrics.append(self._create_gauge_metric("firewall.session_table.utilization", "1", [{
            "timeUnixNano": current_time_ns,
            "asDouble": random.uniform(0.1, 0.7),
        }]))

        return metrics

    def _generate_router_metrics(
        self,
        current_time_ns: str,
        device: NetworkDevice,
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate router-specific metrics."""
        metrics = []

        # BGP peer count
        bgp_peers_up = random.randint(2, 8)
        if effect and effect.get("effect") == "router_bgp_flap":
            bgp_peers_up = max(0, bgp_peers_up - random.randint(1, 3))

        metrics.append(self._create_gauge_metric("router.bgp.peers.up", "{peer}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(bgp_peers_up),
        }]))

        # Routing table size
        metrics.append(self._create_gauge_metric("router.routes.count", "{route}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(random.randint(10000, 100000)),
        }]))

        # Packets routed per second
        metrics.append(self._create_gauge_metric("router.packets.rate", "{packet}/s", [{
            "timeUnixNano": current_time_ns,
            "asDouble": random.uniform(100000, 1000000),
        }]))

        # Route convergence time (ms)
        metrics.append(self._create_gauge_metric("router.convergence.time", "ms", [{
            "timeUnixNano": current_time_ns,
            "asDouble": random.uniform(50, 500),
        }]))

        return metrics

    def generate_network_logs_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP logs payload for network device events."""
        if not self.devices:
            return {"resourceLogs": []}

        resource_logs = []
        current_time_ns = str(time.time_ns())

        for device in self.devices:
            # Only generate logs occasionally
            if random.random() > 0.3:
                continue

            device_info = self._device_data.get(device.name, {})
            log_records = self._generate_device_logs(current_time_ns, device, device_info)

            if not log_records:
                continue

            resource_attrs = self._format_attributes(self.generate_resource_attributes(device))

            resource_logs.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": self.SCHEMA_URL,
                },
                "scopeLogs": [{
                    "scope": {
                        "name": "otel-demo-gen/network-device-logs",
                        "version": "1.0.0",
                    },
                    "logRecords": log_records,
                }],
            })

        return {"resourceLogs": resource_logs}

    def _generate_device_logs(
        self,
        current_time_ns: str,
        device: NetworkDevice,
        device_info: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate log records for a network device."""
        logs = []
        interfaces = device_info.get("interfaces", [])

        # Check for incidents affecting this device
        effect = None
        if self.correlation_manager:
            effect = self.correlation_manager.get_effect_for_component(device.name)

        # Generate event logs based on device type and state
        log_templates = [
            {"level": "INFO", "message": f"Interface {{iface}} link state UP", "severity": 9},
            {"level": "INFO", "message": f"SNMP trap sent to management station", "severity": 9},
            {"level": "WARN", "message": f"High CPU utilization detected: {{cpu}}%", "severity": 13},
        ]

        if effect:
            effect_type = effect.get("effect", "")
            if effect_type == "interface_down":
                iface = random.choice(interfaces) if interfaces else "Gi0/1"
                logs.append(self._create_log_record(
                    current_time_ns,
                    "ERROR",
                    f"Interface {iface} link state DOWN - carrier lost",
                    17,
                    effect.get("incident_id"),
                ))
            elif effect_type == "high_errors":
                iface = random.choice(interfaces) if interfaces else "Gi0/1"
                logs.append(self._create_log_record(
                    current_time_ns,
                    "WARN",
                    f"High error rate detected on {iface}: CRC errors exceeding threshold",
                    13,
                    effect.get("incident_id"),
                ))

        # Random normal logs
        if random.random() < 0.5 and not effect:
            template = random.choice(log_templates)
            message = template["message"]
            if "{iface}" in message:
                message = message.replace("{iface}", random.choice(interfaces) if interfaces else "Gi0/1")
            if "{cpu}" in message:
                message = message.replace("{cpu}", str(random.randint(60, 90)))

            logs.append(self._create_log_record(
                current_time_ns,
                template["level"],
                message,
                template["severity"],
            ))

        return logs

    def _create_log_record(
        self,
        time_ns: str,
        level: str,
        message: str,
        severity_number: int,
        incident_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an OTLP log record."""
        record = {
            "timeUnixNano": time_ns,
            "observedTimeUnixNano": time_ns,
            "severityText": level,
            "severityNumber": severity_number,
            "body": {"stringValue": message},
            "attributes": [],
        }

        if incident_id:
            record["attributes"].append({
                "key": "incident.id",
                "value": {"stringValue": incident_id},
            })

        return record

    # _create_gauge_metric, _create_sum_metric, and _format_attributes
    # are now inherited from BaseInfrastructureGenerator
