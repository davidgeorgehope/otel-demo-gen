import uuid
import re
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Response, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, List, Literal
from pydantic import BaseModel, ValidationError
import os
import asyncio
import threading
import time
import httpx
import json
import queue
import logging
from dataclasses import dataclass, field

from config_schema import GenerateConfigRequest, StartDemoRequest, ScenarioConfig, ScenarioGenerationRequest, ScenarioApplyRequest, ActiveScenario, ScenarioModification
from generator import TelemetryGenerator
from llm_config_gen import generate_config_from_description
from scenario_llm_gen import generate_scenario_from_description, get_predefined_templates


logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI-Powered Observability Demo Generator",
    description="An API to generate and control a synthetic telemetry stream based on user-defined scenarios.",
    version=os.getenv("APP_VERSION", "dev"),
)

# Version information
# Version information
APP_VERSION = os.getenv("APP_VERSION", "dev")

# Allow CORS for the frontend application
# Make sure the port matches your frontend's dev server port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job Management Configuration - Environment configurable with sensible defaults
MAX_ACTIVE_JOBS = int(os.getenv("MAX_ACTIVE_JOBS", "50"))  # Maximum total active jobs
MAX_JOBS_PER_USER = int(os.getenv("MAX_JOBS_PER_USER", "3"))  # Maximum jobs per user
MAX_JOB_DURATION_HOURS = int(os.getenv("MAX_JOB_DURATION_HOURS", "24"))  # Maximum job runtime
JOB_CLEANUP_HOURS = int(os.getenv("JOB_CLEANUP_HOURS", "24"))  # How long to keep stopped jobs
CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "15"))  # Cleanup frequency
CONFIG_JOB_TTL_MINUTES = int(os.getenv("CONFIG_JOB_TTL_MINUTES", "60"))  # Retain finished config jobs
CONFIG_GENERATION_WORKERS = int(os.getenv("CONFIG_GENERATION_WORKERS", "1"))  # Background workers
MAX_CONFIG_GENERATION_ATTEMPTS = int(os.getenv("CONFIG_GENERATION_MAX_ATTEMPTS", "3"))  # Total attempts per job

# Job management system - replace global singleton with multi-job support
class JobInfo(BaseModel):
    id: str
    description: str
    created_at: datetime
    config: dict
    status: str = "running"  # "running", "stopped", "failed"
    otlp_endpoint: Optional[str] = None
    user: Optional[str] = "Not logged in"
    timeout_at: Optional[datetime] = None  # When the job should be automatically stopped
    error_message: Optional[str] = None  # Error details if job failed
    failure_count: int = 0  # Number of consecutive OTLP failures

# Global job storage and active generators
active_jobs: Dict[str, JobInfo] = {}
active_generators: Dict[str, TelemetryGenerator] = {}

# Global scenario storage
active_scenarios: Dict[str, ActiveScenario] = {}  # scenario_id -> ActiveScenario

# Cleanup tracking
cleanup_thread: Optional[threading.Thread] = None
cleanup_stop_event = threading.Event()


@dataclass
class ConfigGenerationJob:
    id: str
    description: str
    status: Literal["pending", "running", "succeeded", "failed"] = "pending"
    config_json: Optional[str] = None
    config: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    attempts: int = 0
    max_attempts: int = 1
    last_error: Optional[str] = None
    last_response: Optional[str] = None
    user: Optional[str] = "Not logged in"


config_jobs: Dict[str, ConfigGenerationJob] = {}
config_jobs_lock = threading.Lock()
config_job_queue: queue.Queue = queue.Queue()
config_worker_threads: List[threading.Thread] = []
config_worker_stop_event = threading.Event()

def _extract_json_content(raw_text: str) -> str:
    """Strip code fences and isolate the JSON object emitted by the LLM."""
    if not raw_text:
        return raw_text

    text = raw_text.strip()

    # Remove Markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Trim any leading language labels like `json` that may remain after fences
    if text.lower().startswith("json\n"):
        text = text[5:].lstrip()

    # Attempt to isolate the JSON object/array boundaries
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end >= start:
        text = text[start:end + 1]

    return text

