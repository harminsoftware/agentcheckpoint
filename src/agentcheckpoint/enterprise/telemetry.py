"""Telemetry Engine for Enterprise.

Provides opt-in aggregate metadata collection to help organizations 
track overall agent success rates, latencies, and token costs.
Licensed under BSL 1.1. Commercial use requires a valid license key.
"""

import os
import time
from typing import Any, Dict
from dataclasses import dataclass

from .license import require_enterprise


@dataclass
class TelemetryEvent:
    event_type: str
    run_id: str
    framework: str
    model: str
    latency_ms: float
    status: str
    step_count: int


class TelemetryEngine:
    """Handles redacted, aggregate organizational telemetry."""

    def __init__(self):
        # Enforce license check at initialization
        require_enterprise("Organizational Telemetry")
        
        # Telemetry is strictly opt-in, even for Enterprise
        self.enabled = os.environ.get("AGENTCHECKPOINT_TELEMETRY", "false").lower() == "true"
        self._endpoints = []

    def configure_export(self, datadog_key: str = None, otlp_endpoint: str = None):
        """Configure where telemetry should be sent (Datadog, OpenTelemetry, etc)."""
        if datadog_key:
            self._endpoints.append(("datadog", datadog_key))
        if otlp_endpoint:
            self._endpoints.append(("otlp", otlp_endpoint))

    def capture_run_metrics(self, event: TelemetryEvent):
        """Capture metrics for a completed or failed run.
        
        Crucially, this NEVER captures message content, tool inputs, 
        prompts, or variables. Only aggregate operational metadata.
        """
        if not self.enabled:
            return

        payload = {
            "timestamp": int(time.time()),
            "metric.name": "agent.lifecycle",
            "tags": {
                "framework": event.framework,
                "model": event.model,
                "status": event.status
            },
            "values": {
                "latency_ms": event.latency_ms,
                "steps": event.step_count
            }
        }

        self._flush(payload)

    def _flush(self, payload: Dict[str, Any]):
        """Send payloads to configured external sinks."""
        # Note: In production, send over async network queue.
        # print(f"[Telemetry] Exporting: {payload}")
        pass
