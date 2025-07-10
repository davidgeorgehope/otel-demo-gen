# Deployment Guide

This guide covers deployment options for the AI-Powered Observability Demo Generator.

## Prerequisites

- Docker & Docker Compose
- Kubernetes cluster (for K8s deployment)
- kubectl configured for your cluster
- OpenAI API key or AWS credentials for Bedrock

## Environment Setup

### 1. Create Environment File

Create a `.env` file in the project root:

```bash
# Copy example file
cp .env.example .env

# Edit with your values
nano .env
```

Required environment variables:
```bash
# OpenAI Configuration (if using OpenAI)
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini

# AWS Bedrock Configuration (if using Bedrock)
AWS_ACCESS_KEY_ID=your-aws-access-key-here
AWS_SECRET_ACCESS_KEY=your-aws-secret-key-here
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

# Optional: Custom OTLP endpoint
OTEL_COLLECTOR_URL=http://localhost:4318
```

## Docker Compose Deployment (Recommended for Testing)

### 1. Build and Run

```bash
# Build and start all services
docker-compose up --build

# Run in background
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### 2. Access the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **OpenTelemetry Collector**: http://localhost:4318 (OTLP HTTP)
- **Prometheus Metrics**: http://localhost:8889

### 3. Customization

Edit `docker-compose.yml` to:
- Change port mappings
- Add additional services (Jaeger, Prometheus, etc.)
- Configure custom networks
- Mount configuration files

## Kubernetes Deployment

### 1. Prerequisites

Ensure you have:
- Kubernetes cluster (v1.19+)
- kubectl configured
- Ingress controller (nginx-ingress recommended)

### 2. Configure Secrets

Update the secret configuration with your actual values:

```bash
# Edit the secret file
nano k8s/secret.yaml

# Replace placeholder values with real ones:
# - your-openai-api-key-here
# - your-aws-access-key-here
# - your-aws-secret-key-here
```

### 3. Deploy with Kustomize

```bash
# Deploy all resources
kubectl apply -k k8s/

# Or deploy individually
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/backend-service.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/frontend-service.yaml
kubectl apply -f k8s/ingress.yaml
```

### 4. Verify Deployment

```bash
# Check namespace
kubectl get namespace otel-demo

# Check all resources
kubectl get all -n otel-demo

# Check pods
kubectl get pods -n otel-demo

# Check services
kubectl get svc -n otel-demo

# Check ingress
kubectl get ingress -n otel-demo
```

### 5. Access the Application

The application will be available at:
- **Development**: http://otel-demo.localhost
- **Production**: Configure your domain in `k8s/ingress.yaml`

### 6. Monitoring

```bash
# View pod logs
kubectl logs -n otel-demo deployment/otel-demo-backend
kubectl logs -n otel-demo deployment/otel-demo-frontend

# Monitor pod status
kubectl get pods -n otel-demo -w

# Debug pod issues
kubectl describe pod -n otel-demo <pod-name>
```

## Building Container Images

### 1. Build Backend Image

```bash
cd backend
docker build -t otel-demo-backend:latest .

# For production, tag with registry
docker tag otel-demo-backend:latest your-registry/otel-demo-backend:v1.0.0
docker push your-registry/otel-demo-backend:v1.0.0
```

### 2. Build Frontend Image

```bash
cd frontend
docker build -t otel-demo-frontend:latest .

# For production, tag with registry
docker tag otel-demo-frontend:latest your-registry/otel-demo-frontend:v1.0.0
docker push your-registry/otel-demo-frontend:v1.0.0
```

### 3. Update Kubernetes Images

Update `k8s/kustomization.yaml` with your image registry:

```yaml
images:
- name: otel-demo-backend
  newName: your-registry/otel-demo-backend
  newTag: v1.0.0
- name: otel-demo-frontend
  newName: your-registry/otel-demo-frontend
  newTag: v1.0.0
```

## Production Considerations

### 1. Security

- Use proper secrets management (e.g., HashiCorp Vault, AWS Secrets Manager)
- Enable RBAC in Kubernetes
- Use network policies for pod-to-pod communication
- Enable TLS/SSL for external access

### 2. Scaling

- Adjust replica counts based on load
- Configure Horizontal Pod Autoscaler (HPA)
- Use resource limits and requests
- Consider using cluster autoscaler

### 3. Monitoring

- Deploy Prometheus and Grafana for metrics
- Use Jaeger or Zipkin for distributed tracing
- Configure log aggregation (ELK stack)
- Set up alerting for critical issues

### 4. Ingress Configuration

For production, configure proper ingress with SSL:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: otel-demo-ingress
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - otel-demo.your-domain.com
    secretName: otel-demo-tls
  rules:
  - host: otel-demo.your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: otel-demo-frontend
            port:
              number: 80
```

## Troubleshooting

### Common Issues

1. **Images not found**
   - Build images locally or push to registry
   - Update image references in Kubernetes manifests

2. **API key not working**
   - Verify secret values are correct
   - Check pod environment variables
   - Ensure API key has proper permissions

3. **Frontend can't reach backend**
   - Verify service names and ports
   - Check network connectivity
   - Review nginx proxy configuration

4. **Ingress not working**
   - Ensure ingress controller is installed
   - Check ingress annotations
   - Verify DNS configuration

### Debugging Commands

```bash
# Check pod logs
kubectl logs -n otel-demo deployment/otel-demo-backend -f

# Execute into pod
kubectl exec -n otel-demo deployment/otel-demo-backend -it -- /bin/bash

# Check service endpoints
kubectl get endpoints -n otel-demo

# Test service connectivity
kubectl run test-pod -n otel-demo --rm -i --tty --image=busybox -- /bin/sh
```

### Health Checks

Both frontend and backend include health check endpoints:

- **Backend**: `GET /` - Returns welcome message
- **Frontend**: `GET /health` - Returns "healthy"

## Advanced Configuration

### 1. Custom Configuration

Create custom ConfigMaps for application-specific settings:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-demo-custom-config
  namespace: otel-demo
data:
  custom-config.yaml: |
    trace_rate: 10
    error_rate: 0.1
    metrics_interval: 30
```

### 2. Persistent Storage

For scenarios requiring persistent storage:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: otel-demo-storage
  namespace: otel-demo
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
```

### 3. Multi-Environment Setup

Use Kustomize overlays for different environments:

```bash
# Create environment-specific overlays
mkdir -p k8s/overlays/staging
mkdir -p k8s/overlays/production

# Deploy to staging
kubectl apply -k k8s/overlays/staging

# Deploy to production
kubectl apply -k k8s/overlays/production
```

## Cleanup

### Docker Compose

```bash
# Stop and remove containers
docker-compose down

# Remove images
docker rmi otel-demo-backend:latest otel-demo-frontend:latest

# Remove volumes
docker-compose down -v
```

### Kubernetes

```bash
# Delete all resources
kubectl delete -k k8s/

# Or delete namespace (removes everything)
kubectl delete namespace otel-demo
```

## Next Steps

1. Configure your observability backend (Jaeger, Elastic, etc.)
2. Set up monitoring and alerting
3. Implement CI/CD pipeline for automated deployments
4. Configure backup and disaster recovery
5. Implement proper logging and monitoring

For more information, see the main README.md file. 