"""
LLM-powered scenario generation for outage simulation.
Converts natural language descriptions into structured scenario modifications.
"""

import os
import json
from typing import Dict, List, Any, Optional
from config_schema import ScenarioModification, ScenarioParameter, ContextualPattern

def generate_scenario_from_description(description: str, context: Optional[Dict[str, Any]] = None) -> ScenarioModification:
    """
    Uses LLM to generate a scenario modification from a natural language description.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        return _generate_scenario_openai(description, context)
    elif provider == "bedrock":
        return _generate_scenario_bedrock(description, context)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

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

def _generate_scenario_openai(description: str, context: Optional[Dict[str, Any]] = None) -> ScenarioModification:
    """Generate scenario using OpenAI."""
    try:
        import openai
    except ImportError:
        raise ImportError("OpenAI library not installed. Run: pip install openai")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")

    client = openai.OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _build_system_prompt(context)},
                {"role": "user", "content": f"Generate a scenario for: {description}"}
            ],
            temperature=0.3,
            max_tokens=1000
        )

        scenario_json = response.choices[0].message.content.strip()

        # Clean up JSON if it has markdown formatting
        if scenario_json.startswith("```json"):
            scenario_json = scenario_json.replace("```json", "").replace("```", "").strip()
        elif scenario_json.startswith("```"):
            scenario_json = scenario_json.replace("```", "").strip()

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
        raise ValueError(f"OpenAI API error: {e}")

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
        scenario_json = response_body['content'][0]['text'].strip()

        # Clean up JSON if it has markdown formatting
        if scenario_json.startswith("```json"):
            scenario_json = scenario_json.replace("```json", "").replace("```", "").strip()
        elif scenario_json.startswith("```"):
            scenario_json = scenario_json.replace("```", "").strip()

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
        }
    ]