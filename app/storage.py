import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO
from uuid import UUID

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.queue import QueueClient

logger = logging.getLogger(__name__)

StorageCredential = DefaultAzureCredential | None


def _storage_mode() -> str:
    mode = os.getenv("PANGOLIN_STORAGE_MODE", "azure").strip().casefold()
    if mode not in {"azure", "azurite"}:
        raise ValueError("PANGOLIN_STORAGE_MODE must be 'azure' or 'azurite'.")
    return mode


def _azurite_connection_string() -> str:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if not connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required in Azurite mode.")
    return connection_string


def create_storage_credential() -> StorageCredential:
    if _storage_mode() == "azurite":
        _azurite_connection_string()
        return None
    return DefaultAzureCredential(
        managed_identity_client_id=os.getenv("AZURE_CLIENT_ID")
    )


def create_blob_service_client(
    credential: StorageCredential,
) -> BlobServiceClient:
    if _storage_mode() == "azurite":
        return BlobServiceClient.from_connection_string(_azurite_connection_string())

    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "").strip()
    if not account_url:
        raise ValueError("AZURE_STORAGE_ACCOUNT_URL is required in Azure mode.")
    if credential is None:
        raise ValueError("An Azure credential is required in Azure mode.")
    return BlobServiceClient(account_url=account_url, credential=credential)


def create_queue_client(
    queue_name: str,
    credential: StorageCredential,
) -> QueueClient:
    if _storage_mode() == "azurite":
        return QueueClient.from_connection_string(
            _azurite_connection_string(),
            queue_name=queue_name,
        )

    queue_url = os.getenv("AZURE_STORAGE_QUEUE_URL", "").strip()
    if not queue_url:
        raise ValueError("AZURE_STORAGE_QUEUE_URL is required in Azure mode.")
    if credential is None:
        raise ValueError("An Azure credential is required in Azure mode.")
    return QueueClient(
        account_url=queue_url,
        queue_name=queue_name,
        credential=credential,
    )


@dataclass(frozen=True)
class SampleReceipt:
    sample_id: UUID
    data_blob_name: str
    metadata_blob_name: str


class BlobStore:
    def __init__(
        self,
        service: BlobServiceClient,
        queue: QueueClient,
        container_name: str,
        credential: StorageCredential,
    ):
        self._service = service
        self._queue = queue
        self._container_name = container_name
        self._credential = credential

    def close(self) -> None:
        self._queue.close()
        self._service.close()
        if self._credential is not None:
            self._credential.close()

    @classmethod
    def from_environment(cls) -> "BlobStore":
        container_name = os.getenv("BLOB_CONTAINER_NAME", "").strip()
        queue_name = os.getenv("SAMPLE_JOB_QUEUE_NAME", "").strip()
        if not all((container_name, queue_name)):
            raise ValueError(
                "The Blob container and sample job queue must be configured."
            )

        credential = create_storage_credential()
        service: BlobServiceClient | None = None
        queue: QueueClient | None = None
        try:
            service = create_blob_service_client(credential)
            queue = create_queue_client(queue_name, credential)
            return cls(
                service=service,
                queue=queue,
                container_name=container_name,
                credential=credential,
            )
        except (AzureError, ValueError):
            if queue is not None:
                queue.close()
            if service is not None:
                service.close()
            if credential is not None:
                credential.close()
            raise

    def get_sample_status(
        self, submitted_by: str, sample_id: UUID
    ) -> dict[str, object] | None:
        subject_hash = hashlib.sha256(submitted_by.encode("utf-8")).hexdigest()
        metadata_blob_name = f"users/{subject_hash}/samples/{sample_id}/metadata.json"
        metadata_blob = self._service.get_blob_client(
            self._container_name,
            metadata_blob_name,
        )
        try:
            metadata = json.loads(metadata_blob.download_blob().readall())
        except ResourceNotFoundError:
            return None

        return {
            "sample_id": str(sample_id),
            "status": metadata.get("status", "queued"),
            "qc": metadata.get("qc"),
            "error": metadata.get("processing_error"),
        }

    def check_readiness(self) -> None:
        self._service.get_container_client(
            self._container_name
        ).get_container_properties()
        self._queue.get_queue_properties()

    def save_sample(
        self,
        sample_id: UUID,
        submitted_by: str,
        site_code: str,
        observed_at: datetime,
        filename: str,
        content_type: str,
        stream: BinaryIO,
    ) -> SampleReceipt:
        subject_hash = hashlib.sha256(submitted_by.encode("utf-8")).hexdigest()
        sample_path = f"users/{subject_hash}/samples/{sample_id}"
        data_blob_name = f"{sample_path}/data/{filename}"
        metadata_blob_name = f"{sample_path}/metadata.json"
        container = self._service.get_container_client(self._container_name)
        data_blob = container.get_blob_client(data_blob_name)
        metadata_blob = container.get_blob_client(metadata_blob_name)

        metadata = {
            "sample_id": str(sample_id),
            "submitted_by": submitted_by,
            "site_code": site_code,
            "observed_at": observed_at.isoformat(),
            "filename": filename,
            "content_type": content_type,
            "data_blob_name": data_blob_name,
            "status": "queued",
        }
        data_created = False
        metadata_created = False
        try:
            data_blob.upload_blob(
                stream,
                overwrite=False,
                content_settings=ContentSettings(content_type=content_type),
            )
            data_created = True
            metadata_blob.upload_blob(
                json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
                overwrite=False,
                content_settings=ContentSettings(content_type="application/json"),
            )
            metadata_created = True
            self._queue.send_message(
                json.dumps(
                    {"metadata_blob_name": metadata_blob_name},
                    separators=(",", ":"),
                )
            )
        except AzureError:
            for blob, created in (
                (metadata_blob, metadata_created),
                (data_blob, data_created),
            ):
                if not created:
                    continue
                try:
                    blob.delete_blob()
                except ResourceNotFoundError:
                    pass
                except AzureError:
                    logger.exception(
                        "Could not roll back incomplete sample blob %s", blob.blob_name
                    )
            raise

        return SampleReceipt(sample_id, data_blob_name, metadata_blob_name)
