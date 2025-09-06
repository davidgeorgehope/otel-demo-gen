# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI-Powered Observability Demo Generator that generates realistic telemetry data (traces, logs, and metrics) for user-defined microservices scenarios. Users can describe scenarios in natural language, and the system produces configuration files and streams synthetic telemetry into OpenTelemetry Collectors via OTLP.

## Development Commands

### Backend (Python/FastAPI)
```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Run development server with auto-reload
uvicorn main:app --reload --port 8000

# Run backend health check
curl http://localhost:8000/

# Check LLM configuration status
curl http://localhost:8000/llm-config
```

### Frontend (React/Vite)
```bash
# Install dependencies
cd frontend
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Run linting
npm run lint

# Preview production build
npm run preview
```

### Full Application
```bash
# Automated startup (recommended for development)
./start-local.sh

# This script:
# 1. Installs backend dependencies and starts backend on available port
# 2. Installs frontend dependencies and starts frontend dev server
# 3. Sets up proper port forwarding and cleanup handlers
```

## Architecture

### High-Level Structure
```
User Input (Natural Language) 
    ↓ 
LLM (OpenAI/Bedrock) 
    ↓ 
YAML Configuration 
    ↓ 
Telemetry Generation Engine 
    ↓ 
OTLP JSON Payloads 
    ↓ 
OpenTelemetry Collector
```

### Backend Components
- **main.py**: FastAPI application with multi-user job management system
- **generator.py**: Core telemetry generation engine with threading
- **llm_config_gen.py**: LLM integration (OpenAI/Bedrock) for YAML generation
- **config_schema.py**: Pydantic models for configuration validation
- **k8s_metrics_generator.py**: Kubernetes-specific metrics generation

