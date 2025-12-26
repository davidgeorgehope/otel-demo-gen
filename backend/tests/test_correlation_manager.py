"""
Tests for the CorrelationManager class.
"""
import pytest
from unittest.mock import Mock, patch
import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from correlation_manager import CorrelationManager
from config_schema import CascadingOutageConfig, CascadeStage


@pytest.fixture
def correlation_manager():
    """Create a fresh CorrelationManager instance."""
    return CorrelationManager()


@pytest.fixture
def cascade_config():
    """Create a sample cascading outage configuration."""
    return CascadingOutageConfig(
        name="Test Cascade",
        description="Test cascading outage",
        origin="infrastructure",
        trigger_component="test-switch",
        cascade_chain=[
            CascadeStage(component="test-switch", effect="port_down", delay_ms=0),
            CascadeStage(component="database", effect="connection_timeout", delay_ms=1000),
            CascadeStage(component="api-service", effect="error_rate", delay_ms=2000)
        ]
    )


class TestIncidentCreation:
    """Tests for incident creation."""

    def test_start_incident_returns_id(self, correlation_manager, cascade_config):
        """start_incident returns a valid incident ID."""
        incident_id = correlation_manager.start_incident(
            job_id="test-job",
            root_cause_type="infrastructure",
            root_cause_component="test-switch",
            cascade_config=cascade_config,
            severity="high",
            description="Test incident"
        )

        assert incident_id is not None
        assert incident_id.startswith("INC-")
        assert len(incident_id) > 10

    def test_start_incident_creates_state(self, correlation_manager, cascade_config):
        """start_incident creates proper incident state."""
        incident_id = correlation_manager.start_incident(
            job_id="test-job",
            root_cause_type="infrastructure",
            root_cause_component="test-switch",
            cascade_config=cascade_config,
            severity="high"
        )

        incident = correlation_manager.get_incident(incident_id)
        assert incident is not None
        assert incident.incident_id == incident_id
        assert incident.root_cause_type == "infrastructure"
        assert incident.root_cause_component == "test-switch"
        assert incident.severity == "high"


class TestCorrelationAttributes:
    """Tests for correlation attribute retrieval."""

    def test_get_attributes_for_affected_component(self, correlation_manager, cascade_config):
        """get_attributes_for_component returns correlation data for affected component."""
        incident_id = correlation_manager.start_incident(
            job_id="test-job",
            root_cause_type="infrastructure",
            root_cause_component="test-switch",
            cascade_config=cascade_config,
            severity="high"
        )

        attrs = correlation_manager.get_attributes_for_component("test-switch")

        assert "incident.id" in attrs
        assert attrs["incident.id"] == incident_id
        assert "incident.root_cause.type" in attrs
        assert "incident.root_cause.component" in attrs
        assert "incident.severity" in attrs

    def test_get_attributes_for_unaffected_component(self, correlation_manager):
        """get_attributes_for_component returns empty dict for unaffected component."""
        attrs = correlation_manager.get_attributes_for_component("unaffected-service")
        assert attrs == {}


class TestEffectRetrieval:
    """Tests for effect retrieval."""

    def test_get_effect_for_component(self, correlation_manager, cascade_config):
        """get_effect_for_component returns correct effect."""
        correlation_manager.start_incident(
            job_id="test-job",
            root_cause_type="infrastructure",
            root_cause_component="test-switch",
            cascade_config=cascade_config,
            severity="high"
        )

        effect = correlation_manager.get_effect_for_component("test-switch")
        assert effect is not None
        assert effect["effect"] == "port_down"
        assert "parameters" in effect
        assert "incident_id" in effect

    def test_get_effect_for_unaffected_component(self, correlation_manager):
        """get_effect_for_component returns None for unaffected component."""
        effect = correlation_manager.get_effect_for_component("unaffected")
        assert effect is None


