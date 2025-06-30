import yaml
from fastapi import FastAPI, HTTPException, Response, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from pydantic import BaseModel

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

# Global state to hold the single generator instance
generator_instance: Optional[TelemetryGenerator] = None

# --- Models ---
class GenerateRequest(BaseModel):
    description: str

class StartRequest(BaseModel):
    config: dict
    otlp_endpoint: Optional[str] = None
    api_key: Optional[str] = None

class StatusResponse(BaseModel):
    running: bool
    config: Optional[dict] = None

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate config: {e}")

@app.post("/start")
async def start_generation(request: StartRequest):
    """
    Starts the telemetry generator with a given configuration.
    """
    global generator_instance
    if generator_instance and generator_instance.is_running():
        raise HTTPException(status_code=400, detail="Generator is already running.")

    try:
        scenario_config = ScenarioConfig(**request.config)
        generator_instance = TelemetryGenerator(
            config=scenario_config,
            otlp_endpoint=request.otlp_endpoint,
            api_key=request.api_key
        )
        generator_instance.start()
        return {"status": "started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start generator: {e}")

@app.post("/stop")
async def stop_generation():
    """
    Stops the telemetry generator.
    """
    global generator_instance
    if not generator_instance or not generator_instance.is_running():
        raise HTTPException(status_code=400, detail="Generator is not running.")
    
    generator_instance.stop()
    generator_instance = None
    return {"status": "stopped"}

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Returns the current status of the generator.
    """
    if generator_instance and generator_instance.is_running():
        return {"running": True, "config": generator_instance.get_config_as_dict()}
    return {"running": False, "config": None}

@app.get("/", summary="Root endpoint for health check")
async def read_root():
    return {"message": "Welcome to the Telemetry Demo Generator API"} 