def _build_retry_prompt(description: str, last_error: Optional[str], previous_output: Optional[str]) -> str:
    """Create a prompt that feeds the previous error/output back to the LLM."""
    guidance_parts = [
        description.strip(),
        "\nThe previous JSON output failed to parse with the following error:",
        last_error or "Unknown validation error.",
        "\nIMPORTANT: Please ensure all string values in log messages are properly quoted and escaped.",
        "\nSpecifically:",
        "- Emit valid JSON (double quotes, no trailing commas)",
        "- Escape any internal quotes with backslash (\\\")",
        "- Ensure arrays and objects are properly closed",
        "\nPlease regenerate a corrected configuration as pure JSON (no code fences)."
    ]

    if previous_output:
        guidance_parts.extend([
            "\nPrevious JSON output for reference:",
            "```json",
            previous_output.strip(),
            "```",
            "\nCorrect the issues and ensure the JSON satisfies the previously provided requirements."
        ])

    return "\n".join(guidance_parts)


def config_generation_worker():
    """Worker that processes config generation jobs asynchronously."""
    while not config_worker_stop_event.is_set():
        try:
            job_id = config_job_queue.get(timeout=1)
        except queue.Empty:
            continue

        if job_id is None:
            config_job_queue.task_done()
            continue

        with config_jobs_lock:
            job = config_jobs.get(job_id)
            if not job:
                config_job_queue.task_done()
                continue
            job.status = "running"
            job.updated_at = datetime.utcnow()

        success = False
        last_error: Optional[str] = None
        last_response: Optional[str] = None

        for attempt_index in range(job.max_attempts):
            with config_jobs_lock:
                job.attempts = attempt_index + 1
                job.updated_at = datetime.utcnow()

            prompt = job.description
            if attempt_index > 0:
                prompt = _build_retry_prompt(job.description, last_error, last_response)

            try:
                raw_config_str = generate_config_from_description(prompt) or ""
                raw_config_str = raw_config_str.strip()
                normalized_json = _extract_json_content(raw_config_str) or raw_config_str
                last_response = raw_config_str  # Store original for debugging

                try:
                    config_dict = json.loads(normalized_json)
                except json.JSONDecodeError as decode_err:
                    last_error = f"JSON decoding error: {decode_err}"
                    with config_jobs_lock:
                        job.last_error = last_error
                        job.last_response = raw_config_str
                        job.updated_at = datetime.utcnow()
                    logger.warning(
                        "Config job %s attempt %d/%d JSON decode error: %s | preview=%s",
                        job_id,
                        attempt_index + 1,
                        job.max_attempts,
                        decode_err,
                        (raw_config_str[:800] + "...[truncated]") if raw_config_str and len(raw_config_str) > 800 else raw_config_str
                    )
                    continue

                try:
                    scenario_model = ScenarioConfig(**config_dict)
                    validated_config = scenario_model.model_dump()
                except ValidationError as validation_err:
                    last_error = f"Schema validation error: {validation_err}"
                    with config_jobs_lock:
                        job.last_error = last_error
                        job.last_response = raw_config_str
                        job.updated_at = datetime.utcnow()
                    logger.warning(
                        "Config job %s attempt %d/%d schema validation error: %s | preview=%s",
                        job_id,
                        attempt_index + 1,
                        job.max_attempts,
                        validation_err,
                        (raw_config_str[:800] + "...[truncated]") if raw_config_str and len(raw_config_str) > 800 else raw_config_str
                    )
                    continue

                pretty_json = json.dumps(validated_config, indent=2)

                with config_jobs_lock:
                    job.config_json = pretty_json
                    job.config = validated_config
                    job.status = "succeeded"
                    job.error_message = None
                    job.last_error = None
                    job.last_response = raw_config_str
                    job.updated_at = datetime.utcnow()
                success = True
                break

            except Exception as err:
                last_error = str(err)
                with config_jobs_lock:
                    job.last_error = last_error
                    job.last_response = last_response
                    job.updated_at = datetime.utcnow()
                logger.exception("Config job %s attempt %d/%d failed with unexpected error", job_id, attempt_index + 1, job.max_attempts)
                break

        if not success:
            with config_jobs_lock:
                job.status = "failed"
                job.config = None
                job.config_json = None
                job.updated_at = datetime.utcnow()
                job.last_response = last_response
                job.last_error = last_error
                job.error_message = (
                    last_error
                    if last_error
                    else "Config generation failed after exhausting all retries."
                )

        config_job_queue.task_done()


