import logging
import os
import re
from datetime import datetime, timezone
from pathlib import PurePath, PureWindowsPath
from typing import Annotated
from uuid import UUID

from azure.core.exceptions import AzureError, ResourceExistsError
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth import get_current_user
from app.storage import BlobStore

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "104857600"))

app = FastAPI(title="Pangolin Field Data API", version="0.1.0")


class SampleResponse(BaseModel):
    sample_id: str
    data_blob_name: str
    metadata_blob_name: str


def get_blob_store() -> BlobStore:
    try:
        return BlobStore.from_environment()
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail="Blob storage is not configured for this service.",
        ) from error


def safe_filename(filename: str | None) -> str:
    name = PurePath(PureWindowsPath(filename or "").name).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if safe_name in {"", ".", ".."}:
        return "sample-data.bin"
    return safe_name[:128]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/samples", status_code=201, response_model=SampleResponse)
def create_sample(
    sample_id: Annotated[UUID, Form()],
    site_code: Annotated[str, Form(min_length=1, max_length=64)],
    observed_at: Annotated[datetime, Form()],
    file: Annotated[UploadFile, File()],
    current_user: Annotated[dict[str, object], Depends(get_current_user)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> SampleResponse:
    site_code = site_code.strip()
    if not site_code:
        raise HTTPException(status_code=422, detail="site_code must not be blank.")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="observed_at must include a timezone.")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds the configured limit.")

    try:
        receipt = blob_store.save_sample(
            sample_id=sample_id,
            submitted_by=str(current_user["sub"]),
            site_code=site_code,
            observed_at=observed_at.astimezone(timezone.utc),
            filename=safe_filename(file.filename),
            content_type=file.content_type or "application/octet-stream",
            stream=file.file,
        )
    except ResourceExistsError as error:
        logger.exception("Blob already exists for sample %s", sample_id)
        raise HTTPException(status_code=409, detail="Sample data already exists.") from error
    except AzureError as error:
        logger.exception("Azure Blob Storage request failed for sample %s", sample_id)
        raise HTTPException(status_code=503, detail="Could not store sample data.") from error

    return SampleResponse(
        sample_id=str(receipt.sample_id),
        data_blob_name=receipt.data_blob_name,
        metadata_blob_name=receipt.metadata_blob_name,
    )
