import logging
import os
import json
from typing import Any, List, Optional

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from pydantic import ValidationError

from config_schema import ScenarioConfig


load_dotenv()

# Don't initialize clients on import - do them lazily
bedrock_client = None

logger = logging.getLogger(__name__)


def _get_bedrock_client():
    """Get or create the Bedrock client lazily."""
    global bedrock_client
    if bedrock_client is None:
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_region = os.getenv("AWS_REGION", "us-east-1")
        
        if not aws_access_key or not aws_secret_key:
            raise ValueError(
                "AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
            )
        
        bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
            config=Config(read_timeout=300)
        )
    return bedrock_client

def _select_content_from_blocks(content_blocks: List[dict[str, Any]]) -> tuple[Optional[str], bool]:
    """Pick the best content emitted by the model along with empty-tool flag."""
    selected_text: Optional[str] = None
    empty_tool = False

    for block in content_blocks or []:
        block_type = block.get("type")

        if block_type == "tool_use" and block.get("name") == "emit_config":
            input_payload = block.get("input")

            if isinstance(input_payload, (dict, list)):
                if input_payload:
                    return json.dumps(input_payload), empty_tool
                empty_tool = True
                continue

            if isinstance(input_payload, str):
                stripped = input_payload.strip()
                if stripped:
                    return stripped, empty_tool
                empty_tool = True
                continue

        if block_type == "text":
            text_value = block.get("text")
            if text_value and text_value.strip():
                selected_text = text_value.strip()

    return selected_text, empty_tool


def _call_bedrock(prompt: str) -> str:
    """Call Amazon Bedrock Claude API."""
    client = _get_bedrock_client()
    model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-20250514-v1:0")
    temperature = float(os.getenv("BEDROCK_TEMPERATURE", "0"))

    tools = [
        {
            "name": "emit_config",
            "description": "Return a JSON object that matches the observability scenario schema.",
            "input_schema": SCENARIO_RESPONSE_SCHEMA,
        }
    ]
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 65536,
        "temperature": temperature,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        "tools": tools,
        "tool_choice": {"type": "tool", "name": "emit_config"}
    }
    
    try:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body),
            contentType="application/json"
        )

        response_body = json.loads(response["body"].read())
        content_blocks = response_body.get("content", [])

        selected_content, saw_empty_tool = _select_content_from_blocks(content_blocks)

        if selected_content:
            return selected_content

        if saw_empty_tool:
            logger.warning("Bedrock emit_config tool returned empty payload; falling back to raw response")

        # Fallback to serialized response if no usable content present
        return json.dumps(response_body)

    except Exception:
        logger.exception("Error calling Bedrock API")
        raise


def _normalize_json_text(raw_text: str) -> str:
    """Strip markdown fences and isolate the JSON object."""
    if not raw_text:
        return raw_text

    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        # Drop opening fence
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # Drop closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.lower().startswith("json\n"):
        text = text[5:].lstrip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end >= start:
        text = text[start:end + 1]

    return text


def _format_validation_error(error: str) -> str:
    """Tidy up noisy validation errors for prompt inclusion."""
    lines = [line.strip() for line in error.splitlines() if line.strip()]
    if not lines:
        return error
    # Limit to first ~20 lines to avoid overwhelming prompt
    return "\n".join(lines[:20])


def _build_retry_prompt(description: str, last_error: Optional[str], previous_output: Optional[str]) -> str:
    """Create a retry prompt that includes validation feedback."""
    parts = [description.strip(),
             "\nThe previous JSON output failed validation with this error:",
             last_error or "Unknown validation error.",
             "\nREQUIREMENTS:",
             "- Emit valid JSON that matches the provided schema.",
             "- Do not include markdown fences or comments.",
             "- Ensure required sections like services, telemetry, log_samples are present." ]

    if previous_output:
        parts.extend([
            "\nPrevious JSON output for reference:",
            previous_output.strip()
        ])

    parts.append("\nRegenerate a corrected JSON document that satisfies all schema constraints.")
    return "\n".join(parts)


