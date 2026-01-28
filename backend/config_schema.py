from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, model_validator, field_validator
from datetime import datetime

# Pydantic models for API requests
class GenerateConfigRequest(BaseModel):
    prompt: str

class StartDemoRequest(BaseModel):
    config: Dict[str, Any]
    otlp_endpoint: str
    api_key: Optional[str] = None
    auth_type: str = Field(default="ApiKey", description="Authentication type: 'Bearer' or 'ApiKey'")

# --- New Models for Enhanced Realism ---

class LatencyConfig(BaseModel):
    """Defines latency characteristics for an operation or dependency."""
    min_ms: int = Field(..., description="Minimum latency in milliseconds.", ge=0)
    max_ms: int = Field(..., description="Maximum latency in milliseconds.", ge=0)
    probability: float = Field(1.0, description="Probability of this latency occurring (0.0 to 1.0).", ge=0.0, le=1.0)

    @model_validator(mode='after')
    def validate_min_max(self) -> 'LatencyConfig':
        """Ensure min_ms <= max_ms, swapping if necessary."""
        if self.min_ms > self.max_ms:
            self.min_ms, self.max_ms = self.max_ms, self.min_ms
        return self

class BusinessDataField(BaseModel):
    """Defines a business-relevant data field to be added to traces."""
    name: str = Field(..., description="The field name that will be added as a span attribute (e.g., 'cart_amount', 'user_id').")
    type: str = Field(..., description="Data type: 'string', 'number', 'integer', 'boolean', or 'enum'.")

    # For string fields
    pattern: Optional[str] = Field(None, description="Pattern for string generation (e.g., 'user_{random}', 'order_{uuid}').")

    # For number/integer fields
    min_value: Optional[float] = Field(None, description="Minimum value for numeric fields.")
    max_value: Optional[float] = Field(None, description="Maximum value for numeric fields.")

    # For enum fields
    values: Optional[List[str]] = Field(None, description="List of possible values for enum fields.")

    # For boolean fields (no additional config needed)
    description: Optional[str] = Field(None, description="Optional description of what this field represents.")

    @model_validator(mode='after')
    def validate_min_max(self) -> 'BusinessDataField':
        """Ensure min_value <= max_value for numeric fields, swapping if necessary."""
        if self.min_value is not None and self.max_value is not None:
            if self.min_value > self.max_value:
                self.min_value, self.max_value = self.max_value, self.min_value
        return self

class Operation(BaseModel):
    """Defines a specific business operation within a service."""
    name: str = Field(..., description="A friendly name for the operation (e.g., 'ProcessPayment').")
    span_name: str = Field(..., description="The desired name for the root span (e.g., 'POST /payments').")
    description: Optional[str] = None
    db_queries: Optional[List[str]] = Field(default_factory=list, description="List of realistic DB queries for this operation.")
    latency: Optional[LatencyConfig] = None
    business_data: Optional[List[BusinessDataField]] = Field(default_factory=list, description="Business-relevant data fields to add to traces.")

# --- Updated Configuration Models ---

class ServiceDependency(BaseModel):
    service: str
    protocol: Optional[str] = None
    via: Optional[str] = None
    example_queries: Optional[List[str]] = Field(default_factory=list)
    latency: Optional[LatencyConfig] = None


class DbDependency(BaseModel):
    db: str
    example_queries: Optional[List[str]] = Field(default_factory=list)
    latency: Optional[LatencyConfig] = None

class CacheDependency(BaseModel):
    cache: str
    example_queries: Optional[List[str]] = Field(default_factory=list)
    latency: Optional[LatencyConfig] = None

class QueueDependency(BaseModel):
    queue: str

AnyDependency = Union[ServiceDependency, DbDependency, CacheDependency, QueueDependency]

class LogSample(BaseModel):
    """Sample log message for realistic log generation."""
    level: str = Field(..., description="Log level: INFO, WARN, ERROR, DEBUG")
    message: str = Field(..., description="Log message template with placeholders")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context for this log type")

class Service(BaseModel):
    name: str
    language: Optional[str] = 'python'
    role: Optional[str] = None
    depends_on: List[AnyDependency] = Field(default_factory=list)
    operations: Optional[List[Operation]] = Field(default_factory=list, description="Specific business operations for this service.")
    log_samples: Optional[List[LogSample]] = Field(default_factory=list, description="Sample log messages for realistic log generation")

class Database(BaseModel):
    name: str
    type: str

class MessageQueue(BaseModel):
    name: str
    type: str

# --- Infrastructure Models ---

class NetworkDevice(BaseModel):
    """Network device configuration (switches, routers, firewalls)."""
    name: str = Field(..., description="Unique device name (e.g., 'core-switch-01')")
    type: str = Field(..., description="Device type: 'switch', 'router', 'firewall'")
    vendor: Optional[str] = Field(None, description="Vendor: 'cisco', 'juniper', 'palo_alto', 'arista', 'fortinet'")
    model: Optional[str] = Field(None, description="Device model")
    interfaces: List[str] = Field(default_factory=list, description="Interface names (e.g., 'Gi0/1', 'eth0')")
    connected_services: List[str] = Field(default_factory=list, description="Services reachable through this device")

