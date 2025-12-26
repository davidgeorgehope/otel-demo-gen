"""
Tests for the FastAPI endpoints in main.py.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    # Import here to avoid issues with module initialization
    from main import app
    return TestClient(app)


@pytest.fixture
def mock_generator():
    """Mock TelemetryGenerator for testing."""
    with patch('main.TelemetryGenerator') as mock_class:
        mock_instance = MagicMock()
        mock_instance.is_running.return_value = True
        mock_instance.get_config_as_dict.return_value = {}
        mock_instance.get_correlation_manager.return_value = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


class TestHealthEndpoints:
    """Tests for health and info endpoints."""

    def test_root_endpoint(self, client):
        """Root endpoint returns welcome message."""
        response = client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()

    def test_version_endpoint(self, client):
        """Version endpoint returns version info."""
        response = client.get("/version")
        assert response.status_code == 200
        assert "version" in response.json()

    def test_whoami_endpoint(self, client):
        """Whoami endpoint returns user info."""
        response = client.get("/whoami")
        assert response.status_code == 200
        assert "user" in response.json()

    def test_whoami_with_header(self, client):
        """Whoami respects X-Forwarded-User header."""
        response = client.get("/whoami", headers={"X-Forwarded-User": "testuser"})
        assert response.status_code == 200
        assert response.json()["user"] == "testuser"

    def test_llm_config_endpoint(self, client):
        """LLM config endpoint returns provider info."""
        response = client.get("/llm-config")
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "configured" in data
        assert "details" in data


class TestLimitsEndpoint:
    """Tests for limits and usage endpoint."""

    def test_limits_endpoint(self, client):
        """Limits endpoint returns limit configuration."""
        response = client.get("/limits")
        assert response.status_code == 200
        data = response.json()
        assert "limits" in data
        assert "current_usage" in data
        assert "max_active_jobs" in data["limits"]
        assert "max_jobs_per_user" in data["limits"]


class TestJobManagement:
    """Tests for job management endpoints."""

    def test_list_jobs_empty(self, client):
        """List jobs returns empty when no jobs exist."""
        # Clear any existing jobs
        from main import active_jobs, jobs_lock
        with jobs_lock:
            active_jobs.clear()

        response = client.get("/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)

    def test_get_job_not_found(self, client):
        """Get job returns 404 for non-existent job."""
        response = client.get("/jobs/nonexistent")
        assert response.status_code == 404

    def test_delete_job_not_found(self, client):
        """Delete job returns 404 for non-existent job."""
        response = client.delete("/jobs/nonexistent")
        assert response.status_code == 404

    def test_stop_job_not_found(self, client):
        """Stop job returns 404 for non-existent job."""
        response = client.post("/stop/nonexistent")
        assert response.status_code == 404


class TestStartGeneration:
    """Tests for starting telemetry generation."""

    def test_start_requires_config(self, client):
        """Start endpoint requires valid config."""
        response = client.post("/start", json={})
        assert response.status_code == 422  # Validation error

    def test_start_with_minimal_config(self, client, mock_generator, minimal_config):
        """Start endpoint accepts minimal valid config."""
        response = client.post("/start", json={
            "config": minimal_config,
            "description": "Test job"
        })
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "started"

    def test_start_returns_limits_info(self, client, mock_generator, minimal_config):
        """Start endpoint returns limits info."""
        response = client.post("/start", json={
            "config": minimal_config,
            "description": "Test job"
        })
        assert response.status_code == 200
        data = response.json()
        assert "limits" in data
        assert "max_jobs_per_user" in data["limits"]


class TestConfigGeneration:
    """Tests for config generation endpoints."""

    def test_generate_config_empty_description(self, client):
        """Generate config rejects empty description."""
        response = client.post("/generate-config", json={"description": ""})
        assert response.status_code == 400

    def test_generate_config_whitespace_description(self, client):
        """Generate config rejects whitespace-only description."""
        response = client.post("/generate-config", json={"description": "   "})
        assert response.status_code == 400

    def test_get_config_job_not_found(self, client):
        """Get config job returns 404 for non-existent job."""
        response = client.get("/generate-config/nonexistent-job-id")
        assert response.status_code == 404

    def test_list_config_jobs(self, client):
        """List config jobs endpoint works."""
        response = client.get("/config-jobs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_generate_config_creates_job(self, client):
        """Generate config creates a pending job."""
        # This tests the API layer only - actual LLM call happens in background worker
        response = client.post("/generate-config", json={"description": "A simple e-commerce app"})
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"

        # Verify job can be retrieved
        job_response = client.get(f"/generate-config/{data['job_id']}")
        assert job_response.status_code == 200
        job_data = job_response.json()
        assert job_data["job_id"] == data["job_id"]


class TestLLMConfig:
    """Tests for LLM configuration endpoint."""

    def test_llm_config_endpoint(self, client):
        """LLM config endpoint returns provider info."""
        response = client.get("/llm-config")
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "configured" in data


class TestTestConfig:
    """Tests for test configuration endpoint."""

    def test_get_test_config(self, client):
        """Test config endpoint returns valid config."""
        response = client.get("/test-config")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert "config_json" in data
        assert "services" in data["config"]


class TestScenarioEndpoints:
    """Tests for scenario management endpoints."""

    def test_get_scenario_templates(self, client):
        """Scenario templates endpoint returns templates."""
        response = client.get("/scenarios/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "total" in data

    def test_get_active_scenarios_job_not_found(self, client):
        """Get active scenarios returns 404 for non-existent job."""
        response = client.get("/scenarios/active/nonexistent")
        assert response.status_code == 404

    def test_stop_scenario_not_found(self, client):
        """Stop scenario returns 404 for non-existent scenario."""
        response = client.delete("/scenarios/nonexistent")
        assert response.status_code == 404


class TestIncidentEndpoints:
    """Tests for incident management endpoints."""

    @pytest.fixture(autouse=True)
    def clear_state(self):
        """Clear global state before each test."""
        from main import active_jobs, active_generators, jobs_lock, generators_lock
        with jobs_lock:
            active_jobs.clear()
        with generators_lock:
            active_generators.clear()

    def test_list_active_incidents(self, client):
        """List active incidents returns empty list initially."""
        response = client.get("/incidents/active")
        assert response.status_code == 200
        data = response.json()
        assert "incidents" in data
        assert "total" in data

    def test_get_incident_not_found(self, client):
        """Get incident returns 404 for non-existent incident."""
        response = client.get("/incidents/nonexistent-incident-id")
        assert response.status_code == 404

    def test_stop_incident_not_found(self, client):
        """Stop incident returns 404 for non-existent incident."""
        response = client.delete("/incidents/nonexistent-incident-id")
        assert response.status_code == 404

    def test_cascade_job_not_found(self, client):
        """Cascade endpoint returns 404 for non-existent job."""
        response = client.post("/incidents/cascade/nonexistent", json={
            "template_name": "test"
        })
        assert response.status_code == 404

    def test_get_cascade_templates(self, client):
        """Cascade templates endpoint returns templates with structure."""
        response = client.get("/incidents/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "total" in data


class TestCleanup:
    """Tests for cleanup endpoint."""

    def test_manual_cleanup(self, client):
        """Manual cleanup endpoint works."""
        response = client.post("/cleanup")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "jobs_cleaned" in data
