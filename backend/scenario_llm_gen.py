"""
LLM-powered scenario generation for outage simulation.
Converts natural language descriptions into structured scenario modifications.
"""

import os
import json
from typing import Dict, List, Any, Optional
from config_schema import ScenarioModification, ScenarioParameter, ContextualPattern

def generate_scenario_from_description(description: str, context: Optional[Dict[str, Any]] = None) -> ScenarioModification:
    """Uses the configured Bedrock model to generate a scenario modification."""
    provider = os.getenv("LLM_PROVIDER", "bedrock").lower()

    if provider != "bedrock":
        raise ValueError(
            f"Unsupported LLM provider '{provider}'. Only 'bedrock' is supported; update LLM_PROVIDER to 'bedrock'."
        )

    return _generate_scenario_bedrock(description, context)

def _build_system_prompt(context: Optional[Dict[str, Any]] = None) -> str:
    """Build the system prompt for scenario generation."""

    base_prompt = """You are an expert in observability and incident simulation. Generate realistic outage scenarios for telemetry demonstration.

Your task is to convert natural language outage descriptions into structured scenario modifications that can be applied to running telemetry generators.

SCENARIO TYPES AVAILABLE:
- latency_spike: Increase response times
- error_rate: Increase error percentages
- service_unavailable: Make service return 503 errors
- memory_pressure: Simulate high memory usage
- cpu_spike: Simulate high CPU usage
- database_slow: Slow down database operations
- network_partition: Simulate network issues between services
- circuit_breaker_trip: Trigger circuit breaker patterns
- cache_miss_storm: Simulate cache failures
- thread_pool_exhaustion: Simulate resource exhaustion

RESPONSE FORMAT (JSON):
{
  "type": "scenario_type_from_above",
  "target_services": ["service1", "service2"],
  "target_operations": ["operation1"],
  "parameters": [
    {"key": "parameter_name", "value": parameter_value, "unit": "unit_if_applicable"}
  ],
  "contextual_patterns": [
    {
      "attribute_name": "user.id",
      "failure_values": ["user_premium_12345", "user_enterprise_67890"],
      "normal_values": ["user_standard_11111", "user_basic_22222", "user_trial_33333"],
      "description": "Premium users experiencing issues due to complex processing"
    }
  ],
  "ramp_up_seconds": 30,
  "ramp_down_seconds": 15
}

PARAMETER EXAMPLES:
- latency_spike: {"key": "multiplier", "value": 5.0}, {"key": "base_latency_ms", "value": 200}
- error_rate: {"key": "error_percentage", "value": 25.0, "unit": "%"}
- service_unavailable: {"key": "unavailable_percentage", "value": 100.0, "unit": "%"}
- database_slow: {"key": "query_delay_ms", "value": 2000, "unit": "ms"}
- cpu_spike: {"key": "cpu_percentage", "value": 95.0, "unit": "%"}

CONTEXTUAL PATTERN EXAMPLES:
- For user-related issues: {"attribute_name": "user.id", "failure_values": ["user_premium_001", "user_enterprise_999"], "normal_values": ["user_basic_123", "user_trial_456"]}
- For regional issues: {"attribute_name": "cloud.region", "failure_values": ["us-west-2", "eu-central-1"], "normal_values": ["us-east-1", "ap-southeast-1"]}
- For database shard issues: {"attribute_name": "db.shard", "failure_values": ["shard_03", "shard_07"], "normal_values": ["shard_01", "shard_02", "shard_04"]}
- For payment method issues: {"attribute_name": "payment.method", "failure_values": ["credit_card_amex", "paypal"], "normal_values": ["credit_card_visa", "bank_transfer"]}

GUIDELINES:
1. Infer target services from description context
2. Use realistic parameter values that demonstrate the issue clearly
3. Add appropriate ramp-up/ramp-down for gradual onset
4. Focus on common production issues that observability tools should detect
5. Ensure scenarios create clear signals in metrics, logs, and traces
6. ALWAYS include 1-2 contextual patterns that make failures realistic and traceable
7. Choose attribute names that make sense for the failure type (user IDs for premium user issues, regions for infrastructure problems, etc.)"""

    if context:
        services = context.get("services", [])
        if services:
            service_names = [s.get("name", "unknown") for s in services if isinstance(s, dict)]
            base_prompt += f"\n\nAVAILABLE SERVICES IN CURRENT JOB: {', '.join(service_names)}"

        operations = context.get("operations", [])
        if operations:
            base_prompt += f"\nAVAILABLE OPERATIONS: {', '.join(operations)}"

    return base_prompt

