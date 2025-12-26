"""
Incident correlation manager for unified outage simulation.
Ensures all signals (traces, logs, metrics, infrastructure) share correlation context.
"""
import uuid
import logging
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from config_schema import (
    IncidentCorrelation,
    CascadingOutageConfig,
    CascadeStage,
)

logger = logging.getLogger(__name__)


@dataclass
class ActiveIncidentState:
    """Internal state for an active correlated incident."""
    incident_id: str
    job_id: str
    root_cause_type: str  # "infrastructure" or "application"
    root_cause_component: str
    affected_components: List[str]
    cascade_path: List[str]
    cascade_stages: List[CascadeStage]
    current_stage: int = 0
    severity: str = "medium"
    description: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    status: str = "active"  # active, cascading, recovering, resolved
    attributes: Dict[str, Any] = field(default_factory=dict)


class CorrelationManager:
    """
    Manages incident correlation across all telemetry signals.
    Ensures traces, logs, metrics, and infrastructure data are connected
    through a unified incident ID and correlation attributes.
    """

    def __init__(self):
        self._active_incidents: Dict[str, ActiveIncidentState] = {}
        self._lock = threading.RLock()  # RLock allows same thread to acquire multiple times
        # Map component -> incident_ids for quick lookup
        self._component_incidents: Dict[str, List[str]] = {}

    def start_incident(
        self,
        job_id: str,
        root_cause_type: str,
        root_cause_component: str,
        cascade_config: CascadingOutageConfig,
        severity: str = "medium",
        description: str = ""
    ) -> str:
        """
        Start a new correlated incident.

        Args:
            job_id: The job this incident affects
            root_cause_type: 'infrastructure' or 'application'
            root_cause_component: The component that triggered the incident
            cascade_config: Configuration for the cascading outage
            severity: 'critical', 'high', 'medium', 'low'
            description: Human-readable description

        Returns:
            The generated incident_id
        """
        incident_id = f"INC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        # Extract cascade path from stages
        cascade_path = [stage.component for stage in cascade_config.cascade_chain]

        incident = ActiveIncidentState(
            incident_id=incident_id,
            job_id=job_id,
            root_cause_type=root_cause_type,
            root_cause_component=root_cause_component,
            affected_components=[root_cause_component],
            cascade_path=cascade_path,
            cascade_stages=cascade_config.cascade_chain,
            severity=severity,
            description=description or cascade_config.description,
            status="cascading" if len(cascade_path) > 1 else "active",
        )

        with self._lock:
            self._active_incidents[incident_id] = incident
            # Register component -> incident mapping
            if root_cause_component not in self._component_incidents:
                self._component_incidents[root_cause_component] = []
            self._component_incidents[root_cause_component].append(incident_id)

        logger.info(f"Started incident {incident_id}: {description}")
        logger.info(f"Root cause: {root_cause_type}/{root_cause_component}")
        logger.info(f"Cascade path: {' -> '.join(cascade_path)}")

        return incident_id

    def get_correlation_attributes(self, incident_id: str) -> Dict[str, Any]:
        """
        Get attributes to inject into all telemetry for this incident.
        These attributes enable correlation across traces, logs, and metrics.

        Args:
            incident_id: The incident to get attributes for

        Returns:
            Dictionary of attributes to add to telemetry
        """
        with self._lock:
            incident = self._active_incidents.get(incident_id)
            if not incident:
                return {}

        return {
            "incident.id": incident.incident_id,
            "incident.root_cause.type": incident.root_cause_type,
            "incident.root_cause.component": incident.root_cause_component,
            "incident.severity": incident.severity,
            "incident.cascade_stage": incident.current_stage,
            "incident.status": incident.status,
            "incident.affected_components": ",".join(incident.affected_components),
        }

    def get_attributes_for_component(self, component: str) -> Dict[str, Any]:
        """
        Get correlation attributes for a specific component.
        Used when generating telemetry to check if the component is affected.

        Args:
            component: The component name (service, device, etc.)

        Returns:
            Correlation attributes if component is affected, empty dict otherwise
        """
        with self._lock:
            incident_ids = self._component_incidents.get(component, [])
            if not incident_ids:
                return {}

            # Return attributes from the first active incident affecting this component
            for incident_id in incident_ids:
                incident = self._active_incidents.get(incident_id)
                if incident and incident.status in ("active", "cascading"):
                    return self.get_correlation_attributes(incident_id)

        return {}

    def advance_cascade(self, incident_id: str) -> Optional[CascadeStage]:
        """
        Advance to next stage of cascade.

        Args:
            incident_id: The incident to advance

        Returns:
            The CascadeStage that was activated, or None if cascade is complete
        """
        with self._lock:
            incident = self._active_incidents.get(incident_id)
            if not incident:
                return None

            if incident.current_stage >= len(incident.cascade_stages):
                incident.status = "active"  # Cascade complete, now just active
                return None

            # Get the next stage
            next_stage = incident.cascade_stages[incident.current_stage]
            next_component = next_stage.component

            # Add to affected components
            if next_component not in incident.affected_components:
                incident.affected_components.append(next_component)

            # Register component -> incident mapping
            if next_component not in self._component_incidents:
                self._component_incidents[next_component] = []
            if incident_id not in self._component_incidents[next_component]:
                self._component_incidents[next_component].append(incident_id)

            incident.current_stage += 1

            logger.info(f"Incident {incident_id} cascade stage {incident.current_stage}: {next_component} ({next_stage.effect})")

            return next_stage

    def is_component_affected(self, incident_id: str, component: str) -> bool:
        """
        Check if a component is affected by a specific incident.

        Args:
            incident_id: The incident to check
            component: The component name

        Returns:
            True if the component is in the affected list
        """
        with self._lock:
            incident = self._active_incidents.get(incident_id)
            if not incident:
                return False
            return component in incident.affected_components

    def is_any_incident_affecting(self, component: str) -> bool:
        """
        Check if any active incident is affecting a component.

        Args:
            component: The component name

        Returns:
            True if any incident affects this component
        """
        with self._lock:
            incident_ids = self._component_incidents.get(component, [])
            for incident_id in incident_ids:
                incident = self._active_incidents.get(incident_id)
                if incident and incident.status in ("active", "cascading"):
                    return True
            return False

    def get_effect_for_component(self, component: str) -> Optional[Dict[str, Any]]:
        """
        Get the effect configuration for a component if it's affected by an incident.

        Args:
            component: The component name

        Returns:
            Effect configuration dict with 'effect' type and 'parameters', or None
        """
        with self._lock:
            incident_ids = self._component_incidents.get(component, [])
            for incident_id in incident_ids:
                incident = self._active_incidents.get(incident_id)
                if incident and incident.status in ("active", "cascading"):
                    # Find the stage for this component
                    for stage in incident.cascade_stages:
                        if stage.component == component:
                            return {
                                "effect": stage.effect,
                                "parameters": stage.parameters or {},
                                "incident_id": incident_id,
                            }
        return None

    def get_incident(self, incident_id: str) -> Optional[IncidentCorrelation]:
        """
        Get incident details as an IncidentCorrelation object.

        Args:
            incident_id: The incident to get

        Returns:
            IncidentCorrelation object or None
        """
        with self._lock:
            incident = self._active_incidents.get(incident_id)
            if not incident:
                return None

            return IncidentCorrelation(
                incident_id=incident.incident_id,
                root_cause_type=incident.root_cause_type,
                root_cause_component=incident.root_cause_component,
                affected_components=incident.affected_components.copy(),
                cascade_path=incident.cascade_path.copy(),
                severity=incident.severity,
                description=incident.description,
            )

    def list_active_incidents(self, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all active incidents, optionally filtered by job.

        Args:
            job_id: Optional job ID to filter by

        Returns:
            List of incident summaries
        """
        with self._lock:
            incidents = []
            for incident_id, incident in self._active_incidents.items():
                if job_id and incident.job_id != job_id:
                    continue
                if incident.status not in ("active", "cascading"):
                    continue

                incidents.append({
                    "incident_id": incident.incident_id,
                    "job_id": incident.job_id,
                    "root_cause_type": incident.root_cause_type,
                    "root_cause_component": incident.root_cause_component,
                    "affected_components": incident.affected_components.copy(),
                    "current_stage": incident.current_stage,
                    "total_stages": len(incident.cascade_stages),
                    "severity": incident.severity,
                    "status": incident.status,
                    "started_at": incident.started_at.isoformat(),
                    "description": incident.description,
                })

            return incidents

    def stop_incident(self, incident_id: str) -> bool:
        """
        Stop an active incident and begin recovery.

        Args:
            incident_id: The incident to stop

        Returns:
            True if incident was stopped, False if not found
        """
        with self._lock:
            incident = self._active_incidents.get(incident_id)
            if not incident:
                return False

            incident.status = "resolved"

            # Clean up component mappings
            for component in incident.affected_components:
                if component in self._component_incidents:
                    if incident_id in self._component_incidents[component]:
                        self._component_incidents[component].remove(incident_id)
                    if not self._component_incidents[component]:
                        del self._component_incidents[component]

            logger.info(f"Incident {incident_id} resolved")
            return True

    def remove_incident(self, incident_id: str) -> bool:
        """
        Completely remove an incident from tracking.

        Args:
            incident_id: The incident to remove

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            incident = self._active_incidents.pop(incident_id, None)
            if not incident:
                return False

            # Clean up component mappings
            for component in incident.affected_components:
                if component in self._component_incidents:
                    if incident_id in self._component_incidents[component]:
                        self._component_incidents[component].remove(incident_id)
                    if not self._component_incidents[component]:
                        del self._component_incidents[component]

            return True

    def cleanup_resolved_incidents(self, max_age_seconds: int = 3600) -> int:
        """
        Remove resolved incidents older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age for resolved incidents

        Returns:
            Number of incidents removed
        """
        now = datetime.now()
        to_remove = []

        with self._lock:
            for incident_id, incident in self._active_incidents.items():
                if incident.status == "resolved":
                    age = (now - incident.started_at).total_seconds()
                    if age > max_age_seconds:
                        to_remove.append(incident_id)

        for incident_id in to_remove:
            self.remove_incident(incident_id)

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} resolved incidents")

        return len(to_remove)

    def cleanup_stale_incidents(self, max_active_age_seconds: int = 86400) -> int:
        """
        Remove all stale incidents (both resolved and long-running active ones).

        This prevents memory leaks from incidents that were never properly resolved
        or have been running for an unreasonably long time.

        Args:
            max_active_age_seconds: Maximum age for active incidents (default 24 hours)

        Returns:
            Number of incidents removed
        """
        now = datetime.now()
        to_remove = []

        with self._lock:
            for incident_id, incident in self._active_incidents.items():
                age = (now - incident.started_at).total_seconds()
                # Remove resolved incidents older than 1 hour
                if incident.status == "resolved" and age > 3600:
                    to_remove.append(incident_id)
                # Remove active incidents older than max_active_age
                elif incident.status in ("active", "cascading") and age > max_active_age_seconds:
                    logger.warning(f"Removing stale active incident {incident_id} (age: {age/3600:.1f}h)")
                    to_remove.append(incident_id)

        for incident_id in to_remove:
            self.remove_incident(incident_id)

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} stale incidents")

        return len(to_remove)