### Frontend Components
- **src/App.jsx**: Main application with job management UI
- **src/components/**: React components for forms, config display, job controls
- **vite.config.js**: Development server with backend proxy configuration

### Key Features
- **Multi-User Job Management**: Supports concurrent telemetry generation jobs
- **Multiple LLM Providers**: OpenAI and Amazon Bedrock support
- **Flexible Authentication**: Support for Bearer tokens and ApiKey authentication
- **Realistic Telemetry**: Multi-language simulation with runtime-specific metrics
- **Advanced Configuration**: Business operations, latency simulation, example queries
- **Kubernetes Metrics**: Dedicated K8s pod/node metrics generation

## Configuration

### Environment Variables
```bash
# LLM Provider (required for config generation)
LLM_PROVIDER=openai|bedrock

# OpenAI Configuration
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini  # Default model

# Amazon Bedrock Configuration
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

# Optional Configuration
OTEL_COLLECTOR_URL=http://localhost:4318  # Default OTLP endpoint
DEBUG=false

# Job Management Limits
MAX_ACTIVE_JOBS=50
MAX_JOBS_PER_USER=3
MAX_JOB_DURATION_HOURS=24
```

### YAML Configuration Schema
```yaml
services:
  - name: service-name
    language: python|java|nodejs|go|ruby|dotnet|typescript
    role: frontend|backend|database-service|worker
    operations:  # Business operation modeling
      - name: "ProcessPayment"
        span_name: "POST /payments"
        db_queries:
          - "SELECT * FROM accounts WHERE id = ?"
        business_data:  # Realistic business data in traces
          - name: "user_id"
            type: "string"
            pattern: "user_{random}"
          - name: "amount"
            type: "number"
            min_value: 1.00
            max_value: 999.99
        latency:  # Performance simulation
          min_ms: 50
          max_ms: 200
          probability: 0.1  # 10% of operations slow
    depends_on:
      - service: other-service
        protocol: http|grpc
      - db: postgres-main
        example_queries:
          - "SELECT * FROM users WHERE email = ?"
      - cache: redis-cache
      - queue: kafka-events

databases:
  - name: postgres-main
    type: postgres|mysql|mongodb|redis

message_queues:
  - name: kafka-events
    type: kafka|rabbitmq|sqs

telemetry:
  trace_rate: 5           # Traces per second
  error_rate: 0.05        # 5% error rate
  metrics_interval: 10    # Seconds between metrics
  include_logs: true
```

## Authentication Types

The application supports flexible authentication for OTLP endpoints:

### Supported Auth Types
- **ApiKey**: `Authorization: ApiKey your-key-here`
- **Bearer**: `Authorization: Bearer your-token-here`

### Frontend Configuration
Users can select the authentication type in the UI:
1. Enter API key/token in the credentials field
2. Select "ApiKey" or "Bearer" from the dropdown
3. The system displays a preview: `Authorization: Bearer ***` 

### Backend API Parameters
```json
{
  "api_key": "your-credential-here",
  "auth_type": "Bearer"  // or "ApiKey"
}
```

Both `/start` and `/restart` endpoints accept the `auth_type` parameter. If not specified, defaults to "ApiKey" for backward compatibility.

## API Endpoints

### Core APIs
- `POST /generate-config`: Generate YAML from natural language description
- `POST /start`: Start new telemetry generation job
- `POST /stop/{job_id}`: Stop specific job
- `GET /jobs`: List all jobs with status
- `DELETE /jobs/{job_id}`: Delete job
- `GET /test-config`: Get sample configuration without LLM
- `GET /llm-config`: Check LLM provider configuration
- `GET /limits`: View job limits and current usage

### Health & Utilities  
- `GET /`: Health check endpoint
- `POST /health-check-otlp`: Test OTLP endpoint connectivity
- `POST /cleanup`: Manually trigger job cleanup
- `GET /whoami`: Get current user from headers

## Development Guidelines

### Backend Development
- Use type hints throughout Python code
- Follow Pydantic models for validation
- Implement proper error handling with HTTPException
- Use threading for telemetry generation (see TelemetryGenerator class)
- Handle OTLP connection failures gracefully

### Frontend Development  
- Use functional React components with hooks
- Implement proper error boundaries
- Use Tailwind CSS for styling consistency
- Handle API errors with user-friendly messages
- Implement real-time job status updates

### Testing
- Backend: Test API endpoints and telemetry generation
- Frontend: Test component rendering and user interactions
- Integration: Test full workflow from description to telemetry
- Manual: Verify telemetry appears in observability backends

## Common Development Tasks

### Adding New LLM Provider
1. Update `llm_config_gen.py` with new provider client
2. Add provider-specific environment variables
3. Update system prompt if needed
4. Test configuration generation

### Extending Configuration Schema
1. Update Pydantic models in `config_schema.py`
2. Modify telemetry generation logic in `generator.py`
3. Update system prompt in `llm_config_gen.py`
4. Test with sample configurations

### Adding New Telemetry Types
1. Implement generation logic in `generator.py`
2. Add OTLP payload formatting
3. Update resource attributes as needed
4. Test with target observability backend

### Adding New Authentication Types
1. Update `TelemetryGenerator.__init__()` to handle new auth type
2. Add new option to frontend dropdown in `Controls.jsx`
3. Update API models in `config_schema.py` and `main.py`
4. Test with target OTLP endpoint

### Debugging Telemetry Generation
- Check backend logs: `uvicorn main:app --reload --log-level debug`
- Verify OTLP endpoint: `curl http://localhost:4318/v1/traces`
- Inspect generated payloads in console output
- Use dry-run capabilities for payload inspection

## Deployment

### Docker Development
```bash
# Build and run with Docker Compose
docker-compose up --build

# Backend only
cd backend && docker build -t otel-demo-backend .
docker run -p 8000:8000 -e OPENAI_API_KEY=$OPENAI_API_KEY otel-demo-backend
```

### Kubernetes
- See `k8s/` directory for deployment manifests
- Configure secrets for API keys
- Set up proper service networking
- Configure resource limits for jobs

## Important Implementation Notes

### Job Management
- System supports multiple concurrent telemetry jobs
- Each job runs in separate threads (main + k8s metrics)
- Automatic cleanup of old/timed-out jobs
- Per-user job limits with configurable thresholds

### Telemetry Realism
- Multi-language runtime simulation with different metrics per language
- Semantic conventions compliance for OTLP attributes  
- Business operation modeling with realistic database queries
- Probabilistic latency and error injection
- Kubernetes pod/node metrics with realistic resource usage

### Error Handling
- OTLP connection failure detection and job marking
- Graceful degradation when LLM providers unavailable
- Proper HTTP status codes and error messages
- Background thread cleanup on application shutdown

## Architecture Documentation

For detailed architecture information, see `.cursor/rules/architecture.mdc` which contains comprehensive technical implementation details, system design decisions, and extension points.