def _normalize_json_text(raw_text: str) -> str:
    """Normalize raw model text into clean JSON."""
    if not raw_text:
        return raw_text

    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.lower().startswith("json\n"):
        text = text[5:].lstrip()

    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end >= start:
        text = text[start:end + 1]

    return text

def _generate_scenario_bedrock(description: str, context: Optional[Dict[str, Any]] = None) -> ScenarioModification:
    """Generate scenario using Amazon Bedrock."""
    try:
        import boto3
    except ImportError:
        raise ImportError("Boto3 library not installed. Run: pip install boto3")

    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION", "us-east-1")

    if not aws_access_key or not aws_secret_key:
        raise ValueError("AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables.")

    model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")

    try:
        bedrock_client = boto3.client(
            "bedrock-runtime",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region
        )

        prompt = f"{_build_system_prompt(context)}\n\nGenerate a scenario for: {description}"

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "temperature": 0.3,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=json.dumps(body)
        )

        response_body = json.loads(response['body'].read().decode('utf-8'))
        content_block = response_body.get('content', [{}])[0]
        scenario_text = content_block.get('text', '').strip()
        scenario_json = _normalize_json_text(scenario_text)

        scenario_data = json.loads(scenario_json)

        # Convert to ScenarioModification
        parameters = [
            ScenarioParameter(
                key=p["key"],
                value=p["value"],
                unit=p.get("unit")
            ) for p in scenario_data["parameters"]
        ]

        # Convert contextual patterns
        contextual_patterns = []
        if "contextual_patterns" in scenario_data:
            contextual_patterns = [
                ContextualPattern(
                    attribute_name=cp["attribute_name"],
                    failure_values=cp["failure_values"],
                    normal_values=cp["normal_values"],
                    description=cp["description"]
                ) for cp in scenario_data["contextual_patterns"]
            ]

        return ScenarioModification(
            type=scenario_data["type"],
            target_services=scenario_data["target_services"],
            target_operations=scenario_data.get("target_operations", []),
            parameters=parameters,
            contextual_patterns=contextual_patterns,
            ramp_up_seconds=scenario_data.get("ramp_up_seconds", 0),
            ramp_down_seconds=scenario_data.get("ramp_down_seconds", 0)
        )

    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}")
    except Exception as e:
        raise ValueError(f"Bedrock API error: {e}")

