# AI-Powered Observability Demo Generator

## Overview
This tool generates realistic telemetry data (traces, logs, and metrics) for a user-defined microservices scenario. Users can describe a scenario in natural language, and the system will produce a configuration file for that scenario. The backend service will then use this config to continuously stream synthetic telemetry into an OpenTelemetry (OTel) Collector via OTLP.

## Features
- Generate traces, logs, and metrics in OTLP format.
- Simulate distributed transactions, application logs, and system metrics.
- User-driven configuration through natural language input.
- Realistic simulation of service interactions, dependencies, errors, and performance patterns.

## Prerequisites
- Python 3.9+
- Node.js
- Docker (optional, for containerized deployment)

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd otel-demo-gen
   ```

2. **Install Python dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Install Node.js dependencies:**
   ```bash
   cd ../frontend
   npm install
   ```

4. **Set up environment variables:**
   Export your OpenAI API key:
   ```bash
   export OPENAI_API_KEY=your_openai_api_key
   ```

5. **Start the application locally:**
   From the root directory, run:
   ```bash
   ./start-local.sh
   ```

## Usage
- Access the frontend UI to input your scenario description.
- Review the generated YAML configuration.
- Start and stop the telemetry simulation as needed.

## Deployment
- Use Docker Compose to run the frontend, backend, and OpenTelemetry Collector together.
- Kubernetes manifests are available for cloud deployment.

## Contributing
- Contributions are welcome! Please fork the repository and submit a pull request.

## License
- This project is licensed under the MIT License.
