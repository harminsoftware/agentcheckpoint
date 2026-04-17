"""Policy-based auto-resume engine.

Define YAML policies that automatically handle different failure types:
- Rate limit errors → wait and retry
- Context overflow → compress history and resume
- Unknown errors → notify on-call

Usage:
    from agentcheckpoint.enterprise.auto_resume import AutoResumeEngine

    engine = AutoResumeEngine("policies.yaml")
    engine.handle_failure(run_id, error)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agentcheckpoint.enterprise import require_enterprise

logger = logging.getLogger(__name__)


@dataclass
class ResumePolicy:
    """A single auto-resume policy."""

    match: dict[str, str]  # e.g., {"error_type": "RateLimitError"}
    action: dict[str, Any]  # e.g., {"wait": 60, "resume": True}
    name: str = ""
    max_retries: int = 3


@dataclass
class PolicyResult:
    """Result of policy evaluation."""

    matched: bool = False
    policy_name: str = ""
    should_resume: bool = False
    wait_seconds: int = 0
    compress_history: bool = False
    notify_channel: str = ""
    notify_message: str = ""


class AutoResumeEngine:
    """Evaluates failure policies and takes automatic recovery actions."""

    def __init__(self, policy_file: str | Path | None = None, policies: list[dict] | None = None):
        require_enterprise("Policy-Based Auto-Resume")

        self._policies: list[ResumePolicy] = []
        self._retry_counts: dict[str, int] = {}  # run_id -> retry count

        if policy_file:
            self._load_from_file(policy_file)
        if policies:
            self._load_from_dicts(policies)

    def _load_from_file(self, path: str | Path) -> None:
        """Load policies from a YAML file."""
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required for policy files. pip install pyyaml")

        with open(path) as f:
            data = yaml.safe_load(f)

        self._load_from_dicts(data.get("policies", []))

    def _load_from_dicts(self, policies: list[dict]) -> None:
        """Load policies from a list of dicts."""
        for i, p in enumerate(policies):
            self._policies.append(
                ResumePolicy(
                    match=p.get("match", {}),
                    action=p.get("action", {}),
                    name=p.get("name", f"policy_{i}"),
                    max_retries=p.get("max_retries", 3),
                )
            )

    def evaluate(self, run_id: str, error_type: str, error_message: str = "") -> PolicyResult:
        """Evaluate policies against a failure and return the action to take."""
        for policy in self._policies:
            if self._matches(policy, error_type, error_message):
                # Check retry limit
                retries = self._retry_counts.get(run_id, 0)
                if retries >= policy.max_retries:
                    logger.warning(
                        f"Max retries ({policy.max_retries}) reached for "
                        f"run={run_id}, policy={policy.name}"
                    )
                    return PolicyResult(
                        matched=True,
                        policy_name=policy.name,
                        should_resume=False,
                        notify_channel="oncall",
                        notify_message=f"Max retries exceeded for run {run_id}",
                    )

                self._retry_counts[run_id] = retries + 1

                return PolicyResult(
                    matched=True,
                    policy_name=policy.name,
                    should_resume=policy.action.get("resume", False),
                    wait_seconds=policy.action.get("wait", 0),
                    compress_history=policy.action.get("compress_history", False),
                    notify_channel=policy.action.get("notify", ""),
                    notify_message=policy.action.get("message", f"Auto-resume triggered for {run_id}"),
                )

        return PolicyResult(matched=False)

    def handle_failure(
        self,
        run_id: str,
        error: BaseException,
        storage_path: str = "./checkpoints",
    ) -> PolicyResult:
        """Evaluate policies and execute the matching action.

        This is the main entry point. It evaluates the error against all
        policies, waits if needed, and triggers resume if the policy says to.
        """
        error_type = type(error).__name__
        result = self.evaluate(run_id, error_type, str(error))

        if not result.matched:
            logger.info(f"No policy matched for {error_type} in run={run_id}")
            return result

        logger.info(
            f"Policy '{result.policy_name}' matched for {error_type} in run={run_id}. "
            f"Action: resume={result.should_resume}, wait={result.wait_seconds}s"
        )

        # Send notification if configured
        if result.notify_channel:
            self._notify(result.notify_channel, result.notify_message)

        # Wait if configured
        if result.wait_seconds > 0:
            logger.info(f"Waiting {result.wait_seconds}s before resume...")
            time.sleep(result.wait_seconds)

        # Resume if configured
        if result.should_resume:
            from agentcheckpoint.resume import resume
            try:
                resume_result = resume(run_id=run_id, storage_path=storage_path)
                logger.info(f"Auto-resumed run={run_id} from step={resume_result.step_number}")
            except Exception as e:
                logger.error(f"Auto-resume failed for run={run_id}: {e}")
                result.should_resume = False

        return result

    def _matches(self, policy: ResumePolicy, error_type: str, error_message: str) -> bool:
        """Check if a policy matches the given error."""
        match_type = policy.match.get("error_type", "*")
        if match_type != "*" and match_type != error_type:
            return False

        match_message = policy.match.get("error_message", "")
        if match_message and match_message not in error_message:
            return False

        return True

    def _notify(self, channel: str, message: str) -> None:
        """Send notification to a channel. Override for custom integrations."""
        # Default: just log it. Override for Slack, PagerDuty, email, etc.
        logger.info(f"Notification [{channel}]: {message}")

    def reset_retries(self, run_id: str | None = None) -> None:
        """Reset retry counters."""
        if run_id:
            self._retry_counts.pop(run_id, None)
        else:
            self._retry_counts.clear()