def get_predefined_templates() -> List[Dict[str, Any]]:
    """Get predefined scenario templates for quick access."""
    return [
        {
            "name": "Database Latency Spike",
            "description": "Database becomes slow and responses take 2-5 seconds",
            "category": "infrastructure",
            "modification": {
                "type": "database_slow",
                "target_services": ["user-service", "payment-service", "order-service"],
                "target_operations": [],
                "parameters": [
                    {"key": "query_delay_ms", "value": 3000, "unit": "ms"},
                    {"key": "affected_percentage", "value": 80.0, "unit": "%"}
                ],
                "contextual_patterns": [
                    {
                        "attribute_name": "db.shard",
                        "failure_values": ["shard_03", "shard_07"],
                        "normal_values": ["shard_01", "shard_02", "shard_04", "shard_05"],
                        "description": "Database shards 3 and 7 experiencing high latency"
                    }
                ],
                "ramp_up_seconds": 60,
                "ramp_down_seconds": 30
            },
            "default_duration_minutes": 5
        },
        {
            "name": "Service Error Spike",
            "description": "Service starts returning 500 errors for 25% of requests",
            "category": "application",
            "modification": {
                "type": "error_rate",
                "target_services": ["api-gateway"],
                "target_operations": [],
                "parameters": [
                    {"key": "error_percentage", "value": 25.0, "unit": "%"},
                    {"key": "error_code", "value": 500}
                ],
                "contextual_patterns": [
                    {
                        "attribute_name": "cloud.region",
                        "failure_values": ["us-west-2", "eu-central-1"],
                        "normal_values": ["us-east-1", "ap-southeast-1", "eu-west-1"],
                        "description": "Regional infrastructure issues affecting specific AWS regions"
                    }
                ],
                "ramp_up_seconds": 30,
                "ramp_down_seconds": 15
            },
            "default_duration_minutes": 3
        },
        {
            "name": "Payment Service Unavailable",
            "description": "Payment service becomes completely unavailable",
            "category": "application",
            "modification": {
                "type": "service_unavailable",
                "target_services": ["payment-service"],
                "target_operations": [],
                "parameters": [
                    {"key": "unavailable_percentage", "value": 100.0, "unit": "%"}
                ],
                "contextual_patterns": [
                    {
                        "attribute_name": "payment.method",
                        "failure_values": ["credit_card_amex", "paypal"],
                        "normal_values": ["credit_card_visa", "bank_transfer", "crypto"],
                        "description": "Payment gateway issues affecting AmEx and PayPal transactions"
                    }
                ],
                "ramp_up_seconds": 0,
                "ramp_down_seconds": 0
            },
            "default_duration_minutes": 2
        },
        {
            "name": "Memory Pressure",
            "description": "Service experiences high memory usage (90%+)",
            "category": "infrastructure",
            "modification": {
                "type": "memory_pressure",
                "target_services": ["user-service"],
                "target_operations": [],
                "parameters": [
                    {"key": "memory_percentage", "value": 95.0, "unit": "%"},
                    {"key": "gc_frequency_multiplier", "value": 3.0}
                ],
                "ramp_up_seconds": 120,
                "ramp_down_seconds": 60
            },
            "default_duration_minutes": 8
        },
        {
            "name": "Network Partition",
            "description": "Network issues between frontend and backend services",
            "category": "infrastructure",
            "modification": {
                "type": "network_partition",
                "target_services": ["web-frontend", "api-gateway"],
                "target_operations": [],
                "parameters": [
                    {"key": "packet_loss_percentage", "value": 15.0, "unit": "%"},
                    {"key": "additional_latency_ms", "value": 500, "unit": "ms"}
                ],
                "ramp_up_seconds": 45,
                "ramp_down_seconds": 30
            },
            "default_duration_minutes": 4
        },
        # Infrastructure device scenarios
        {
            "name": "Switch Port Failure",
            "description": "Network switch port goes down affecting connected services",
            "category": "infrastructure_device",
            "modification": {
                "type": "interface_down",
                "target_services": [],
                "target_infrastructure": ["core-switch-01"],
                "target_operations": [],
                "parameters": [
                    {"key": "interfaces", "value": ["Gi0/24", "Gi0/25"]},
                    {"key": "duration_seconds", "value": 300}
                ],
                "ramp_up_seconds": 0,
                "ramp_down_seconds": 0
            },
            "default_duration_minutes": 5
        },
        {
            "name": "Firewall Blocking Traffic",
            "description": "Firewall rule misconfiguration blocking legitimate traffic",
            "category": "infrastructure_device",
            "modification": {
                "type": "firewall_rule_block",
                "target_services": [],
                "target_infrastructure": ["edge-firewall-01"],
                "target_operations": [],
                "parameters": [
                    {"key": "blocked_ports", "value": [443, 8080]},
                    {"key": "block_percentage", "value": 50.0}
                ],
                "ramp_up_seconds": 0,
                "ramp_down_seconds": 0
            },
            "default_duration_minutes": 3
        },
        {
            "name": "VM Host Memory Pressure",
            "description": "Hypervisor host under memory pressure affecting all VMs",
            "category": "infrastructure_device",
            "modification": {
                "type": "vm_host_overload",
                "target_services": [],
                "target_infrastructure": ["esxi-host-01"],
                "target_operations": [],
                "parameters": [
                    {"key": "memory_percentage", "value": 95},
                    {"key": "cpu_multiplier", "value": 1.5},
                    {"key": "memory_multiplier", "value": 1.3}
                ],
                "ramp_up_seconds": 60,
                "ramp_down_seconds": 30
            },
            "default_duration_minutes": 8
        },
        {
            "name": "Load Balancer Backend Unhealthy",
            "description": "Load balancer marks backends as unhealthy",
            "category": "infrastructure_device",
            "modification": {
                "type": "lb_backend_unhealthy",
                "target_services": [],
                "target_infrastructure": ["alb-frontend"],
                "target_operations": [],
                "parameters": [
                    {"key": "unhealthy_count", "value": 2},
                    {"key": "health_check_failures", "value": 3}
                ],
                "ramp_up_seconds": 30,
                "ramp_down_seconds": 15
            },
            "default_duration_minutes": 5
        },
        {
            "name": "Storage Latency Spike",
            "description": "SAN/NAS storage experiencing high latency",
            "category": "infrastructure_device",
            "modification": {
                "type": "storage_latency_spike",
                "target_services": [],
                "target_infrastructure": ["san-primary"],
                "target_operations": [],
                "parameters": [
                    {"key": "latency_multiplier", "value": 5.0},
                    {"key": "iops_reduction", "value": 0.5}
                ],
                "ramp_up_seconds": 30,
                "ramp_down_seconds": 60
            },
            "default_duration_minutes": 6
        },
        # Cascading outage scenarios
        {
            "name": "Storage to Database Cascade",
            "description": "Storage latency causes database timeouts cascading to app errors",
            "category": "cascading",
            "cascade_config": {
                "name": "Storage Cascade",
                "description": "Storage array latency cascading to application layer",
                "origin": "infrastructure",
                "trigger_component": "san-primary",
                "cascade_chain": [
                    {"component": "san-primary", "effect": "storage_latency_spike", "delay_ms": 0, "parameters": {"latency_multiplier": 5.0}},
                    {"component": "postgres-main", "effect": "query_timeout", "delay_ms": 5000, "parameters": {"timeout_multiplier": 3.0}},
                    {"component": "user-service", "effect": "error_rate", "delay_ms": 10000, "parameters": {"error_percentage": 30.0}},
                    {"component": "api-gateway", "effect": "latency_spike", "delay_ms": 15000, "parameters": {"latency_multiplier": 2.0}}
                ],
                "delay_between_stages_ms": 5000
            },
            "default_duration_minutes": 10
        },
        {
            "name": "Network Switch Cascade",
            "description": "Switch failure cascades to VM network issues and app errors",
            "category": "cascading",
            "cascade_config": {
                "name": "Network Switch Cascade",
                "description": "Core switch failure affecting multiple layers",
                "origin": "infrastructure",
                "trigger_component": "core-switch-01",
                "cascade_chain": [
                    {"component": "core-switch-01", "effect": "interface_down", "delay_ms": 0, "parameters": {}},
                    {"component": "vm-app-01", "effect": "network_timeout", "delay_ms": 2000, "parameters": {}},
                    {"component": "payment-service", "effect": "service_unavailable", "delay_ms": 5000, "parameters": {"unavailable_percentage": 100.0}},
                    {"component": "order-service", "effect": "error_rate", "delay_ms": 8000, "parameters": {"error_percentage": 50.0}}
                ],
                "delay_between_stages_ms": 3000
            },
            "default_duration_minutes": 8
        }
    ]
