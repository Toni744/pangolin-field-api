import json
import logging
import os
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO
from uuid import UUID

from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SampleReceipt:
    sample_id: UUID
    data_blob_name: str
    metadata_blob_name: str


class BlobStore:
    def __init__(self, account_url: str, container_name: str, credential: TokenCredential):
        self._service = BlobServiceClient(account_url=account_url, credential=credential)
        self._container_name = container_name

    @classmethod
    def from_environment(cls) -> "BlobStore":
        account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
        container_name = os.getenv("BLOB_CONTAINER_NAME")
        if not account_url or not container_name:
            raise ValueError("AZURE_STORAGE_ACCOUNT_URL and BLOB_CONTAINER_NAME must be set.")

        client_id = os.getenv("AZURE_CLIENT_ID")
        credential = (
            ManagedIdentityCredential(client_id=client_id)
            if client_id
            else DefaultAzureCredential()
        )
        return cls(account_url, container_name, credential)

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

        data_blob.upload_blob(
            stream,
            overwrite=False,
            content_settings=ContentSettings(content_type=content_type),
        )

        metadata = {
            "sample_id": str(sample_id),
            "submitted_by": submitted_by,
            "site_code": site_code,
            "observed_at": observed_at.isoformat(),
            "filename": filename,
            "content_type": content_type,
            "data_blob_name": data_blob_name,
        }
        try:
            metadata_blob.upload_blob(
                json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
                overwrite=False,
                content_settings=ContentSettings(content_type="application/json"),
            )
        except AzureError:
            try:
                data_blob.delete_blob()
            except AzureError:
                logger.exception("Could not remove incomplete sample data blob %s", data_blob_name)
            raise

        return SampleReceipt(sample_id, data_blob_name, metadata_blob_name)