def start_config_generation_workers():
    """Start config generation worker threads if not already running."""
    if config_worker_threads:
        return

    worker_count = max(1, CONFIG_GENERATION_WORKERS)
    for _ in range(worker_count):
        worker = threading.Thread(target=config_generation_worker, daemon=True)
        config_worker_threads.append(worker)
        worker.start()
    print(f"Started {len(config_worker_threads)} config generation worker(s)")


def stop_config_generation_workers():
    """Signal workers to stop and wait briefly for shutdown."""
    config_worker_stop_event.set()
    for _ in config_worker_threads:
        config_job_queue.put(None)
    for worker in config_worker_threads:
        worker.join(timeout=5)
    config_worker_threads.clear()
    print("Stopped config generation workers")


def handle_generator_failure(job_id: str, error_message: str):
    """Callback function to handle generator failures and update job status."""
    if job_id in active_jobs:
        print(f"🚨 Job {job_id} failed: {error_message}")
        active_jobs[job_id].status = "failed"
        active_jobs[job_id].error_message = error_message
        active_jobs[job_id].failure_count += 1
        
        # Remove from active generators since it's failed
        if job_id in active_generators:
            del active_generators[job_id]

def get_user_from_request(request: Request) -> str:
    """Extract user from X-Forwarded-User header, defaulting to 'Not logged in'."""
    return request.headers.get("X-Forwarded-User", "Not logged in")

def count_user_jobs(user: str, status_filter: Optional[str] = None) -> int:
    """Count jobs for a specific user, optionally filtered by status."""
    count = 0
    for job in active_jobs.values():
        if job.user == user:
            if status_filter is None or job.status == status_filter:
                count += 1
    return count

def count_active_jobs() -> int:
    """Count currently active (running) jobs."""
    return len([job for job in active_jobs.values() if job.status == "running"])

def cleanup_old_jobs():
    """Remove old stopped jobs and timeout long-running jobs."""
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(hours=JOB_CLEANUP_HOURS)
    
    jobs_to_remove = []
    jobs_to_timeout = []
    
    for job_id, job in active_jobs.items():
        # Remove old stopped jobs
        if job.status == "stopped" and job.created_at < cutoff_time:
            jobs_to_remove.append(job_id)
        
        # Timeout long-running jobs
        elif (job.status == "running" and 
              job.timeout_at and 
              current_time > job.timeout_at):
            jobs_to_timeout.append(job_id)
    
    # Remove old stopped jobs
    for job_id in jobs_to_remove:
        print(f"Cleaning up old stopped job: {job_id}")
        del active_jobs[job_id]
    
    # Timeout long-running jobs
    for job_id in jobs_to_timeout:
        print(f"Timing out long-running job: {job_id}")
        try:
            if job_id in active_generators:
                generator = active_generators[job_id]
                generator.stop()
                del active_generators[job_id]
            
            active_jobs[job_id].status = "stopped"
            print(f"Job {job_id} stopped due to timeout")
        except Exception as e:
            print(f"Error stopping timed-out job {job_id}: {e}")

    cleanup_config_jobs(current_time)


def cleanup_config_jobs(current_time: Optional[datetime] = None):
    """Remove completed config generation jobs beyond the retention window."""
    if current_time is None:
        current_time = datetime.now()

    cutoff_time = current_time - timedelta(minutes=CONFIG_JOB_TTL_MINUTES)

    with config_jobs_lock:
        expired_jobs = [job_id for job_id, job in config_jobs.items()
                        if job.updated_at < cutoff_time and job.status in {"succeeded", "failed"}]

        for job_id in expired_jobs:
            del config_jobs[job_id]
            print(f"Cleaned up config generation job: {job_id}")


def cleanup_worker():
    """Background worker for periodic cleanup of jobs."""
    while not cleanup_stop_event.is_set():
        try:
            cleanup_old_jobs()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        
        # Wait for the cleanup interval or until stop event is set
        cleanup_stop_event.wait(timeout=CLEANUP_INTERVAL_MINUTES * 60)

def start_cleanup_worker():
    """Start the background cleanup worker if not already running."""
    global cleanup_thread
    if cleanup_thread is None or not cleanup_thread.is_alive():
        cleanup_stop_event.clear()
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        print(f"Started cleanup worker (interval: {CLEANUP_INTERVAL_MINUTES} minutes)")

