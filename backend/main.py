import yaml
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Response, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, List
from pydantic import BaseModel
import os

from config_schema import GenerateConfigRequest, StartDemoRequest, ScenarioConfig
from generator import TelemetryGenerator
from llm_config_gen import generate_config_from_description

app = FastAPI(
    title="AI-Powered Observability Demo Generator",
    description="An API to generate and control a synthetic telemetry stream based on user-defined scenarios.",
    version="0.1.0",
)

# Allow CORS for the frontend application
# Make sure the port matches your frontend's dev server port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job management system - replace global singleton with multi-job support
class JobInfo(BaseModel):
    id: str
    description: str
    created_at: datetime
    config: dict
    status: str = "running"
    otlp_endpoint: Optional[str] = None

# Global job storage and active generators
active_jobs: Dict[str, JobInfo] = {}
active_generators: Dict[str, TelemetryGenerator] = {}

# --- Models ---
class GenerateRequest(BaseModel):
    description: str

class StartRequest(BaseModel):
    config: dict
    description: str = "Telemetry Generation Job"
    otlp_endpoint: Optional[str] = None
    api_key: Optional[str] = None

class JobResponse(BaseModel):
    id: str
    description: str
    created_at: datetime
    config: dict
    status: str
    otlp_endpoint: Optional[str] = None

class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int

class StatusResponse(BaseModel):
    running: bool
    config: Optional[dict] = None
    job_id: Optional[str] = None

@app.post("/generate-config", response_model=dict)
async def generate_config(request: GenerateRequest):
    """
    Generates a scenario configuration from a user description using an LLM.
    """
    try:
        yaml_config_str = generate_config_from_description(request.description)
        # Validate that the output is valid YAML
        config_dict = yaml.safe_load(yaml_config_str)
        return {"yaml": yaml_config_str, "config": config_dict}
    except ValueError as e:
        # Handle missing API keys or configuration errors
        error_message = str(e)
        if "OpenAI API key not found" in error_message:
            raise HTTPException(
                status_code=400, 
                detail="OpenAI API key not configured. Please set the OPENAI_API_KEY environment variable."
            )
        elif "AWS credentials not found" in error_message:
            raise HTTPException(
                status_code=400,
                detail="AWS credentials not configured. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
            )
        elif "Unsupported LLM provider" in error_message:
            raise HTTPException(
                status_code=400,
                detail="Invalid LLM provider. Please set LLM_PROVIDER to 'openai' or 'bedrock'."
            )
        else:
            raise HTTPException(status_code=500, detail=f"Configuration error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate config: {e}")

