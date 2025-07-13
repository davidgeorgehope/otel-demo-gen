#!/bin/bash

# End-to-end Kubernetes deployment script for OTEL Demo Generator
# This script builds Docker images, pushes them to Docker Hub, and deploys to k8s

set -e  # Exit on any error

# Configuration
DOCKER_REGISTRY="djhope99"
BACKEND_IMAGE="$DOCKER_REGISTRY/otel-demo-backend"
FRONTEND_IMAGE="$DOCKER_REGISTRY/otel-demo-frontend"
NAMESPACE="otel-demo"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if required tools are installed
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing_tools=()
    
    if ! command -v docker &> /dev/null; then
        missing_tools+=("docker")
    fi
    
    if ! command -v kubectl &> /dev/null; then
        missing_tools+=("kubectl")
    fi
    

    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_error "Please install the missing tools and run this script again."
        exit 1
    fi
    
    log_success "All prerequisites are installed"
}

# Function to check Docker login
check_docker_login() {
    log_info "Checking Docker Hub authentication..."
    
    if ! docker info | grep -q "Username:"; then
        log_warning "Not logged in to Docker Hub. Please login:"
        docker login
    fi
    
    log_success "Docker Hub authentication verified"
}

# Function to build Docker images
build_images() {
    log_info "Building Docker images..."
    
    # Get current git commit hash for tagging
    GIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    VERSION_TAG="$TIMESTAMP-$GIT_HASH"
    
    # Build backend image
    log_info "Building backend image..."
    docker build -t "$BACKEND_IMAGE:latest" -t "$BACKEND_IMAGE:$VERSION_TAG" "$PROJECT_ROOT/backend"
    
    # Build frontend image
    log_info "Building frontend image..."
    docker build -t "$FRONTEND_IMAGE:latest" -t "$FRONTEND_IMAGE:$VERSION_TAG" "$PROJECT_ROOT/frontend"
    
    log_success "Docker images built successfully"
    log_info "Images tagged with: latest, $VERSION_TAG"
}

# Function to push Docker images
push_images() {
    log_info "Pushing Docker images to Docker Hub..."
    
    # Push backend image
    log_info "Pushing backend image..."
    docker push "$BACKEND_IMAGE:latest"
    docker push "$BACKEND_IMAGE:$VERSION_TAG"
    
    # Push frontend image
    log_info "Pushing frontend image..."
    docker push "$FRONTEND_IMAGE:latest"
    docker push "$FRONTEND_IMAGE:$VERSION_TAG"
    
    log_success "Docker images pushed successfully"
}

# Function to check Kubernetes cluster connectivity
check_k8s_connection() {
    log_info "Checking Kubernetes cluster connectivity..."
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Unable to connect to Kubernetes cluster"
        log_error "Please ensure your kubectl is configured and cluster is accessible"
        exit 1
    fi
    
    CLUSTER_NAME=$(kubectl config current-context)
    log_success "Connected to Kubernetes cluster: $CLUSTER_NAME"
}

# Function to deploy to Kubernetes
deploy_to_k8s() {
    log_info "Deploying to Kubernetes..."
    
    # Apply the Kubernetes manifests
    log_info "Applying Kubernetes manifests..."
    
    # Apply in specific order to handle dependencies
    kubectl apply -f "$PROJECT_ROOT/k8s/namespace.yaml"
    kubectl apply -f "$PROJECT_ROOT/k8s/secret.yaml"
    kubectl apply -f "$PROJECT_ROOT/k8s/configmap.yaml"
    kubectl apply -f "$PROJECT_ROOT/k8s/backend-deployment.yaml"
    kubectl apply -f "$PROJECT_ROOT/k8s/backend-service.yaml"
    kubectl apply -f "$PROJECT_ROOT/k8s/frontend-deployment.yaml"
    kubectl apply -f "$PROJECT_ROOT/k8s/frontend-service.yaml"
    
    # Wait for deployments to be ready
    log_info "Waiting for deployments to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/otel-demo-backend -n $NAMESPACE
    kubectl wait --for=condition=available --timeout=300s deployment/otel-demo-frontend -n $NAMESPACE
    
    log_success "Kubernetes deployment completed successfully"
}

