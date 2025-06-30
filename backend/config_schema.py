from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

# Pydantic models for API requests
class GenerateConfigRequest(BaseModel):
    prompt: str

class StartDemoRequest(BaseModel):
    yaml_config: str
    otlp_endpoint: str
    api_key: Optional[str] = None

# --- New Models for Enhanced Realism ---

class LatencyConfig(BaseModel):
    """Defines latency characteristics for an operation or dependency."""
    min_ms: int = Field(..., description="Minimum latency in milliseconds.")
    max_ms: int = Field(..., description="Maximum latency in milliseconds.")
    probability: float = Field(1.0, description="Probability of this latency occurring (0.0 to 1.0).")

class Operation(BaseModel):
    """Defines a specific business operation within a service."""
    name: str = Field(..., description="A friendly name for the operation (e.g., 'ProcessPayment').")
    span_name: str = Field(..., description="The desired name for the root span (e.g., 'POST /payments').")
    description: Optional[str] = None
    db_queries: Optional[List[str]] = Field(default_factory=list, description="List of realistic DB queries for this operation.")
    latency: Optional[LatencyConfig] = None

# --- Updated YAML Configuration Models ---

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

class Service(BaseModel):
    name: str
    language: Optional[str] = 'python'
    role: Optional[str] = None
    depends_on: List[AnyDependency] = Field(default_factory=list)
    operations: Optional[List[Operation]] = Field(default_factory=list, description="Specific business operations for this service.")

class Database(BaseModel):
    name: str
    type: str

class MessageQueue(BaseModel):
    name: str
    type: str

class Telemetry(BaseModel):
    trace_rate: int = 1
    error_rate: float = 0.05
    metrics_interval: int = 10
    include_logs: bool = True

class ScenarioConfig(BaseModel):
    services: List[Service]
    databases: Optional[List[Database]] = []
    message_queues: Optional[List[MessageQueue]] = []
    telemetry: Telemetry 