def stop_cleanup_worker():
    """Stop the background cleanup worker."""
    global cleanup_thread
    if cleanup_thread and cleanup_thread.is_alive():
        cleanup_stop_event.set()
        cleanup_thread.join(timeout=5)
        print("Stopped cleanup worker")

# Start cleanup worker on application startup
start_cleanup_worker()
start_config_generation_workers()

# --- Models ---
class GenerateRequest(BaseModel):
    description: str

class StartRequest(BaseModel):
    config: dict
    description: str = "Telemetry Generation Job"
    otlp_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    auth_type: str = "ApiKey"

class JobResponse(BaseModel):
    id: str
    description: str
    created_at: datetime
    config: dict
    status: str
    otlp_endpoint: Optional[str] = None
    user: Optional[str] = "Not logged in"
    error_message: Optional[str] = None
    failure_count: int = 0

class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int

class StatusResponse(BaseModel):
    running: bool
    config: Optional[dict] = None
    job_id: Optional[str] = None

class RestartRequest(BaseModel):
    config: Optional[dict] = None
    description: Optional[str] = None
    otlp_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    auth_type: Optional[str] = None


class GenerateConfigJobResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    max_attempts: int


class ConfigJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    config_json: Optional[str] = None
    config: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    attempts: int
    max_attempts: int
    last_error: Optional[str] = None
    user: Optional[str] = "Not logged in"

class HealthCheckResponse(BaseModel):
    endpoint: str
    status: str  # "healthy", "unhealthy"
    response_time_ms: Optional[int] = None
    error: Optional[str] = None


@app.post("/generate-config", response_model=GenerateConfigJobResponse, status_code=202)
async def request_config_generation(request: GenerateRequest, req: Request):
    """Create an asynchronous config generation job and return its identifier."""
    description = request.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="Description must not be empty.")

    user = get_user_from_request(req)

    job_id = str(uuid.uuid4())
    job = ConfigGenerationJob(
        id=job_id,
        description=description,
        max_attempts=max(1, MAX_CONFIG_GENERATION_ATTEMPTS),
        user=user,
    )

    with config_jobs_lock:
        config_jobs[job_id] = job

    config_job_queue.put(job_id)

    return GenerateConfigJobResponse(job_id=job_id, status=job.status, max_attempts=job.max_attempts)


@app.get("/version", response_model=dict)
async def get_version():
    """Return the current application version."""
    return {"version": APP_VERSION}


@app.get("/config-jobs", response_model=List[ConfigJobStatusResponse])
async def list_config_jobs():
    """List all config generation jobs."""
    with config_jobs_lock:
        jobs_list = []
        for job in config_jobs.values():
            jobs_list.append(ConfigJobStatusResponse(
                job_id=job.id,
                status=job.status,
                config_json=job.config_json,
                config=job.config,
                error_message=job.error_message,
                created_at=job.created_at,
                updated_at=job.updated_at,
                attempts=job.attempts,
                max_attempts=job.max_attempts,
                last_error=job.last_error,
                user=job.user,
            ))
        # Sort by created_at desc
        jobs_list.sort(key=lambda x: x.created_at, reverse=True)
        return jobs_list


@app.get("/generate-config/{job_id}", response_model=ConfigJobStatusResponse)
async def get_config_generation_job(job_id: str):
    """Fetch the current status (and result if available) for a config generation job."""
    with config_jobs_lock:
        job = config_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Config generation job not found.")

        job_data = dict(
            job_id=job.id,
            status=job.status,
            config_json=job.config_json,
            config=job.config,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            last_error=job.last_error,
            user=job.user,
        )

    return ConfigJobStatusResponse(**job_data)

