# AI-Powered Observability Demo Generator

## Overview
This tool generates realistic telemetry data (traces, logs, and metrics) for user-defined microservices scenarios. Users can describe scenarios in natural language, and the system will produce configuration files and continuously stream synthetic telemetry into OpenTelemetry (OTel) Collectors via OTLP.

## ✨ Key Features
- **AI-Powered Config Generation**: Natural language → production-ready observability scenarios
- **Multi-User Job Management**: Multiple concurrent telemetry generation jobs
- **Multiple LLM Providers**: Support for OpenAI and Amazon Bedrock (Claude Sonnet 4)
- **Realistic Telemetry**: Traces, logs, and metrics with semantic conventions
- **Zero Infrastructure**: No need to deploy actual microservices for demos
- **Multi-Language Simulation**: Runtime-specific metrics per language (Java, Python, Go, etc.)

## 🚀 Quick Start

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd otel-demo-gen
   ```

2. **Set up environment configuration:**
   ```bash
   cp .env.example .env
   # Edit .env with your preferred LLM provider (see LLM Setup section)
   ```

3. **Install dependencies:**
   ```bash
   # Backend
   cd backend
   pip install -r requirements.txt
   
   # Frontend  
   cd ../frontend
   npm install
   ```

4. **Start the application:**
   ```bash
   # From root directory
   ./start-local.sh
   ```

5. **Access the UI:**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000

## 🤖 LLM Provider Setup

### Option 1: OpenAI (Default)
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

### Option 2: Amazon Bedrock (Claude Sonnet 4)
```env
LLM_PROVIDER=bedrock
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

### No LLM Provider
If no LLM is configured, you can still:
- Use the "Load Test Config" button
- Create jobs with pre-built configurations
- Access test config via `GET /test-config`

📖 **Detailed Setup**: See [README-LLM-Setup.md](./README-LLM-Setup.md) for complete configuration guide.

## 👥 Multi-User Job Management

The application supports multiple concurrent telemetry generation jobs:

- **Create New Job**: Generate or load configurations and start telemetry streams
- **Manage Jobs**: View all running/stopped jobs across all users
- **Job Details**: See service counts, languages, configuration summaries
- **Real-time Updates**: Job status updates every 5 seconds

### API Endpoints
- `GET /jobs` - List all jobs
- `POST /start` - Start new telemetry job
- `POST /stop/{job_id}` - Stop specific job
- `DELETE /jobs/{job_id}` - Delete job
- `GET /llm-config` - Check LLM provider status

## 🏗️ Architecture

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
    ↓ 
Observability Backend
```

### Tech Stack
- **Backend**: Python, FastAPI, OpenTelemetry
- **Frontend**: React, Vite, Tailwind CSS
- **LLM Integration**: OpenAI API, Amazon Bedrock
- **Telemetry**: OTLP JSON format

## 📊 Configuration Schema

```yaml
services:
  - name: payment-service
    language: java
    role: backend
    operations:
      - name: "ProcessPayment"
        span_name: "POST /payments"
        business_data:
          - name: "amount"
            type: "number"
            min_value: 1.00
            max_value: 999.99
    depends_on:
      - db: postgres-main
      - service: fraud-service
        protocol: http

databases:
  - name: postgres-main
    type: postgres

telemetry:
  trace_rate: 5
  error_rate: 0.05
  include_logs: true
```

## 🐳 Deployment

### Docker Compose
```bash
docker-compose up -d
```

### Kubernetes
```bash
kubectl apply -f k8s/
```

### Environment Variables
```env
# Required for LLM generation
LLM_PROVIDER=openai|bedrock
OPENAI_API_KEY=sk-...        # For OpenAI
AWS_ACCESS_KEY_ID=...        # For Bedrock
AWS_SECRET_ACCESS_KEY=...    # For Bedrock

# Optional
OTEL_COLLECTOR_URL=http://localhost:4318
DEBUG=false
```

## 🧪 Testing

```bash
# Test backend health
curl http://localhost:8000/

# Check LLM configuration
curl http://localhost:8000/llm-config

# Get test configuration
curl http://localhost:8000/test-config

# List jobs
curl http://localhost:8000/jobs
```

## 🛠️ Development

### Prerequisites
- Python 3.9+
- Node.js 18+
- OpenAI API key OR AWS credentials with Bedrock access

### Local Development
```bash
# Backend with hot reload
cd backend && uvicorn main:app --reload --port 8000

# Frontend with hot reload  
cd frontend && npm run dev
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)
- **Documentation**: [Architecture Guide](.cursor/rules/architecture.mdc)
- **LLM Setup**: [LLM Setup Guide](./README-LLM-Setup.md)