def _preview_text(text: Optional[str], limit: int = 800) -> str:
    """Return a truncated preview of potentially long model output for logging."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated]"

SCENARIO_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["services", "telemetry"],
    "properties": {
        "services": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "language", "log_samples"],
                "properties": {
                    "name": {"type": "string"},
                    "language": {"type": "string"},
                    "role": {"type": "string"},
                    "depends_on": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "service": {"type": "string"},
                                "db": {"type": "string"},
                                "cache": {"type": "string"},
                                "queue": {"type": "string"},
                                "protocol": {"type": "string"},
                                "via": {"type": "string"},
                                "example_queries": {"type": "array", "items": {"type": "string"}},
                                "latency": {
                                    "type": "object",
                                    "properties": {
                                        "min_ms": {"type": "integer"},
                                        "max_ms": {"type": "integer"},
                                        "probability": {"type": "number"}
                                    },
                                    "required": ["min_ms", "max_ms"]
                                }
                            },
                            "additionalProperties": False,
                            "minProperties": 1
                        }
                    },
                    "operations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "span_name"],
                            "properties": {
                                "name": {"type": "string"},
                                "span_name": {"type": "string"},
                                "description": {"type": "string"},
                                "db_queries": {"type": "array", "items": {"type": "string"}},
                                "latency": {
                                    "type": "object",
                                    "properties": {
                                        "min_ms": {"type": "integer"},
                                        "max_ms": {"type": "integer"},
                                        "probability": {"type": "number"}
                                    },
                                    "required": ["min_ms", "max_ms"]
                                },
                                "business_data": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["name", "type"],
                                        "properties": {
                                            "name": {"type": "string"},
                                            "type": {"type": "string", "enum": ["string", "number", "integer", "boolean", "enum"]},
                                            "pattern": {"type": "string"},
                                            "min_value": {"type": "number"},
                                            "max_value": {"type": "number"},
                                            "values": {"type": "array", "items": {"type": "string"}},
                                            "description": {"type": "string"}
                                        },
                                        "additionalProperties": False
                                    }
                                }
                            },
                            "additionalProperties": False
                        }
                    },
                    "log_samples": {
                        "type": "array",
                        "minItems": 8,
                        "maxItems": 10,
                        "items": {
                            "type": "object",
                            "required": ["level", "message"],
                            "properties": {
                                "level": {"type": "string", "enum": ["INFO", "WARN", "ERROR", "DEBUG"]},
                                "message": {"type": "string"},
                                "context": {"type": "object"}
                            },
                            "additionalProperties": False
                        }
                    }
                },
                "additionalProperties": False
            }
        },
        "databases": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "type"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"}
                },
                "additionalProperties": False
            }
        },
        "message_queues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "type"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"}
                },
                "additionalProperties": False
            }
        },
        "telemetry": {
            "type": "object",
            "required": ["trace_rate", "error_rate", "metrics_interval", "include_logs"],
            "properties": {
                "trace_rate": {"type": "integer"},
                "error_rate": {"type": "number"},
                "metrics_interval": {"type": "integer"},
                "include_logs": {"type": "boolean"}
            },
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}

SCENARIO_SCHEMA_TEXT = json.dumps(SCENARIO_RESPONSE_SCHEMA, indent=2)

SYSTEM_PROMPT = f"""
You are an expert assistant that generates architecture configuration files for a microservices observability demo tool.
Produce a JSON object that satisfies the scenario description and the schema below.

REQUIREMENTS
1. Output only valid JSON (no code fences or commentary) that conforms to the schema.
2. Populate 8-10 log_samples per service with 6-8 INFO entries and 2 ERROR entries, using realistic placeholders like {{user_id}}, {{order_id}}, {{duration_ms}}.
3. Provide coherent dependencies (frontends -> backends -> data stores) and vary language assignments for services.
4. Use dependency keys exactly as specified (service, db, cache, queue).
5. Keep latency objects well-formed and ensure probability defaults to 1.0 if omitted.
6. Prefer detailed business_data definitions that match the service domain.

EXPECTED JSON SCHEMA:
{SCENARIO_SCHEMA_TEXT}
"""

def generate_config_from_description(description: str, *, max_attempts: int = 3) -> str:
    """Generate a JSON configuration from a natural language description using Amazon Bedrock."""

    if not description or not description.strip():
        raise ValueError("Description must not be empty.")

    last_error: Optional[str] = None
    previous_output: Optional[str] = None

    total_attempts = max(1, max_attempts)

    for attempt in range(total_attempts):
        prompt = description if attempt == 0 else _build_retry_prompt(description, last_error, previous_output)

        raw_response = _call_bedrock(prompt)
        normalized = _normalize_json_text(raw_response)

        previous_output = normalized

        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as decode_err:
            last_error = _format_validation_error(f"JSON decoding error: {decode_err}")
            logger.warning(
                "Config generation attempt %d/%d failed JSON decode: %s | preview=%s",
                attempt + 1,
                total_attempts,
                decode_err,
                _preview_text(normalized)
            )
            continue

        try:
            scenario = ScenarioConfig(**parsed)
            # Return a compact JSON string suitable for downstream processing
            logger.info("Config generation attempt %d/%d succeeded", attempt + 1, total_attempts)
            return json.dumps(scenario.model_dump())
        except ValidationError as validation_err:
            last_error = _format_validation_error(str(validation_err))
            logger.warning(
                "Config generation attempt %d/%d failed validation: %s | preview=%s",
                attempt + 1,
                total_attempts,
                last_error,
                _preview_text(normalized)
            )
            continue

    raise ValueError(last_error or "Failed to generate configuration that matches the schema.")

if __name__ == '__main__':
    # Example usage for testing
    user_description = "A financial services app with 5 microservices, a Postgres database, a Redis cache, and a Kafka queue for notifications."
    try:
        generated_json = generate_config_from_description(user_description)
        print("--- Generated JSON Config ---")
        print(generated_json)
    except Exception as e:
        print(f"Failed to generate config: {e}") 