@app.post("/start", response_model=dict)
async def start_generation(request: StartRequest):
    """
    Starts a new telemetry generator job with a given configuration.
    """
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())[:8]
        
        # Validate configuration
        scenario_config = ScenarioConfig(**request.config)
        
        # Create and start generator
        generator = TelemetryGenerator(
            config=scenario_config,
            otlp_endpoint=request.otlp_endpoint,
            api_key=request.api_key
        )
        
        # Store job info
        job_info = JobInfo(
            id=job_id,
            description=request.description,
            created_at=datetime.now(),
            config=request.config,
            status="running",
            otlp_endpoint=request.otlp_endpoint
        )
        
        active_jobs[job_id] = job_info
        active_generators[job_id] = generator
        
        # Start the generator
        generator.start()
        
        return {
            "status": "started",
            "job_id": job_id,
            "description": request.description,
            "created_at": job_info.created_at.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start generator: {e}")

@app.post("/stop/{job_id}")
async def stop_generation(job_id: str):
    """
    Stops a specific telemetry generator job.
    """
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    if job_id not in active_generators:
        raise HTTPException(status_code=400, detail=f"Job {job_id} is not running")
    
    try:
        # Stop the generator
        generator = active_generators[job_id]
        generator.stop()
        
        # Update job status
        active_jobs[job_id].status = "stopped"
        
        # Remove from active generators
        del active_generators[job_id]
        
        return {"status": "stopped", "job_id": job_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop generator: {e}")

@app.get("/jobs", response_model=JobListResponse)
async def list_jobs():
    """
    Returns a list of all jobs (running and stopped).
    """
    # Update status for any generators that may have stopped
    for job_id, generator in list(active_generators.items()):
        if not generator.is_running():
            active_jobs[job_id].status = "stopped"
            del active_generators[job_id]
    
    job_responses = [
        JobResponse(
            id=job.id,
            description=job.description,
            created_at=job.created_at,
            config=job.config,
            status=job.status,
            otlp_endpoint=job.otlp_endpoint
        )
        for job in active_jobs.values()
    ]
    
    return JobListResponse(jobs=job_responses, total=len(job_responses))

@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """
    Returns details for a specific job.
    """
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    job = active_jobs[job_id]
    
    # Update status if generator stopped
    if job_id in active_generators and not active_generators[job_id].is_running():
        job.status = "stopped"
        del active_generators[job_id]
    
    return JobResponse(
        id=job.id,
        description=job.description,
        created_at=job.created_at,
        config=job.config,
        status=job.status,
        otlp_endpoint=job.otlp_endpoint
    )

@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """
    Deletes a job from the system. Stops it first if it's running.
    """
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    # Stop the job if it's running
    if job_id in active_generators:
        generator = active_generators[job_id]
        generator.stop()
        del active_generators[job_id]
    
    # Remove from jobs
    del active_jobs[job_id]
    
    return {"status": "deleted", "job_id": job_id}

# Legacy endpoints for backward compatibility
@app.post("/stop")
async def stop_generation_legacy():
    """
    Legacy endpoint - stops the most recent job for backward compatibility.
    """
    if not active_jobs:
        raise HTTPException(status_code=400, detail="No jobs are running")
    
    # Find the most recent job
    most_recent_job_id = max(active_jobs.keys(), key=lambda x: active_jobs[x].created_at)
    
    return await stop_generation(most_recent_job_id)

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Legacy endpoint - returns status of the most recent job for backward compatibility.
    """
    if not active_jobs:
        return StatusResponse(running=False, config=None, job_id=None)
    
    # Find the most recent job
    most_recent_job_id = max(active_jobs.keys(), key=lambda x: active_jobs[x].created_at)
    most_recent_job = active_jobs[most_recent_job_id]
    
    # Check if it's actually running
    is_running = (most_recent_job_id in active_generators and 
                 active_generators[most_recent_job_id].is_running())
    
    if not is_running and most_recent_job.status == "running":
        most_recent_job.status = "stopped"
        if most_recent_job_id in active_generators:
            del active_generators[most_recent_job_id]
    
    return StatusResponse(
        running=is_running,
        config=most_recent_job.config if is_running else None,
        job_id=most_recent_job_id
    )

@app.get("/test-config", response_model=dict)
async def get_test_config():
    """
    Returns a sample configuration for testing without requiring LLM generation.
    """
    test_config = {
        "services": [
            {
                "name": "web-frontend",
                "language": "typescript",
                "role": "frontend",
                "operations": [
                    {
                        "name": "LoadHomePage",
                        "span_name": "GET /",
                        "business_data": [
                            {"name": "user_id", "type": "string", "pattern": "user_{random}"},
                            {"name": "session_id", "type": "string", "pattern": "session_{uuid}"}
                        ]
                    }
                ],
                "depends_on": [
                    {"service": "api-gateway", "protocol": "http", "latency": {"min_ms": 10, "max_ms": 50}}
                ]
            },
            {
                "name": "api-gateway",
                "language": "java",
                "role": "backend",
                "operations": [
                    {
                        "name": "RouteRequest",
                        "span_name": "POST /api/v1/route",
                        "business_data": [
                            {"name": "request_id", "type": "string", "pattern": "req_{uuid}"},
                            {"name": "route_match", "type": "boolean"}
                        ]
                    }
                ],
                "depends_on": [
                    {"service": "user-service", "protocol": "http", "latency": {"min_ms": 5, "max_ms": 25}},
                    {"cache": "redis-cache"}
                ]
            },
            {
                "name": "user-service",
                "language": "python",
                "role": "backend",
                "operations": [
                    {
                        "name": "GetUserProfile",
                        "span_name": "GET /users/{id}",
                        "db_queries": ["SELECT * FROM users WHERE id = ?"],
                        "business_data": [
                            {"name": "user_id", "type": "string", "pattern": "user_{random}"},
                            {"name": "profile_loaded", "type": "boolean"}
                        ]
                    }
                ],
                "depends_on": [
                    {"db": "postgres-main", "example_queries": ["SELECT * FROM users WHERE id = ?"], "latency": {"min_ms": 2, "max_ms": 100, "probability": 0.1}}
                ]
            }
        ],
        "databases": [
            {"name": "postgres-main", "type": "postgres"}
        ],
        "message_queues": [
            {"name": "kafka-events", "type": "kafka"}
        ],
        "telemetry": {
            "trace_rate": 3,
            "error_rate": 0.05,
            "metrics_interval": 10,
            "include_logs": True
        }
    }
    
    # Convert to YAML string for consistency with generate-config endpoint
    import yaml
    yaml_config_str = yaml.dump(test_config, default_flow_style=False)
    
    return {"yaml": yaml_config_str, "config": test_config}

@app.get("/llm-config", response_model=dict)
async def get_llm_config():
    """
    Returns information about the current LLM provider configuration.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    config_status = {
        "provider": provider,
        "configured": False,
        "model": None,
        "details": {}
    }
    
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        config_status["configured"] = bool(api_key)
        config_status["model"] = model
        config_status["details"] = {
            "api_key_set": bool(api_key),
            "model": model
        }
    elif provider == "bedrock":
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_region = os.getenv("AWS_REGION", "us-east-1")
        model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
        
        config_status["configured"] = bool(aws_access_key and aws_secret_key)
        config_status["model"] = model_id
        config_status["details"] = {
            "aws_access_key_set": bool(aws_access_key),
            "aws_secret_key_set": bool(aws_secret_key),
            "aws_region": aws_region,
            "model_id": model_id
        }
    else:
        config_status["details"]["error"] = f"Unsupported provider: {provider}"
    
    return config_status

@app.get("/", summary="Root endpoint for health check")
async def read_root():
    return {"message": "Welcome to the Telemetry Demo Generator API"} 