class TestCascadeAdvancement:
    """Tests for cascade stage advancement."""

    def test_advance_cascade_increments_stage(self, correlation_manager, cascade_config):
        """advance_cascade moves to next stage."""
        incident_id = correlation_manager.start_incident(
            job_id="test-job",
            root_cause_type="infrastructure",
            root_cause_component="test-switch",
            cascade_config=cascade_config,
            severity="high"
        )

        # Use list_active_incidents to get current_stage info
        incidents_before = correlation_manager.list_active_incidents()
        initial_stage = incidents_before[0]["current_stage"]

        correlation_manager.advance_cascade(incident_id)

        incidents_after = correlation_manager.list_active_incidents()
        assert incidents_after[0]["current_stage"] == initial_stage + 1

    def test_advance_cascade_updates_affected_components(self, correlation_manager, cascade_config):
        """advance_cascade adds new affected components."""
        incident_id = correlation_manager.start_incident(
            job_id="test-job",
            root_cause_type="infrastructure",
            root_cause_component="test-switch",
            cascade_config=cascade_config,
            severity="high"
        )

        # First advance processes stage 0 (test-switch, already root cause)
        correlation_manager.advance_cascade(incident_id)
        # Second advance adds database (stage 1)
        correlation_manager.advance_cascade(incident_id)

        # Database should now be affected
        attrs = correlation_manager.get_attributes_for_component("database")
        assert "incident.id" in attrs


class TestIncidentResolution:
    """Tests for incident stopping/resolution."""

    def test_stop_incident_returns_true(self, correlation_manager, cascade_config):
        """stop_incident returns True for existing incident."""
        incident_id = correlation_manager.start_incident(
            job_id="test-job",
            root_cause_type="infrastructure",
            root_cause_component="test-switch",
            cascade_config=cascade_config,
            severity="high"
        )

        result = correlation_manager.stop_incident(incident_id)
        assert result is True

    def test_stop_incident_returns_false_for_nonexistent(self, correlation_manager):
        """stop_incident returns False for non-existent incident."""
        result = correlation_manager.stop_incident("nonexistent-incident")
        assert result is False

    def test_stop_incident_clears_component_effects(self, correlation_manager, cascade_config):
        """stop_incident clears effects for affected components."""
        incident_id = correlation_manager.start_incident(
            job_id="test-job",
            root_cause_type="infrastructure",
            root_cause_component="test-switch",
            cascade_config=cascade_config,
            severity="high"
        )

        # Verify component is affected
        attrs = correlation_manager.get_attributes_for_component("test-switch")
        assert "incident.id" in attrs

        # Stop incident
        correlation_manager.stop_incident(incident_id)

        # Component should no longer be affected
        attrs_after = correlation_manager.get_attributes_for_component("test-switch")
        assert attrs_after == {}


class TestListIncidents:
    """Tests for listing incidents."""

    def test_list_active_incidents_empty(self, correlation_manager):
        """list_active_incidents returns empty list when no incidents."""
        incidents = correlation_manager.list_active_incidents("test-job")
        assert incidents == []

    def test_list_active_incidents_filters_by_job(self, correlation_manager, cascade_config):
        """list_active_incidents filters by job_id."""
        correlation_manager.start_incident(
            job_id="job-1",
            root_cause_type="infrastructure",
            root_cause_component="switch-1",
            cascade_config=cascade_config,
            severity="high"
        )
        correlation_manager.start_incident(
            job_id="job-2",
            root_cause_type="infrastructure",
            root_cause_component="switch-2",
            cascade_config=cascade_config,
            severity="high"
        )

        job1_incidents = correlation_manager.list_active_incidents("job-1")
        job2_incidents = correlation_manager.list_active_incidents("job-2")

        assert len(job1_incidents) == 1
        assert len(job2_incidents) == 1
        assert job1_incidents[0]["root_cause_component"] == "switch-1"
        assert job2_incidents[0]["root_cause_component"] == "switch-2"


class TestThreadSafety:
    """Tests for thread safety of CorrelationManager."""

    def test_concurrent_incident_creation(self, correlation_manager, cascade_config):
        """Multiple threads can create incidents safely."""
        incident_ids = []
        errors = []

        def create_incident(thread_id):
            try:
                incident_id = correlation_manager.start_incident(
                    job_id=f"job-{thread_id}",
                    root_cause_type="infrastructure",
                    root_cause_component=f"switch-{thread_id}",
                    cascade_config=cascade_config,
                    severity="high"
                )
                incident_ids.append(incident_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_incident, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(incident_ids) == 10
        assert len(set(incident_ids)) == 10  # All unique

    def test_concurrent_attribute_access(self, correlation_manager, cascade_config):
        """Multiple threads can access attributes safely."""
        incident_id = correlation_manager.start_incident(
            job_id="test-job",
            root_cause_type="infrastructure",
            root_cause_component="test-switch",
            cascade_config=cascade_config,
            severity="high"
        )

        results = []
        errors = []

        def get_attrs():
            try:
                attrs = correlation_manager.get_attributes_for_component("test-switch")
                results.append(attrs.get("incident.id"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_attrs) for _ in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r == incident_id for r in results)