def clean_config_for_validation(config: dict) -> dict:
    """
    Clean and fix configuration before validation.
    Removes incomplete log_samples and adds default telemetry section if missing.
    """
    import copy
    cleaned_config = copy.deepcopy(config)  # Deep copy to avoid modifying original

    # Clean up services
    if "services" in cleaned_config:
        for service in cleaned_config["services"]:
            # Remove incomplete log_samples
            if "log_samples" in service:
                cleaned_samples = []
                for sample in service["log_samples"]:
                    # Check if it's a valid log sample with both level and message
                    if (isinstance(sample, dict) and
                        sample.get("level") and
                        sample.get("message") and
                        isinstance(sample.get("level"), str) and
                        isinstance(sample.get("message"), str)):
                        cleaned_samples.append({
                            "level": sample["level"],
                            "message": sample["message"]
                        })
                if cleaned_samples:
                    service["log_samples"] = cleaned_samples
                else:
                    # Remove log_samples if all were invalid
                    del service["log_samples"]

    # Add default telemetry section if missing
    if "telemetry" not in cleaned_config:
        cleaned_config["telemetry"] = {
            "trace_rate": 5,
            "error_rate": 0.05,
            "metrics_interval": 10,
            "include_logs": True
        }

    return cleaned_config

@app.post("/start", response_model=dict)
async def start_generation(start_request: StartRequest, request: Request):
    """
    Starts a new telemetry generator job with a given configuration.
    """
    try:
        # Get user from request headers
        user = get_user_from_request(request)

        # Check system-wide active job limit
        if count_active_jobs() >= MAX_ACTIVE_JOBS:
            raise HTTPException(
                status_code=429,
                detail=f"Maximum active jobs limit reached ({MAX_ACTIVE_JOBS}). Please wait for some jobs to complete or stop existing jobs."
            )

        # Check per-user active job limit
        user_active_jobs = count_user_jobs(user, "running")
        if user_active_jobs >= MAX_JOBS_PER_USER:
            raise HTTPException(
                status_code=429,
                detail=f"Maximum jobs per user limit reached ({MAX_JOBS_PER_USER}). Please stop some of your existing jobs first."
            )

        # Generate unique job ID
        job_id = str(uuid.uuid4())[:8]

        # Clean and validate configuration
        cleaned_config = clean_config_for_validation(start_request.config)
        scenario_config = ScenarioConfig(**cleaned_config)
        
        # Create and start generator with failure callback
        def failure_callback(error_msg: str):
            handle_generator_failure(job_id, error_msg)
        
        generator = TelemetryGenerator(
            config=scenario_config,
            otlp_endpoint=start_request.otlp_endpoint,
            api_key=start_request.api_key,
            auth_type=start_request.auth_type,
            failure_callback=failure_callback
        )
        
        # Calculate timeout time
        timeout_at = datetime.now() + timedelta(hours=MAX_JOB_DURATION_HOURS)
        
        # Store job info with cleaned config
        job_info = JobInfo(
            id=job_id,
            description=start_request.description,
            created_at=datetime.now(),
            config=cleaned_config,
            status="running",
            otlp_endpoint=start_request.otlp_endpoint,
            user=user,
            timeout_at=timeout_at
        )
        
        active_jobs[job_id] = job_info
        active_generators[job_id] = generator
        
        # Start the generator
        generator.start()
        
        return {
            "status": "started",
            "job_id": job_id,
            "description": start_request.description,
            "created_at": job_info.created_at.isoformat(),
            "user": user,
            "timeout_at": timeout_at.isoformat(),
            "limits": {
                "max_duration_hours": MAX_JOB_DURATION_HOURS,
                "user_active_jobs": user_active_jobs + 1,
                "max_jobs_per_user": MAX_JOBS_PER_USER,
                "system_active_jobs": count_active_jobs() + 1,
                "max_active_jobs": MAX_ACTIVE_JOBS
            }
        }
        
    except HTTPException:
        raise
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
            otlp_endpoint=job.otlp_endpoint,
            user=job.user,
            error_message=job.error_message,
            failure_count=job.failure_count
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
        otlp_endpoint=job.otlp_endpoint,
        user=job.user,
        error_message=job.error_message,
        failure_count=job.failure_count
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

