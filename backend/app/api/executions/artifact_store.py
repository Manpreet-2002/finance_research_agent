"""Memo artifact storage adapters for local disk and Google Cloud Storage."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import quote

import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import httpx

from ...core.settings import Settings
from ...memo.post_run_memo import MemoWrapperResult

_STORAGE_SCOPE = ("https://www.googleapis.com/auth/devstorage.read_write",)


@dataclass(frozen=True)
class MemoArtifactPublishResult:
    """Resolved memo references after the worker persists artifacts."""

    memo_pdf_path: str | None = None
    memo_pdf_reference: str | None = None


@dataclass(frozen=True)
class DownloadedMemoArtifact:
    """Memo artifact payload loaded from external storage."""

    content: bytes
    media_type: str


class MemoArtifactStore:
    """Contract for storing and retrieving memo artifacts."""

    def publish(
        self,
        *,
        run_id: str,
        memo_result: MemoWrapperResult,
    ) -> MemoArtifactPublishResult:
        raise NotImplementedError

    def download(self, reference: str) -> DownloadedMemoArtifact:
        raise NotImplementedError

    def uses_local_paths(self) -> bool:
        return False


class LocalMemoArtifactStore(MemoArtifactStore):
    """No-op artifact storage that keeps memo paths on the local filesystem."""

    def publish(
        self,
        *,
        run_id: str,  # noqa: ARG002
        memo_result: MemoWrapperResult,
    ) -> MemoArtifactPublishResult:
        memo_pdf_path = str(memo_result.pdf_path) if memo_result.pdf_path else None
        return MemoArtifactPublishResult(
            memo_pdf_path=memo_pdf_path,
            memo_pdf_reference=None,
        )

    def download(self, reference: str) -> DownloadedMemoArtifact:  # pragma: no cover - defensive
        raise RuntimeError(f"Local memo artifact store cannot download reference: {reference}")

    def uses_local_paths(self) -> bool:
        return True


class GcsMemoArtifactStore(MemoArtifactStore):
    """Uploads memo artifacts to Google Cloud Storage and downloads them via the JSON API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bucket = str(settings.gcs_memo_bucket).strip()
        self.prefix = str(settings.gcs_memo_prefix).strip().strip("/")
        if not self.bucket:
            raise ValueError("GCS_MEMO_BUCKET is required when MEMO_ARTIFACT_STORE=gcs.")
        self._logger = logging.getLogger("finance_research_agent.api.memo_artifact_store")

    def publish(
        self,
        *,
        run_id: str,
        memo_result: MemoWrapperResult,
    ) -> MemoArtifactPublishResult:
        if memo_result.pdf_path is None:
            return MemoArtifactPublishResult()

        pdf_key = self._object_key(run_id=run_id, filename=memo_result.pdf_path.name)
        self._upload_file(
            local_path=memo_result.pdf_path,
            object_name=pdf_key,
            content_type="application/pdf",
        )

        if memo_result.manifest_path.exists():
            manifest_key = self._object_key(run_id=run_id, filename=memo_result.manifest_path.name)
            self._upload_file(
                local_path=memo_result.manifest_path,
                object_name=manifest_key,
                content_type="application/json",
            )

        gs_reference = f"gs://{self.bucket}/{pdf_key}"
        self._logger.info(
            "memo_artifacts_uploaded run_id=%s bucket=%s pdf=%s",
            run_id,
            self.bucket,
            pdf_key,
        )
        return MemoArtifactPublishResult(
            memo_pdf_path=None,
            memo_pdf_reference=gs_reference,
        )

    def download(self, reference: str) -> DownloadedMemoArtifact:
        bucket, object_name = _parse_gs_reference(reference)
        token = self._access_token()
        encoded_object = quote(object_name, safe="")
        url = (
            "https://storage.googleapis.com/download/storage/v1/"
            f"b/{bucket}/o/{encoded_object}?alt=media"
        )
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
        )
        response.raise_for_status()
        media_type = guess_type(object_name)[0] or "application/octet-stream"
        return DownloadedMemoArtifact(
            content=response.content,
            media_type=media_type,
        )

    def _upload_file(
        self,
        *,
        local_path: Path,
        object_name: str,
        content_type: str,
    ) -> None:
        service = build("storage", "v1", credentials=self._credentials(), cache_discovery=False)
        media = MediaFileUpload(
            str(local_path),
            mimetype=content_type,
            resumable=False,
        )
        service.objects().insert(
            bucket=self.bucket,
            name=object_name,
            media_body=media,
        ).execute()

    def _object_key(self, *, run_id: str, filename: str) -> str:
        root = f"{self.prefix}/" if self.prefix else ""
        return f"{root}{run_id}/{filename}"

    def _credentials(self):
        credentials, _ = google.auth.default(scopes=_STORAGE_SCOPE)
        if not credentials.valid or not getattr(credentials, "token", None):
            credentials.refresh(GoogleAuthRequest())
        return credentials

    def _access_token(self) -> str:
        credentials = self._credentials()
        token = str(getattr(credentials, "token", "") or "").strip()
        if not token:
            raise RuntimeError("Application default credentials did not yield a storage access token.")
        return token


def build_memo_artifact_store(settings: Settings) -> MemoArtifactStore:
    """Build the memo artifact store for the active environment."""

    mode = str(settings.memo_artifact_store).strip().lower()
    if mode == "gcs":
        return GcsMemoArtifactStore(settings=settings)
    return LocalMemoArtifactStore()


def is_gcs_reference(value: str | None) -> bool:
    return str(value or "").strip().startswith("gs://")


def is_http_reference(value: str | None) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://")


def _parse_gs_reference(reference: str) -> tuple[str, str]:
    normalized = str(reference).strip()
    if not normalized.startswith("gs://"):
        raise ValueError(f"Unsupported GCS reference: {reference}")
    remainder = normalized.removeprefix("gs://")
    bucket, _, object_name = remainder.partition("/")
    if not bucket or not object_name:
        raise ValueError(f"Invalid GCS reference: {reference}")
    return bucket, object_name