class VirtualMachine(BaseModel):
    """VM/Hypervisor configuration."""
    name: str = Field(..., description="VM name (e.g., 'vm-app-01')")
    hypervisor_type: str = Field(..., description="Hypervisor: 'esxi', 'hyperv', 'kvm', 'proxmox'")
    host_name: str = Field(..., description="Physical host running this VM")
    vcpus: int = Field(4, description="Number of virtual CPUs")
    memory_gb: int = Field(16, description="Memory allocation in GB")
    disk_gb: int = Field(100, description="Disk allocation in GB")
    hosted_services: List[str] = Field(default_factory=list, description="Services running on this VM")

class LoadBalancer(BaseModel):
    """Load balancer configuration."""
    name: str = Field(..., description="Load balancer name (e.g., 'alb-frontend')")
    type: str = Field(..., description="Type: 'f5', 'haproxy', 'nginx', 'aws_alb', 'azure_lb', 'gcp_lb'")
    backend_services: List[str] = Field(default_factory=list, description="Backend services being load balanced")
    virtual_servers: List[str] = Field(default_factory=list, description="Virtual server names/IPs")
    health_check_path: Optional[str] = Field("/health", description="Health check endpoint")

class StorageSystem(BaseModel):
    """Storage system configuration."""
    name: str = Field(..., description="Storage system name (e.g., 'san-primary')")
    type: str = Field(..., description="Type: 'san', 'nas', 's3', 'azure_blob', 'nfs', 'iscsi'")
    vendor: Optional[str] = Field(None, description="Vendor: 'netapp', 'dell_emc', 'pure', 'hpe'")
    capacity_tb: float = Field(10.0, description="Total capacity in TB")
    connected_services: List[str] = Field(default_factory=list, description="Services using this storage")

class InfrastructureConfig(BaseModel):
    """Complete infrastructure topology configuration."""
    network_devices: List[NetworkDevice] = Field(default_factory=list)
    virtual_machines: List[VirtualMachine] = Field(default_factory=list)
    load_balancers: List[LoadBalancer] = Field(default_factory=list)
    storage_systems: List[StorageSystem] = Field(default_factory=list)

# --- Correlation Models ---

class CascadeStage(BaseModel):
    """Individual stage in a cascading outage."""
    component: str = Field(..., description="Component affected at this stage")
    effect: str = Field(..., description="Effect type: 'latency_spike', 'error_rate', 'unavailable', etc.")
    delay_ms: int = Field(0, description="Delay from previous stage in milliseconds")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Effect-specific parameters")

class IncidentCorrelation(BaseModel):
    """Correlation context for unified incident tracking across all signals."""
    incident_id: str = Field(..., description="Unique incident identifier (e.g., 'INC-20241226-A1B2C3')")
    root_cause_type: str = Field(..., description="Origin: 'infrastructure', 'application', 'external'")
    root_cause_component: str = Field(..., description="Specific component causing the issue")
    affected_components: List[str] = Field(default_factory=list, description="All affected components")
    cascade_path: List[str] = Field(default_factory=list, description="Ordered failure propagation path")
    severity: str = Field("medium", description="Severity: 'critical', 'high', 'medium', 'low'")
    description: Optional[str] = Field(None, description="Human-readable incident description")

class CascadingOutageConfig(BaseModel):
    """Configuration for cascading outage simulation."""
    name: str = Field(..., description="Outage scenario name")
    description: str = Field(..., description="What this outage simulates")
    origin: str = Field(..., description="Origin layer: 'infrastructure' or 'application'")
    trigger_component: str = Field(..., description="Component that triggers the cascade")
    cascade_chain: List[CascadeStage] = Field(..., description="Ordered cascade stages")
    delay_between_stages_ms: int = Field(5000, description="Default delay between stages")

class Telemetry(BaseModel):
    trace_rate: int = 1
    error_rate: float = 0.05
    metrics_interval: int = 10
    include_logs: bool = True

class ScenarioConfig(BaseModel):
    title: Optional[str] = Field(None, description="Short summary title of the scenario (max 5-7 words)")
    cloud_platform: Optional[str] = Field(
        None,
        description="K8s platform: 'aws_eks', 'azure_aks', 'gcp_gke', 'openshift', or 'on_prem'. If not specified, randomly selected."
    )
    services: List[Service]
    databases: Optional[List[Database]] = []
    message_queues: Optional[List[MessageQueue]] = []
    infrastructure: Optional[InfrastructureConfig] = Field(None, description="Infrastructure topology configuration")
    telemetry: Telemetry

    @field_validator('services')
    @classmethod
    def services_not_empty(cls, v):
        """Ensure at least one service is defined."""
        if not v:
            raise ValueError('At least one service is required')
        return v