# Function to display deployment status
show_deployment_status() {
    log_info "Deployment Status:"
    echo ""
    
    # Show pods
    echo "Pods:"
    kubectl get pods -n $NAMESPACE -o wide
    echo ""
    
    # Show services
    echo "Services:"
    kubectl get services -n $NAMESPACE -o wide
    echo ""
    
    # Show deployment status
    echo "Deployments:"
    kubectl get deployments -n $NAMESPACE -o wide
    echo ""
    
    # Get service access information
    get_service_access_info
}

# Function to get service access information
get_service_access_info() {
    log_info "Service Access Information:"
    
    # Check if services are LoadBalancer type
    BACKEND_SERVICE_TYPE=$(kubectl get service otel-demo-backend -n $NAMESPACE -o jsonpath='{.spec.type}' 2>/dev/null || echo "Unknown")
    FRONTEND_SERVICE_TYPE=$(kubectl get service otel-demo-frontend -n $NAMESPACE -o jsonpath='{.spec.type}' 2>/dev/null || echo "Unknown")
    
    if [ "$BACKEND_SERVICE_TYPE" = "LoadBalancer" ] || [ "$FRONTEND_SERVICE_TYPE" = "LoadBalancer" ]; then
        log_info "Waiting for LoadBalancer external IPs (this may take a few minutes)..."
        
        # Wait for external IPs to be assigned
        local max_wait=300  # 5 minutes
        local wait_time=0
        
        while [ $wait_time -lt $max_wait ]; do
            BACKEND_EXTERNAL_IP=$(kubectl get service otel-demo-backend -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
            FRONTEND_EXTERNAL_IP=$(kubectl get service otel-demo-frontend -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
            
            # Also check for hostname (some cloud providers use hostname instead of IP)
            if [ -z "$BACKEND_EXTERNAL_IP" ]; then
                BACKEND_EXTERNAL_IP=$(kubectl get service otel-demo-backend -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
            fi
            
            if [ -z "$FRONTEND_EXTERNAL_IP" ]; then
                FRONTEND_EXTERNAL_IP=$(kubectl get service otel-demo-frontend -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
            fi
            
            if [ -n "$BACKEND_EXTERNAL_IP" ] && [ -n "$FRONTEND_EXTERNAL_IP" ]; then
                break
            fi
            
            echo "  Still waiting for external IPs... ($wait_time/${max_wait}s)"
            sleep 10
            wait_time=$((wait_time + 10))
        done
        
        if [ -n "$BACKEND_EXTERNAL_IP" ] && [ -n "$FRONTEND_EXTERNAL_IP" ]; then
            log_success "LoadBalancer services are ready!"
            echo "  Backend:  http://$BACKEND_EXTERNAL_IP:8000"
            echo "  Frontend: http://$FRONTEND_EXTERNAL_IP:80"
            echo ""
            log_info "API Health Check:"
            echo "  curl http://$BACKEND_EXTERNAL_IP:8000/"
            echo ""
            log_info "To monitor external IPs:"
            echo "  kubectl get services -n $NAMESPACE -w"
        else
            log_warning "LoadBalancer external IPs not yet available after ${max_wait}s"
            echo "  This is normal for some cloud providers - external IPs may take longer to provision"
            echo "  Check status with: kubectl get services -n $NAMESPACE -w"
            echo ""
            echo "  Current service status:"
            kubectl get services -n $NAMESPACE
        fi
    else
        echo "  Services are using ClusterIP. Use port-forwarding to access:"
        echo "  Backend:  kubectl port-forward service/otel-demo-backend 8000:8000 -n $NAMESPACE"
        echo "  Frontend: kubectl port-forward service/otel-demo-frontend 5173:80 -n $NAMESPACE"
    fi
}

# Function to setup port forwarding for local access (fallback for non-LoadBalancer)
setup_port_forwarding() {
    # Check if services are LoadBalancer type
    BACKEND_SERVICE_TYPE=$(kubectl get service otel-demo-backend -n $NAMESPACE -o jsonpath='{.spec.type}' 2>/dev/null || echo "Unknown")
    FRONTEND_SERVICE_TYPE=$(kubectl get service otel-demo-frontend -n $NAMESPACE -o jsonpath='{.spec.type}' 2>/dev/null || echo "Unknown")
    
    if [ "$BACKEND_SERVICE_TYPE" = "LoadBalancer" ] || [ "$FRONTEND_SERVICE_TYPE" = "LoadBalancer" ]; then
        log_info "Services are configured as LoadBalancer - external access should be available directly"
        log_info "Run './scripts/deploy.sh status' to check external IP addresses"
        return 0
    fi
    
    log_info "Setting up port forwarding for local access..."
    
    # Kill existing port-forward processes
    pkill -f "kubectl port-forward.*otel-demo" 2>/dev/null || true
    
    # Start port forwarding in background
    kubectl port-forward service/otel-demo-backend 8000:8000 -n $NAMESPACE &
    kubectl port-forward service/otel-demo-frontend 5173:80 -n $NAMESPACE &
    
    sleep 2
    
    log_success "Port forwarding established:"
    log_info "  Backend:  http://localhost:8000"
    log_info "  Frontend: http://localhost:5173"
    log_info "  Use 'pkill -f \"kubectl port-forward.*otel-demo\"' to stop port forwarding"
}

# Function to cleanup deployment
cleanup_deployment() {
    log_info "Cleaning up deployment..."
    
    # Delete in reverse order (deployments first, then supporting resources)
    kubectl delete -f "$PROJECT_ROOT/k8s/frontend-service.yaml" --ignore-not-found=true
    kubectl delete -f "$PROJECT_ROOT/k8s/frontend-deployment.yaml" --ignore-not-found=true
    kubectl delete -f "$PROJECT_ROOT/k8s/backend-service.yaml" --ignore-not-found=true
    kubectl delete -f "$PROJECT_ROOT/k8s/backend-deployment.yaml" --ignore-not-found=true
    kubectl delete -f "$PROJECT_ROOT/k8s/configmap.yaml" --ignore-not-found=true
    kubectl delete -f "$PROJECT_ROOT/k8s/secret.yaml" --ignore-not-found=true
    kubectl delete -f "$PROJECT_ROOT/k8s/namespace.yaml" --ignore-not-found=true
    
    log_success "Deployment cleanup completed"
}

# Function to show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

End-to-end Kubernetes deployment script for OTEL Demo Generator

 OPTIONS:
     deploy          Full deployment (build, push, deploy) [default]
     build           Build Docker images only
     push            Push Docker images only (requires build first)
     k8s             Deploy to Kubernetes only (requires images in registry)
     status          Show deployment status and external IPs
     port-forward    Setup port forwarding (fallback for non-LoadBalancer)
     cleanup         Remove deployment from Kubernetes
     help            Show this help message

EXAMPLES:
    $0                    # Full deployment
    $0 deploy             # Full deployment
    $0 build              # Build images only
    $0 push               # Push images only
    $0 k8s                # Deploy to k8s only
    $0 status             # Show deployment status
    $0 port-forward       # Setup port forwarding
    $0 cleanup            # Remove deployment

 PREREQUISITES:
     - Docker installed and logged in to Docker Hub
     - kubectl configured with cluster access
     - Git (for version tagging)
     - Cloud provider LoadBalancer support (AWS ELB, GCP LB, Azure LB, etc.)

 NOTES:
     - Services are configured as LoadBalancer type for external access
     - External IP assignment may take 2-5 minutes depending on cloud provider
     - Use 'kubectl get services -n otel-demo -w' to monitor IP assignment

EOF
}

# Main execution
main() {
    local action=${1:-deploy}
    
    case $action in
                 deploy)
             check_prerequisites
             check_docker_login
             check_k8s_connection
             build_images
             push_images
             deploy_to_k8s
             show_deployment_status
             ;;
        build)
            check_prerequisites
            build_images
            ;;
        push)
            check_prerequisites
            check_docker_login
            push_images
            ;;
        k8s)
            check_prerequisites
            check_k8s_connection
            deploy_to_k8s
            show_deployment_status
            ;;
        status)
            check_prerequisites
            check_k8s_connection
            show_deployment_status
            ;;
        port-forward)
            check_prerequisites
            check_k8s_connection
            setup_port_forwarding
            ;;
        cleanup)
            check_prerequisites
            check_k8s_connection
            cleanup_deployment
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown action: $action"
            show_help
            exit 1
            ;;
    esac
}

# Execute main function with all arguments
main "$@" 