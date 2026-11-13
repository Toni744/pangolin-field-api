import logging
import os
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path, PurePath, PureWindowsPath
from typing import Annotated, Literal
from uuid import UUID

from azure.core.exceptions import AzureError, ResourceExistsError
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

from app.auth import get_current_user
from app.storage import BlobStore

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "104857600"))

app = FastAPI(title="Pangolin Field Data API", version="0.1.0")
DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"
HTTP_REQUESTS = Counter(
    "pangolin_http_requests_total",
    "HTTP requests served by the Pangolin API.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "pangolin_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)


@app.middleware("http")
async def record_http_metrics(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    started_at = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if request.url.path != "/metrics":
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            HTTP_REQUESTS.labels(
                request.method,
                route_path,
                str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION.labels(request.method, route_path).observe(
                time.perf_counter() - started_at
            )


class SampleResponse(BaseModel):
    sample_id: str
    data_blob_name: str
    metadata_blob_name: str


class SampleStatusResponse(BaseModel):
    sample_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    qc: dict[str, int | float] | None = None
    error: str | None = None


def get_blob_store() -> Iterator[BlobStore]:
    try:
        blob_store = BlobStore.from_environment()
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail="Blob storage is not configured for this service.",
        ) from error
    try:
        yield blob_store
    finally:
        blob_store.close()


def safe_filename(filename: str | None) -> str:
    name = PurePath(PureWindowsPath(filename or "").name).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if safe_name in {"", ".", ".."}:
        return "sample-data.bin"
    return safe_name[:128]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/readyz")
def readyz(
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> dict[str, str]:
    try:
        blob_store.check_readiness()
    except AzureError as error:
        logger.warning("Blob and Queue Storage readiness check failed: %s", error)
        raise HTTPException(
            status_code=503,
            detail="Blob and Queue Storage are not ready.",
        ) from error
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
        raise HTTPException(
            status_code=422, detail="observed_at must include a timezone."
        )
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail="Uploaded file exceeds the configured limit."
        )

    try:
        receipt = blob_store.save_sample(
            sample_id=sample_id,
            submitted_by=str(current_user["sub"]),
            site_code=site_code,
            observed_at=observed_at.astimezone(UTC),
            filename=safe_filename(file.filename),
            content_type=file.content_type or "application/octet-stream",
            stream=file.file,
        )
    except ResourceExistsError as error:
        logger.exception("Blob already exists for sample %s", sample_id)
        raise HTTPException(
            status_code=409, detail="Sample data already exists."
        ) from error
    except AzureError as error:
        logger.exception("Azure Blob Storage request failed for sample %s", sample_id)
        raise HTTPException(
            status_code=503, detail="Could not store sample data."
        ) from error

    return SampleResponse(
        sample_id=str(receipt.sample_id),
        data_blob_name=receipt.data_blob_name,
        metadata_blob_name=receipt.metadata_blob_name,
    )


@app.get("/samples/{sample_id}/status", response_model=SampleStatusResponse)
def get_sample_status(
    sample_id: UUID,
    current_user: Annotated[dict[str, object], Depends(get_current_user)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> SampleStatusResponse:
    try:
        sample_status = blob_store.get_sample_status(
            submitted_by=str(current_user["sub"]),
            sample_id=sample_id,
        )
    except AzureError as error:
        logger.exception(
            "Azure Blob Storage status request failed for sample %s", sample_id
        )
        raise HTTPException(
            status_code=503, detail="Could not retrieve sample status."
        ) from error
    if sample_status is None:
        raise HTTPException(status_code=404, detail="Sample was not found.")
    return SampleStatusResponse(**sample_status)


@app.get("/", include_in_schema=False)
def demo_home() -> FileResponse:
    if os.getenv("PANGOLIN_DEMO_UI_ENABLED", "").casefold() != "true":
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(DEMO_DIR / "index.html")


@app.get("/demo/config.json", include_in_schema=False)
def demo_config() -> dict[str, str]:
    if os.getenv("PANGOLIN_DEMO_UI_ENABLED", "").casefold() != "true":
        raise HTTPException(status_code=404, detail="Not found.")

    tenant_id = os.getenv("ENTRA_EXTERNAL_ID_TENANT_ID", "").strip()
    tenant_domain = os.getenv("ENTRA_EXTERNAL_ID_TENANT_DOMAIN", "").strip()
    user_flow = os.getenv("ENTRA_EXTERNAL_ID_USER_FLOW", "").strip()
    client_id = os.getenv(
        "ENTRA_PUBLIC_CLIENT_ID",
        os.getenv("ENTRA_ALLOWED_CLIENT_ID", ""),
    ).strip()
    audience = os.getenv("ENTRA_API_AUDIENCE", "").strip()
    scope = os.getenv("ENTRA_API_SCOPE", "samples.write").strip()
    if not all((tenant_id, tenant_domain, user_flow, client_id, audience, scope)):
        raise HTTPException(
            status_code=503,
            detail="The interviewer demo identity settings are incomplete.",
        )

    discovery_url = (
        f"https://{tenant_domain}.ciamlogin.com/{tenant_id}/v2.0/"
        f".well-known/openid-configuration?p={user_flow}"
    )
    return {
        "clientId": client_id,
        "authority": f"https://{tenant_domain}.ciamlogin.com/",
        "authorityMetadataUrl": discovery_url,
        "userFlow": user_flow,
        "apiScope": f"api://{audience}/{scope}",
    }


app.mount(
    "/demo/assets",
    StaticFiles(directory=DEMO_DIR / "assets"),
    name="demo-assets",
)
