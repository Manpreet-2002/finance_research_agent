"""Execution launch adapters for background threads or Cloud Run jobs."""

from __future__ import annotations

from dataclasses import dataclass
import logging

import httpx
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest

from ...core.settings import Settings
from .models import ExecutionRecord

_CLOUD_PLATFORM_SCOPE = ("https://www.googleapis.com/auth/cloud-platform",)


@dataclass(frozen=True)
class ExecutionLaunchResult:
    """Metadata returned after handing execution off to an external runner."""

    job_execution_name: str | None = None


class ExecutionLauncher:
    """Contract for handing a claimed execution to an external runtime."""

    def launch(self, execution: ExecutionRecord) -> ExecutionLaunchResult:
        raise NotImplementedError


class NoopExecutionLauncher(ExecutionLauncher):
    """No-op launcher used for local/manual flows."""

    def launch(self, execution: ExecutionRecord) -> ExecutionLaunchResult:  # noqa: ARG002
        return ExecutionLaunchResult()


class CloudRunJobExecutionLauncher(ExecutionLauncher):
    """Launches a Cloud Run job execution via the v2 REST API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._logger = logging.getLogger("finance_research_agent.api.execution_launcher")

    def launch(self, execution: ExecutionRecord) -> ExecutionLaunchResult:
        project_id = self.settings.cloud_run_job_project_id.strip()
        region = self.settings.cloud_run_job_region.strip()
        job_name = self.settings.cloud_run_job_name.strip()
        env_name = self.settings.cloud_run_job_execution_env_name.strip() or "EXECUTION_ID"

        if not project_id or not region or not job_name:
            raise RuntimeError(
                "Cloud Run job launcher requires CLOUD_RUN_JOB_PROJECT_ID, "
                "CLOUD_RUN_JOB_REGION, and CLOUD_RUN_JOB_NAME."
            )

        container_override: dict[str, object] = {
            "env": [
                {
                    "name": env_name,
                    "value": execution.id,
                }
            ]
        }
        container_name = self.settings.cloud_run_job_container_name.strip()
        if container_name:
            container_override["name"] = container_name

        payload = {
            "overrides": {
                "containerOverrides": [container_override],
            }
        }
        url = (
            "https://run.googleapis.com/v2/"
            f"projects/{project_id}/locations/{region}/jobs/{job_name}:run"
        )
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
        }

        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        operation_name = str(data.get("name") or "").strip() or None
        self._logger.info(
            "cloud_run_job_execution_started execution_id=%s run_id=%s operation=%s",
            execution.id,
            execution.run_id,
            operation_name,
        )
        return ExecutionLaunchResult(job_execution_name=operation_name)

    def _access_token(self) -> str:
        credentials, _ = google.auth.default(scopes=_CLOUD_PLATFORM_SCOPE)
        if not credentials.valid or not getattr(credentials, "token", None):
            credentials.refresh(GoogleAuthRequest())
        token = str(getattr(credentials, "token", "") or "").strip()
        if not token:
            raise RuntimeError("Application default credentials did not yield an access token.")
        return token


def build_execution_launcher(settings: Settings) -> ExecutionLauncher:
    """Build the launch adapter for the configured dispatch mode."""

    mode = str(settings.execution_dispatch_mode).strip().lower()
    if mode == "cloud_run_job":
        return CloudRunJobExecutionLauncher(settings=settings)
    return NoopExecutionLauncher()
