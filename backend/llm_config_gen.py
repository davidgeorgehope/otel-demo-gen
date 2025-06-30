import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
4.  For database dependencies, you can add a list of **`example_queries`** that are realistic for the specified database type (e.g., SQL for Postgres, JSON for MongoDB).
5.  Create plausible dependencies: frontends call backends, backends use databases. Ensure the generated scenario is coherent.
6.  Assign a variety of languages to the services to showcase a polyglot environment.
7.  Maintain valid YAML syntax. Do not include any narrative or explanation, only the YAML code.

**Example User Request:** "An e-commerce app with a slow reporting service and a payments service that sometimes has slow database queries."

**Example Output:**
```yaml
services:
  - name: order-service
    language: java
    depends_on:
      - db: postgres-db
        example_queries:
          - "SELECT * FROM orders WHERE id = ?"
          - "INSERT INTO orders (id, user_id, status) VALUES (?, ?, ?)"
        latency:
          min_ms: 150
          max_ms: 300
          probability: 0.05 # 5% of queries are slow
  - name: reporting-service
    language: python
    operations:
      - name: "GenerateWeeklySalesReport"
        span_name: "GET /reports/sales/weekly"
        db_queries:
          - "SELECT p.category, SUM(oi.quantity * p.price) as total_sales FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_date > ? GROUP BY p.category ORDER BY total_sales DESC"
        latency:
          min_ms: 1200
          max_ms: 3500
    depends_on:
      - db: postgres-db

databases:
  - name: postgres-db
    type: postgres

message_queues: []

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
        Exception: If the OpenAI API call fails.
    """
    try:
        completion = client.chat.completions.create(
            model="o3",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
        )
        response_content = completion.choices[0].message.content
        
        # The LLM sometimes wraps the output in ```yaml ... ```, so we strip that.
        if response_content.startswith("```yaml"):
            response_content = response_content[7:]
        if response_content.endswith("```"):
            response_content = response_content[:-3]
        
        return response_content.strip()

    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
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