@app.post("/restart/{job_id}")
async def restart_job(job_id: str, restart_request: Optional[RestartRequest] = None, request: Request = None):
    """
    Restarts a job. Can optionally update configuration, description, or OTLP endpoint.
    Stops it first if running, then starts it again.
    """
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    job_info = active_jobs[job_id]
    
    try:
        # Stop the job if it's running
        if job_id in active_generators:
            generator = active_generators[job_id]
            generator.stop()
            del active_generators[job_id]
        
        # Get user from request headers (may be different from original)
        user = get_user_from_request(request)
        
        # Use new config if provided, otherwise use original
        config_to_use = restart_request.config if restart_request and restart_request.config else job_info.config
        otlp_endpoint_to_use = restart_request.otlp_endpoint if restart_request and restart_request.otlp_endpoint else job_info.otlp_endpoint
        api_key_to_use = restart_request.api_key if restart_request and restart_request.api_key else None
        auth_type_to_use = restart_request.auth_type if restart_request and restart_request.auth_type else "ApiKey"
        description_to_use = restart_request.description if restart_request and restart_request.description else job_info.description

        # Clean and validate configuration
        cleaned_config = clean_config_for_validation(config_to_use)

        # Create new generator with the config and failure callback
        def failure_callback(error_msg: str):
            handle_generator_failure(job_id, error_msg)

        scenario_config = ScenarioConfig(**cleaned_config)
        generator = TelemetryGenerator(
            config=scenario_config,
            otlp_endpoint=otlp_endpoint_to_use,
            api_key=api_key_to_use,
            auth_type=auth_type_to_use,
            failure_callback=failure_callback
        )
        
        # Update job info with new values - reset error state on restart
        job_info.config = cleaned_config
        job_info.otlp_endpoint = otlp_endpoint_to_use
        job_info.description = description_to_use
        job_info.status = "running"
        job_info.user = user  # Update user in case it changed
        job_info.error_message = None  # Clear previous error
        job_info.failure_count = 0  # Reset failure count
        active_generators[job_id] = generator
        
        # Start the generator
        generator.start()
        
        return {
            "status": "restarted",
            "job_id": job_id,
            "description": job_info.description,
            "user": user
        }
        
    except Exception as e:
        # If restart fails, mark job as stopped
        job_info.status = "stopped"
        if job_id in active_generators:
            del active_generators[job_id]
        raise HTTPException(status_code=500, detail=f"Failed to restart job: {e}")

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
    
    # Convert to JSON string for consistency with generate-config endpoint
    config_json_str = json.dumps(test_config, indent=2)

    return {"config_json": config_json_str, "config": test_config}

@app.get("/llm-config", response_model=dict)
async def get_llm_config():
    """
    Returns information about the current LLM provider configuration.
    """
    provider = os.getenv("LLM_PROVIDER", "bedrock").lower()

    config_status = {
        "provider": provider,
        "configured": False,
        "model": None,
        "details": {}
    }

    if provider != "bedrock":
        config_status["details"]["error"] = (
            "Unsupported provider configured. Set LLM_PROVIDER=bedrock and supply AWS credentials."
        )
        return config_status

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
    
    return config_status

@app.get("/limits", summary="Get current job limits and usage")
async def get_limits():
    """
    Returns current job limits configuration and usage statistics.
    """
    active_count = count_active_jobs()
    total_count = len(active_jobs)
    stopped_count = total_count - active_count
    
    # Get per-user breakdown
    user_stats = {}
    for job in active_jobs.values():
        user = job.user
        if user not in user_stats:
            user_stats[user] = {"active": 0, "stopped": 0, "total": 0}
        
        user_stats[user]["total"] += 1
        if job.status == "running":
            user_stats[user]["active"] += 1
        else:
            user_stats[user]["stopped"] += 1
    
    return {
        "limits": {
            "max_active_jobs": MAX_ACTIVE_JOBS,
            "max_jobs_per_user": MAX_JOBS_PER_USER,
            "max_job_duration_hours": MAX_JOB_DURATION_HOURS,
            "job_cleanup_hours": JOB_CLEANUP_HOURS,
            "cleanup_interval_minutes": CLEANUP_INTERVAL_MINUTES
        },
        "current_usage": {
            "active_jobs": active_count,
            "stopped_jobs": stopped_count,
            "total_jobs": total_count,
            "remaining_slots": max(0, MAX_ACTIVE_JOBS - active_count)
        },
        "user_breakdown": user_stats,
        "cleanup_status": {
            "worker_running": cleanup_thread and cleanup_thread.is_alive(),
            "next_cleanup_in_minutes": CLEANUP_INTERVAL_MINUTES  # Approximate
        }
    }

