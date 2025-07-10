import os
import json
from openai import OpenAI
import boto3
from dotenv import load_dotenv

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
    )
    return completion.choices[0].message.content

def _call_bedrock(prompt: str) -> str:
    """Call Amazon Bedrock Claude API."""
    client = _get_bedrock_client()
    model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-20250514-v1:0")
    
    # Format the prompt for Claude
    formatted_prompt = f"Human: {SYSTEM_PROMPT}\n\n{prompt}\n\nAssistant:"
    
    # Prepare the request body for Claude
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4000,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user", 
                "content": [{"type": "text", "text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]
            }
        ]
    }
    
    try:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body),
            contentType="application/json"
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
        
    except Exception as e:
        print(f"Error calling Bedrock API: {e}")
        raise

SYSTEM_PROMPT = """
You are an expert assistant that generates architecture configuration files for a microservices observability demo tool.
The user will describe a scenario, and you will produce a YAML configuration representing it.

**Requirements:**

1.  **Output only YAML code.** Do not include any explanatory text.
2.  Use the following top-level keys: `services`, `databases`, `message_queues`, `telemetry`.
3.  For each service, you can optionally define a list of **`operations`** to simulate realistic business transactions.
    *   An `operation` should have a `name` (e.g., "GetUserProfile"), a `span_name` (e.g., "GET /users/{id}"), and can include a list of `db_queries`.
    *   To simulate performance issues, you can add a **`latency`** block to operations or dependencies. For example, to make a reporting operation slow, add `latency: {min_ms: 800, max_ms: 1500}`.
    *   To simulate intermittent slowness on a dependency, add a `latency` block with a `probability` less than 1.0 (e.g., `probability: 0.1` for 10% of the time).
    *   **NEW:** Add **`business_data`** to operations to include realistic business-relevant data in traces. This makes demos much more realistic by adding fields like shopping cart amounts, user IDs, product counts, etc.
4.  For database dependencies, you can add a list of **`example_queries`** that are realistic for the specified database type (e.g., SQL for Postgres, JSON for MongoDB).
5.  Create plausible dependencies: frontends call backends, backends use databases. Ensure the generated scenario is coherent.
6.  Assign a variety of languages to the services to showcase a polyglot environment.
7.  Maintain valid YAML syntax. Do not include any narrative or explanation, only the YAML code.

**CRITICAL: Dependency Field Names**
When defining service dependencies in the `depends_on` list, use these EXACT field names:
- **Service dependency**: `service: "service-name"`
- **Database dependency**: `db: "database-name"`  
- **Cache dependency**: `cache: "cache-name"`
- **Message queue dependency**: `queue: "queue-name"` (NOT "message_queue")

**Business Data Configuration:**
- **`type`**: "string", "number", "integer", "boolean", or "enum"
- **For strings**: Use `pattern` with placeholders like `user_{random}`, `order_{uuid}`, `session_{random_string}`
- **For numbers**: Use `min_value` and `max_value` (e.g., cart amounts, prices)
- **For integers**: Use `min_value` and `max_value` (e.g., quantity, counts)
- **For enums**: Use `values` list (e.g., payment methods, status values)
- **For booleans**: No additional config needed

**Example User Request:** "An e-commerce app with microservices, databases, cache, and message queues."

**Example Output:**
```yaml
services:
  - name: order-service
    language: java
    operations:
      - name: "ProcessOrder"
        span_name: "POST /orders"
        db_queries:
          - "INSERT INTO orders (id, user_id, status, total_amount) VALUES (?, ?, ?, ?)"
        business_data:
          - name: "user_id"
            type: "string"
            pattern: "user_{random}"
          - name: "order_total"
            type: "number"
            min_value: 10.99
            max_value: 599.99
          - name: "item_count"
            type: "integer"
            min_value: 1
            max_value: 15
          - name: "payment_method"
            type: "enum"
            values: ["credit_card", "paypal", "bank_transfer", "apple_pay"]
    depends_on:
      - db: postgres-db
        example_queries:
          - "SELECT * FROM orders WHERE id = ?"
          - "INSERT INTO orders (id, user_id, status) VALUES (?, ?, ?)"
        latency:
          min_ms: 150
          max_ms: 300
          probability: 0.05 # 5% of queries are slow
      - cache: redis-cache
      - queue: kafka-events
  - name: notification-service
    language: python
    operations:
      - name: "SendOrderConfirmation"
        span_name: "CONSUME kafka-events"
        business_data:
          - name: "notification_type"
            type: "enum"
            values: ["email", "sms", "push"]
          - name: "delivery_success"
            type: "boolean"
    depends_on:
      - queue: kafka-events
      - service: email-service
        protocol: http
        latency:
          min_ms: 50
          max_ms: 200
  - name: reporting-service
    language: python
    operations:
      - name: "GenerateWeeklySalesReport"
        span_name: "GET /reports/sales/weekly"
        db_queries:
          - "SELECT p.category, SUM(oi.quantity * p.price) as total_sales FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_date > ? GROUP BY p.category ORDER BY total_sales DESC"
        business_data:
          - name: "report_period"
            type: "string"
            pattern: "week_{random}"
          - name: "total_revenue"
            type: "number"
            min_value: 1000.0
            max_value: 50000.0
          - name: "is_scheduled"
            type: "boolean"
        latency:
          min_ms: 1200
          max_ms: 3500
    depends_on:
      - db: postgres-db
      - cache: redis-cache

databases:
  - name: postgres-db
    type: postgres

message_queues:
  - name: kafka-events
    type: kafka

telemetry:
  trace_rate: 2
  error_rate: 0.05
  metrics_interval: 10
  include_logs: true
```
"""

def generate_config_from_description(description: str) -> str:
    """
    Generates a YAML configuration from a natural language description using an LLM.

    Args:
        description: The user's description of the desired scenario.

    Returns:
        A string containing the generated YAML configuration.
    
    Raises:
        ValueError: If LLM provider is not configured properly.
        Exception: If the LLM API call fails.
    """
    try:
        provider = _get_llm_provider()
        
        if provider == "openai":
            response_content = _call_openai(description)
        elif provider == "bedrock":
            response_content = _call_bedrock(description)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}. Use 'openai' or 'bedrock'.")
        
        # The LLM sometimes wraps the output in ```yaml ... ```, so we strip that.
        if response_content.startswith("```yaml"):
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
        generated_yaml = generate_config_from_description(user_description)
        print("--- Generated YAML Config ---")
        print(generated_yaml)
    except Exception as e:
        print(f"Failed to generate config: {e}") 