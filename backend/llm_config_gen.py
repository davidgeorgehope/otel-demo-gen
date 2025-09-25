import os
import json
from openai import OpenAI
import boto3
from dotenv import load_dotenv
from typing import Any


load_dotenv()

# Don't initialize clients on import - do them lazily
openai_client = None
bedrock_client = None

def _get_openai_client():
    """Get or create the OpenAI client lazily."""
    global openai_client
    if openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
        openai_client = OpenAI(api_key=api_key)
    return openai_client

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
            region_name=aws_region
        )
    return bedrock_client

def _get_llm_provider():
    """Get the configured LLM provider."""
    return os.getenv("LLM_PROVIDER", "openai").lower()

def _call_openai(prompt: str) -> str:
    """Call OpenAI API."""
    client = _get_openai_client()
    model = os.getenv("OPENAI_MODEL", "o3")
    
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=float(os.getenv("OPENAI_TEMPERATURE", "0")),
        response_format={"type": "json_object"},
    )
    return completion.choices[0].message.content

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
        "max_tokens": 4000,
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
        
        # Parse response
        response_body = json.loads(response['body'].read())
        content_blocks = response_body.get('content', [])

        for block in content_blocks:
            if block.get('type') == 'tool_use' and block.get('name') == 'emit_config':
                return json.dumps(block.get('input', {}))
            if block.get('type') == 'text':
                return block.get('text', '')

        # Fallback to serialized response if no tool output present
        return json.dumps(response_body)
        
    except Exception as e:
        print(f"Error calling Bedrock API: {e}")
        raise

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

def generate_config_from_description(description: str) -> str:
    """Generate a JSON configuration from a natural language description using an LLM."""
    try:
        provider = _get_llm_provider()
        
        if provider == "openai":
            response_content = _call_openai(description)
        elif provider == "bedrock":
            response_content = _call_bedrock(description)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}. Use 'openai' or 'bedrock'.")
        
        # The LLM sometimes wraps the output in ```json ... ```, so we strip that.
        if response_content.startswith("```json"):
            response_content = response_content[7:]
        elif response_content.startswith("```"):
            response_content = response_content[3:]
        if response_content.endswith("```"):
            response_content = response_content[:-3]
        
        return response_content.strip()

    except ValueError as e:
        # Re-raise ValueError with the configuration message
        raise e
    except Exception as e:
        print(f"Error calling LLM API: {e}")
        raise

if __name__ == '__main__':
    # Example usage for testing
    user_description = "A financial services app with 5 microservices, a Postgres database, a Redis cache, and a Kafka queue for notifications."
    try:
        generated_json = generate_config_from_description(user_description)
        print("--- Generated JSON Config ---")
        print(generated_json)
    except Exception as e:
        print(f"Failed to generate config: {e}") 
