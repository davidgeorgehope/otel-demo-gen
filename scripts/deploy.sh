#!/bin/bash

# AI-Powered Observability Demo Generator Deployment Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
DEPLOYMENT_TYPE="docker-compose"
ENVIRONMENT="local"
NAMESPACE="otel-demo"
IMAGE_TAG="latest"
REGISTRY=""

# Help function
show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -t, --type TYPE         Deployment type: docker-compose, kubernetes (default: docker-compose)"
    echo "  -e, --env ENV           Environment: local, staging, production (default: local)"
    echo "  -n, --namespace NS      Kubernetes namespace (default: otel-demo)"
    echo "  -i, --image-tag TAG     Image tag (default: latest)"
    echo "  -r, --registry REG      Container registry URL"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Deploy with Docker Compose (default)"
    echo "  $0 -t kubernetes                     # Deploy to Kubernetes"
    echo "  $0 -t kubernetes -e production       # Deploy to Kubernetes production"
    echo "  $0 -t docker-compose -e local        # Deploy locally with Docker Compose"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--type)
            DEPLOYMENT_TYPE="$2"
            shift 2
            ;;
        -e|--env)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -i|--image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        if ! command -v docker &> /dev/null; then
            log_error "Docker is not installed or not in PATH"
            exit 1
        fi
        
        if ! command -v docker-compose &> /dev/null; then
            log_error "Docker Compose is not installed or not in PATH"
            exit 1
        fi
    fi
    
    if [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        if ! command -v kubectl &> /dev/null; then
            log_error "kubectl is not installed or not in PATH"
            exit 1
        fi
        
        if ! kubectl cluster-info &> /dev/null; then
            log_error "kubectl is not configured or cluster is not reachable"
            exit 1
        fi
    fi
    
    log_info "Prerequisites check passed"
}

# Check environment variables
check_env_vars() {
    log_info "Checking environment variables..."
    
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        log_info "Found .env file"
        source "$PROJECT_DIR/.env"
    else
        log_warn ".env file not found. Using environment variables from shell"
    fi
    
    if [[ -z "$OPENAI_API_KEY" ]] && [[ -z "$AWS_ACCESS_KEY_ID" ]]; then
        log_warn "Neither OPENAI_API_KEY nor AWS_ACCESS_KEY_ID is set"
        log_warn "The application will work but config generation will fail"
    fi
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."
    
    cd "$PROJECT_DIR"
    
    # Build backend
    log_info "Building backend image..."
    docker build -t otel-demo-backend:${IMAGE_TAG} backend/
    
    # Build frontend
    log_info "Building frontend image..."
    docker build -t otel-demo-frontend:${IMAGE_TAG} frontend/
    
    # Tag and push if registry is provided
    if [[ -n "$REGISTRY" ]]; then
        log_info "Tagging and pushing images to registry..."
        
        docker tag otel-demo-backend:${IMAGE_TAG} ${REGISTRY}/otel-demo-backend:${IMAGE_TAG}
        docker tag otel-demo-frontend:${IMAGE_TAG} ${REGISTRY}/otel-demo-frontend:${IMAGE_TAG}
        
        docker push ${REGISTRY}/otel-demo-backend:${IMAGE_TAG}
        docker push ${REGISTRY}/otel-demo-frontend:${IMAGE_TAG}
    fi
    
    log_info "Docker images built successfully"
}

# Deploy with Docker Compose
deploy_docker_compose() {
    log_info "Deploying with Docker Compose..."
    
    cd "$PROJECT_DIR"
    
    # Stop existing containers
    docker-compose down 2>/dev/null || true
    
    # Start services
    docker-compose up -d --build
    
    log_info "Waiting for services to start..."
    sleep 10
    
    # Check if services are running
    if docker-compose ps | grep -q "Up"; then
        log_info "Services started successfully"
        echo ""
        log_info "Application URLs:"
        log_info "  Frontend: http://localhost:3000"
        log_info "  Backend API: http://localhost:8000"
        log_info "  OTLP Collector: http://localhost:4318"
        echo ""
        log_info "View logs: docker-compose logs -f"
        log_info "Stop services: docker-compose down"
    else
        log_error "Failed to start services"
        docker-compose logs
        exit 1
    fi
}

# Deploy to Kubernetes
deploy_kubernetes() {
    log_info "Deploying to Kubernetes..."
    
    cd "$PROJECT_DIR"
    
    # Update image references if registry is provided
    if [[ -n "$REGISTRY" ]]; then
        log_info "Updating image references in Kubernetes manifests..."
        
        # Create a temporary kustomization file
        cat > k8s/kustomization-temp.yaml << EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- namespace.yaml
- secret.yaml
- configmap.yaml
- backend-deployment.yaml
- backend-service.yaml
- frontend-deployment.yaml
- frontend-service.yaml
- ingress.yaml

commonLabels:
  app: otel-demo-generator
  version: ${IMAGE_TAG}
  environment: ${ENVIRONMENT}

namespace: ${NAMESPACE}

images:
- name: otel-demo-backend
  newName: ${REGISTRY}/otel-demo-backend
  newTag: ${IMAGE_TAG}
- name: otel-demo-frontend
  newName: ${REGISTRY}/otel-demo-frontend
  newTag: ${IMAGE_TAG}
EOF
        
        # Deploy with temporary kustomization
        kubectl apply -k k8s/ -f k8s/kustomization-temp.yaml
        
        # Clean up temporary file
        rm k8s/kustomization-temp.yaml
    else
        # Deploy with default kustomization
        kubectl apply -k k8s/
    fi
    
    log_info "Waiting for deployment to complete..."
    kubectl wait --for=condition=available --timeout=300s deployment/otel-demo-backend -n ${NAMESPACE}
    kubectl wait --for=condition=available --timeout=300s deployment/otel-demo-frontend -n ${NAMESPACE}
    
    log_info "Deployment completed successfully"
    echo ""
    log_info "Checking deployment status:"
    kubectl get pods -n ${NAMESPACE}
    echo ""
    
    # Get ingress info
    if kubectl get ingress -n ${NAMESPACE} &> /dev/null; then
        log_info "Ingress information:"
        kubectl get ingress -n ${NAMESPACE}
        echo ""
    fi
    
    log_info "Useful commands:"
    log_info "  View pods: kubectl get pods -n ${NAMESPACE}"
    log_info "  View logs: kubectl logs -n ${NAMESPACE} deployment/otel-demo-backend"
    log_info "  Delete deployment: kubectl delete -k k8s/"
}

# Main execution
main() {
    echo "AI-Powered Observability Demo Generator Deployment Script"
    echo "=========================================================="
    echo ""
    log_info "Deployment type: $DEPLOYMENT_TYPE"
    log_info "Environment: $ENVIRONMENT"
    log_info "Image tag: $IMAGE_TAG"
    if [[ -n "$REGISTRY" ]]; then
        log_info "Registry: $REGISTRY"
    fi
    echo ""
    
    check_prerequisites
    check_env_vars
    build_images
    
    case $DEPLOYMENT_TYPE in
        docker-compose)
            deploy_docker_compose
            ;;
        kubernetes)
            deploy_kubernetes
            ;;
        *)
            log_error "Invalid deployment type: $DEPLOYMENT_TYPE"
            show_help
            exit 1
            ;;
    esac
    
    echo ""
    log_info "Deployment completed successfully! 🎉"
}

# Run main function
main "$@" 