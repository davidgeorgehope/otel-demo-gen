# OTEL Demo Helm Chart

This Helm chart deploys the OTEL Demo Generator (backend and frontend) to Kubernetes, templating all configuration, secrets, and resources.

## Prerequisites

- Kubernetes cluster (with LoadBalancer support for external access, or use port-forwarding)
- Helm 3.x installed

## Installation

1. **Clone this repository and navigate to the `helm/` directory:**

   ```sh
   cd helm
   ```

2. **Install the chart:**

   ```sh
   helm install otel-demo-gen . --namespace otel-demo-gen --create-namespace
   ```

3. **Customize values:**

   Edit `values.yaml` or override values on the command line:

   ```sh
   helm install otel-demo-gen . \
     --namespace otel-demo-gen \
     --set backend.image.tag=latest \
     --set secrets.awsAccessKeyId=xxx \
     --set secrets.awsSecretAccessKey=xxx \
     --set secrets.awsRegion=xxx
   ```

## Configuration

All configuration is in [`values.yaml`](values.yaml). Key fields:

- `namespace`: Namespace to deploy into
- `backend`/`frontend`: Image, tag, replicas, resources
- `config`: LLM provider, model, log level, CORS, etc.
- `secrets`: API keys, AWS credentials, OTEL collector URL
- `service.type`: LoadBalancer or ClusterIP

## Uninstall

```sh
helm uninstall otel-demo --namespace otel-demo
```

## Notes

- Wait for deployments to be ready:
  `kubectl wait --for=condition=available --timeout=300s deployment/otel-demo-backend -n otel-demo`
- For local clusters without LoadBalancer, use port-forwarding:
  ```sh
  kubectl port-forward service/otel-demo-backend 8000:8000 -n otel-demo &
  kubectl port-forward service/otel-demo-frontend 5173:80 -n otel-demo &
  ```
