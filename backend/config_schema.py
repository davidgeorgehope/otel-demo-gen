from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

# Pydantic models for API requests
class GenerateConfigRequest(BaseModel):
    prompt: str

class StartDemoRequest(BaseModel):
    yaml_config: str
    otlp_endpoint: str
    api_key: Optional[str] = None

# Pydantic models for parsing the YAML configuration
class ServiceDependency(BaseModel):
    service: str
    protocol: Optional[str] = None
    via: Optional[str] = None

class DbDependency(BaseModel):
    db: str

class CacheDependency(BaseModel):
    cache: str

class QueueDependency(BaseModel):
    queue: str

AnyDependency = Union[ServiceDependency, DbDependency, CacheDependency, QueueDependency]

class Service(BaseModel):
    name: str
    language: Optional[str] = 'python'
    role: Optional[str] = None
    depends_on: List[AnyDependency] = []

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