# --- Scenario Simulation Models ---

class ScenarioParameter(BaseModel):
    """Individual parameter for a scenario modification."""
    key: str = Field(..., description="Parameter name (e.g., 'latency_multiplier', 'error_rate')")
    value: Any = Field(..., description="Parameter value")
    unit: Optional[str] = Field(None, description="Optional unit for the parameter (e.g., 'ms', '%')")

class ContextualPattern(BaseModel):
    """Defines patterns for injecting realistic context into failures."""
    attribute_name: str = Field(..., description="Span/log attribute name (e.g., 'user.id', 'cloud.region')")
    failure_values: List[str] = Field(..., description="Values associated with failures (e.g., ['user_premium_12345', 'user_enterprise_67890'])")
    normal_values: List[str] = Field(..., description="Values for normal operations")
    description: str = Field(..., description="Human-readable description of this pattern")

class ScenarioModification(BaseModel):
    """Defines how to modify telemetry generation for a specific scenario."""
    type: str = Field(..., description="Type of modification: 'latency_spike', 'error_rate', 'service_unavailable', etc.")
    target_services: List[str] = Field(..., description="Which services to affect")
    target_operations: Optional[List[str]] = Field(default_factory=list, description="Specific operations to target (empty = all)")
    parameters: List[ScenarioParameter] = Field(..., description="Parameters controlling the modification")
    contextual_patterns: Optional[List[ContextualPattern]] = Field(default_factory=list, description="Patterns for realistic failure context")
    ramp_up_seconds: Optional[int] = Field(0, description="Seconds to gradually apply the scenario")
    ramp_down_seconds: Optional[int] = Field(0, description="Seconds to gradually remove the scenario")

class ScenarioRequest(BaseModel):
    """Request to generate or apply a scenario."""
    description: str = Field(..., description="Natural language description of the scenario")
    target_services: Optional[List[str]] = Field(default_factory=list, description="Specific services to target (empty = auto-detect)")
    severity: str = Field("medium", description="Scenario severity: 'low', 'medium', 'high'")
    duration_minutes: Optional[int] = Field(None, description="How long to run the scenario (None = until manually stopped)")

class ActiveScenario(BaseModel):
    """Represents an active scenario affecting a job."""
    id: str = Field(..., description="Unique scenario ID")
    job_id: str = Field(..., description="Job this scenario is applied to")
    description: str = Field(..., description="Human-readable description")
    modification: ScenarioModification = Field(..., description="The actual modification being applied")
    started_at: datetime = Field(default_factory=datetime.now, description="When the scenario started")
    ends_at: Optional[datetime] = Field(None, description="When the scenario will automatically stop")
    status: str = Field("active", description="Status: 'active', 'ramping_up', 'ramping_down', 'stopped'")

class ScenarioTemplate(BaseModel):
    """Pre-configured scenario template for quick activation."""
    name: str = Field(..., description="Template name")
    description: str = Field(..., description="What this scenario simulates")
    category: str = Field(..., description="Category: 'infrastructure', 'application', 'security', 'cascading'")
    modification: ScenarioModification = Field(..., description="The modification to apply")
    default_duration_minutes: Optional[int] = Field(None, description="Default duration for this scenario")

class ScenarioGenerationRequest(BaseModel):
    """Request for LLM to generate a scenario from natural language."""
    description: str = Field(..., description="Natural language description of the outage/issue")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context about the current job/services")

class ScenarioApplyRequest(BaseModel):
    """Request to apply a scenario to a running job."""
    scenario: Optional[ScenarioModification] = Field(None, description="Specific scenario modification to apply")
    template_name: Optional[str] = Field(None, description="Name of template to apply")
    duration_minutes: Optional[int] = Field(None, description="How long to run (overrides template default)")
    description: Optional[str] = Field(None, description="Custom description for this scenario instance")

# --- Cascading Outage Request Models ---

class CascadingOutageRequest(BaseModel):
    """Request to start a cascading outage simulation."""
    outage_config: Optional[CascadingOutageConfig] = Field(None, description="Custom cascading outage configuration")
    template_name: Optional[str] = Field(None, description="Name of predefined cascade template")
    description: Optional[str] = Field(None, description="Natural language description for LLM to generate cascade")
    duration_minutes: Optional[int] = Field(None, description="How long to run the cascade")

class ActiveIncident(BaseModel):
    """Represents an active correlated incident across a job."""
    incident_id: str = Field(..., description="Unique incident ID")
    job_id: str = Field(..., description="Job this incident affects")
    correlation: IncidentCorrelation = Field(..., description="Correlation context")
    outage_config: CascadingOutageConfig = Field(..., description="The cascade configuration")
    started_at: datetime = Field(default_factory=datetime.now)
    current_stage: int = Field(0, description="Current cascade stage index")
    status: str = Field("active", description="Status: 'active', 'cascading', 'recovering', 'resolved'")