@app.post("/cleanup", summary="Manually trigger job cleanup")
async def manual_cleanup():
    """
    Manually trigger cleanup of old jobs and timeout long-running jobs.
    """
    try:
        jobs_before = len(active_jobs)
        cleanup_old_jobs()
        jobs_after = len(active_jobs)
        cleaned_count = jobs_before - jobs_after
        
        return {
            "status": "completed",
            "jobs_cleaned": cleaned_count,
            "jobs_remaining": jobs_after,
            "message": f"Cleaned up {cleaned_count} old jobs"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {e}")

@app.get("/whoami", summary="Get current user information")
async def whoami(request: Request):
    """
    Returns the current user as determined from the X-Forwarded-User header.
    """
    user = get_user_from_request(request)
    return {"user": user}

@app.get("/", summary="Root endpoint for health check")
async def read_root():
    return {"message": "Welcome to the Telemetry Demo Generator API"}

@app.post("/health-check-otlp", response_model=HealthCheckResponse)
async def health_check_otlp(request: dict = Body(...)):
    """
    Check if an OTLP endpoint is reachable and accepting requests.
    Expects a JSON body with 'otlp_endpoint' field.
    """
    otlp_endpoint = request.get("otlp_endpoint")
    if not otlp_endpoint:
        raise HTTPException(status_code=400, detail="otlp_endpoint is required")
    
    # Ensure endpoint has proper format
    collector_url = otlp_endpoint.rstrip('/')
    if not collector_url.endswith('/'):
        collector_url += '/'
    
    test_url = f"{collector_url}v1/traces"
    
    start_time = datetime.now()
    
    try:
        # Create a minimal test payload
        test_payload = {
            "resourceSpans": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "health-check"}}
                    ]
                },
                "scopeSpans": [{
                    "scope": {"name": "health-check"},
                    "spans": [{
                        "traceId": "00000000000000000000000000000001",
                        "spanId": "0000000000000001",
                        "name": "health-check-span",
                        "kind": 1,
                        "startTimeUnixNano": str(int(start_time.timestamp() * 1_000_000_000)),
                        "endTimeUnixNano": str(int(start_time.timestamp() * 1_000_000_000) + 1_000_000),
                        "status": {"code": 1}
                    }]
                }]
            }]
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                test_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(test_payload),
                timeout=5.0
            )
            
            end_time = datetime.now()
            response_time = int((end_time - start_time).total_seconds() * 1000)
            
            if response.status_code in [200, 202]:
                return HealthCheckResponse(
                    endpoint=otlp_endpoint,
                    status="healthy",
                    response_time_ms=response_time
                )
            else:
                return HealthCheckResponse(
                    endpoint=otlp_endpoint,
                    status="unhealthy",
                    response_time_ms=response_time,
                    error=f"HTTP {response.status_code}: {response.reason_phrase}"
                )
                
    except httpx.TimeoutException:
        end_time = datetime.now()
        response_time = int((end_time - start_time).total_seconds() * 1000)
        return HealthCheckResponse(
            endpoint=otlp_endpoint,
            status="unhealthy",
            response_time_ms=response_time,
            error="Connection timeout"
        )
    except httpx.RequestError as e:
        end_time = datetime.now()
        response_time = int((end_time - start_time).total_seconds() * 1000)
        return HealthCheckResponse(
            endpoint=otlp_endpoint,
            status="unhealthy",
            response_time_ms=response_time,
            error=f"Connection error: {str(e)}"
        )
    except Exception as e:
        end_time = datetime.now()
        response_time = int((end_time - start_time).total_seconds() * 1000)
        return HealthCheckResponse(
            endpoint=otlp_endpoint,
            status="unhealthy",
            response_time_ms=response_time,
            error=f"Unexpected error: {str(e)}"
        )

# --- Scenario Management Endpoints ---

@app.post("/scenarios/generate", summary="Generate scenario from description")
async def generate_scenario(request: ScenarioGenerationRequest):
    """
    Uses LLM to generate a scenario modification from natural language description.
    """
    try:
        # Scenario generation also calls the LLM synchronously, so run it in a worker thread.
        scenario_modification = await asyncio.to_thread(
            generate_scenario_from_description,
            request.description,
            request.context,
        )

        return {
            "scenario": scenario_modification.dict(),
            "description": request.description,
            "generated_at": datetime.now().isoformat()
        }

    except ValueError as e:
        # Handle missing API keys or configuration errors
        error_message = str(e)
        if "Unsupported LLM provider" in error_message:
            raise HTTPException(
                status_code=400,
                detail="Unsupported LLM provider configured. Set LLM_PROVIDER=bedrock."
            )
        elif "AWS credentials not found" in error_message:
            raise HTTPException(
                status_code=400,
                detail="AWS credentials not configured. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
            )
        else:
            raise HTTPException(status_code=400, detail=f"Configuration error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate scenario: {e}")

