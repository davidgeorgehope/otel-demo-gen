import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are an assistant that generates architecture configuration files for a microservices observability demo tool.
The user will describe a hypothetical application (number of services, types of databases, message queues, etc.), and you will produce a YAML configuration representing that scenario.

Requirements:
- Output only YAML code (no explanatory text).
- Use the following structure with top-level keys: services, databases, message_queues, telemetry.
- Under `services`, list each service with a `name`, and if possible assign a `language` (choose from: python, java, nodejs, go, dotnet, ruby, etc. – use a variety if multiple services) and a `depends_on` list describing its connections. Use `service: <name>`, `db: <name>`, or `cache: <name>` to denote dependencies.
- For service-to-service communication, you can specify `protocol` (http or grpc) and if it's asynchronous, `via: <queue_name>`.
- Under `databases`, list any databases mentioned (with `name` and `type`).
- Under `message_queues`, list any message broker or queue if mentioned (with `name` and `type`).
- The `telemetry` section should include default settings (e.g. trace_rate: 5, error_rate: 0.05, metrics_interval: 10, include_logs: true).
- Ensure every component mentioned by the user is included. Create plausible dependencies between services (e.g., frontends call backends, backends use databases) so the scenario is coherent.
- Maintain valid YAML syntax. Do not include any narrative or explanation, only the YAML code.

Example user request: "I want a simple app with 2 services and a MySQL database"

Example output:
```yaml
services:
  - name: service-a
    language: python
    depends_on:
      - service: service-b
        protocol: http
      - db: mysql-db
  - name: service-b
    language: java
    depends_on: []
databases:
  - name: mysql-db
    type: mysql
message_queues: []
telemetry:
  trace_rate: 2
  error_rate: 0.01
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