@app.post("/scenarios/apply/{job_id}", summary="Apply scenario to running job")
async def apply_scenario(job_id: str, request: ScenarioApplyRequest):
    """
    Applies a scenario modification to a running job.
    """
    # Check if job exists and is running
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job_id not in active_generators:
        raise HTTPException(status_code=400, detail=f"Job {job_id} is not running")

    try:
        generator = active_generators[job_id]

        # Determine scenario to apply
        if request.scenario:
            scenario_modification = request.scenario
            description = request.description or "Custom scenario"
        elif request.template_name:
            # Find template
            templates = get_predefined_templates()
            template = next((t for t in templates if t["name"] == request.template_name), None)
            if not template:
                raise HTTPException(status_code=404, detail=f"Template '{request.template_name}' not found")

            scenario_modification = ScenarioModification(**template["modification"])
            description = f"Template: {template['description']}"

            # Override duration if specified
            if not request.duration_minutes:
                request.duration_minutes = template.get("default_duration_minutes")
        else:
            raise HTTPException(status_code=400, detail="Must specify either 'scenario' or 'template_name'")

        # Generate scenario ID
        scenario_id = str(uuid.uuid4())[:8]

        # Calculate end time
        ends_at = None
        if request.duration_minutes:
            ends_at = datetime.now() + timedelta(minutes=request.duration_minutes)

        # Apply scenario to generator
        generator.apply_scenario(scenario_id, scenario_modification)

        # Store active scenario
        active_scenario = ActiveScenario(
            id=scenario_id,
            job_id=job_id,
            description=description,
            modification=scenario_modification,
            started_at=datetime.now(),
            ends_at=ends_at,
            status="active"
        )

        active_scenarios[scenario_id] = active_scenario

        return {
            "status": "applied",
            "scenario_id": scenario_id,
            "job_id": job_id,
            "description": description,
            "ends_at": ends_at.isoformat() if ends_at else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply scenario: {e}")

@app.get("/scenarios/active/{job_id}", summary="List active scenarios for job")
async def get_active_scenarios(job_id: str):
    """
    Returns all active scenarios for a specific job.
    """
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Filter scenarios for this job and clean up expired ones
    job_scenarios = []
    current_time = datetime.now()
    expired_scenarios = []

    for scenario_id, scenario in active_scenarios.items():
        if scenario.job_id == job_id:
            # Check if scenario has expired
            if scenario.ends_at and current_time > scenario.ends_at:
                expired_scenarios.append(scenario_id)
                # Stop scenario in generator
                if job_id in active_generators:
                    try:
                        active_generators[job_id].stop_scenario(scenario_id)
                    except:
                        pass  # Generator might not support this scenario anymore
            else:
                job_scenarios.append(scenario)

    # Clean up expired scenarios
    for scenario_id in expired_scenarios:
        del active_scenarios[scenario_id]

    return {
        "job_id": job_id,
        "active_scenarios": [scenario.dict() for scenario in job_scenarios],
        "total_active": len(job_scenarios)
    }

@app.delete("/scenarios/{scenario_id}", summary="Stop specific scenario")
async def stop_scenario(scenario_id: str):
    """
    Stops a specific active scenario.
    """
    if scenario_id not in active_scenarios:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    scenario = active_scenarios[scenario_id]
    job_id = scenario.job_id

    try:
        # Stop scenario in generator if job is still running
        if job_id in active_generators:
            active_generators[job_id].stop_scenario(scenario_id)

        # Remove from active scenarios
        del active_scenarios[scenario_id]

        return {
            "status": "stopped",
            "scenario_id": scenario_id,
            "job_id": job_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop scenario: {e}")

@app.get("/scenarios/templates", summary="Get predefined scenario templates")
async def get_scenario_templates():
    """
    Returns all available predefined scenario templates.
    """
    templates = get_predefined_templates()
    return {
        "templates": templates,
        "total": len(templates)
    }
