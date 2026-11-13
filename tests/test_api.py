import asyncio
from datetime import UTC, datetime
from uuid import UUID

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import auth, main
from app.storage import SampleDownload, SampleNotReadyError, SampleReceipt

ISSUER = "https://pangolin-test.ciamlogin.com/tenant-id/v2.0"
JWKS_URL = f"{ISSUER}/discovery/v2.0/keys"
AUDIENCE = "api-client-id"
SCOPE = "samples.write"
SUBJECT = "external-user-subject"
MOBILE_CLIENT_ID = "927109f8-f2d7-4e2d-94b2-eb26f3d02cba"


def request_app(method: str, path: str, **kwargs: object) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send_request())


class MemoryBlobStore:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []

    def save_sample(self, **kwargs: object) -> SampleReceipt:
        sample_id = kwargs["sample_id"]
        assert isinstance(sample_id, UUID)
        self.saved.append(kwargs)
        return SampleReceipt(
            sample_id=sample_id,
            data_blob_name=f"users/test/samples/{sample_id}/data/reads.fastq",
            metadata_blob_name=f"users/test/samples/{sample_id}/metadata.json",
        )

    def get_sample_status(
        self,
        submitted_by: str,
        sample_id: UUID,
    ) -> dict[str, object] | None:
        for sample in self.saved:
            if (
                sample["sample_id"] == sample_id
                and sample["submitted_by"] == submitted_by
            ):
                return {
                    "sample_id": str(sample_id),
                    "status": sample.get("status", "queued"),
                    "qc": sample.get("qc"),
                    "error": sample.get("error"),
                }
        return None

    def list_samples(self, submitted_by: str, limit: int) -> list[dict[str, object]]:
        return [
            {
                "sample_id": str(sample["sample_id"]),
                "filename": sample["filename"],
                "site_code": sample["site_code"],
                "observed_at": sample["observed_at"],
                "status": sample.get("status", "queued"),
                "qc": sample.get("qc"),
                "error": sample.get("error"),
            }
            for sample in self.saved
            if sample["submitted_by"] == submitted_by
        ][:limit]

    def get_sample_data(
        self, submitted_by: str, sample_id: UUID
    ) -> SampleDownload | None:
        for sample in self.saved:
            if (
                sample["sample_id"] == sample_id
                and sample["submitted_by"] == submitted_by
            ):
                if sample.get("status") != "completed":
                    raise SampleNotReadyError("Sample processing is not complete.")
                return SampleDownload(
                    filename=str(sample["filename"]),
                    content_type="application/octet-stream",
                    content=b"@PANGOLIN\nACGT\n+\nIIII\n",
                )
        return None

    def get_sample_report(
        self, submitted_by: str, sample_id: UUID
    ) -> SampleDownload | None:
        for sample in self.saved:
            if (
                sample["sample_id"] == sample_id
                and sample["submitted_by"] == submitted_by
            ):
                if sample.get("status") != "completed":
                    raise SampleNotReadyError("Sample processing is not complete.")
                return SampleDownload(
                    filename=f"{sample_id}-qc.json",
                    content_type="application/json",
                    content=b'{"read_count":1,"base_count":4}',
                )
        return None

    def check_readiness(self) -> None:
        return None


@pytest.fixture
def token_keys(monkeypatch: pytest.MonkeyPatch) -> tuple[object, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    monkeypatch.setenv("ENTRA_EXTERNAL_ID_ISSUER", ISSUER)
    monkeypatch.setenv("ENTRA_EXTERNAL_ID_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("ENTRA_API_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("ENTRA_API_SCOPE", SCOPE)
    monkeypatch.setenv("ENTRA_ALLOWED_CLIENT_ID", MOBILE_CLIENT_ID)

    class SigningKey:
        key = public_key

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token: str) -> SigningKey:
            _ = _token
            return SigningKey()

    monkeypatch.setattr(auth, "_jwks_client", lambda _: FakeJwksClient())
    return private_key, public_key


def make_token(private_key: object, **overrides: object) -> str:
    now = int(datetime.now(UTC).timestamp())
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": SUBJECT,
        "scp": SCOPE,
        "azp": MOBILE_CLIENT_ID,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(
        claims, private_key, algorithm="RS256", headers={"kid": "test-key"}
    )


def test_healthz_is_ready_without_azure_configuration() -> None:
    response = request_app("GET", "/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_web_routes_are_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PANGOLIN_WEB_UI_ENABLED", "false")

    home_response = request_app("GET", "/")
    config_response = request_app("GET", "/config.json")

    assert home_response.status_code == 404
    assert config_response.status_code == 404


def test_web_config_uses_external_id_spa_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PANGOLIN_WEB_UI_ENABLED", "true")
    monkeypatch.setenv("ENTRA_EXTERNAL_ID_TENANT_ID", "tenant-id")
    monkeypatch.setenv("ENTRA_EXTERNAL_ID_TENANT_DOMAIN", "pangolincustomers")
    monkeypatch.setenv("ENTRA_EXTERNAL_ID_USER_FLOW", "fieldusersignin")
    monkeypatch.setenv("ENTRA_PUBLIC_CLIENT_ID", "spa-client-id")
    monkeypatch.setenv("ENTRA_API_AUDIENCE", "api-client-id")
    monkeypatch.setenv("ENTRA_API_SCOPE", SCOPE)

    response = request_app("GET", "/config.json")

    assert response.status_code == 200
    assert response.json() == {
        "clientId": "spa-client-id",
        "authority": "https://pangolincustomers.ciamlogin.com/",
        "authorityMetadataUrl": (
            "https://pangolincustomers.ciamlogin.com/tenant-id/v2.0/"
            ".well-known/openid-configuration?p=fieldusersignin"
        ),
        "userFlow": "fieldusersignin",
        "apiScope": "api://api-client-id/samples.write",
    }


def test_readyz_requires_storage_configuration() -> None:
    response = request_app("GET", "/readyz")

    assert response.status_code == 503


def test_sample_status_is_limited_to_the_submitting_user(
    token_keys: tuple[object, object],
) -> None:
    store = MemoryBlobStore()
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    sample_id = UUID("2dbf85de-daa5-4e16-bdbe-c8ab11392400")
    try:
        upload_response = request_app(
            "POST",
            "/samples",
            headers={"Authorization": f"Bearer {make_token(token_keys[0])}"},
            data={
                "sample_id": str(sample_id),
                "site_code": "boreal-7",
                "observed_at": "2026-10-25T10:30:00-04:00",
            },
            files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
        )
        status_response = request_app(
            "GET",
            f"/samples/{sample_id}/status",
            headers={"Authorization": f"Bearer {make_token(token_keys[0])}"},
        )
        other_user_response = request_app(
            "GET",
            f"/samples/{sample_id}/status",
            headers={
                "Authorization": f"Bearer {make_token(token_keys[0], sub='another-user')}"
            },
        )
    finally:
        main.app.dependency_overrides.clear()

    assert upload_response.status_code == 201
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "queued"
    assert other_user_response.status_code == 404


def test_sample_library_and_downloads_are_limited_to_the_submitting_user(
    token_keys: tuple[object, object],
) -> None:
    store = MemoryBlobStore()
    sample_id = UUID("2dbf85de-daa5-4e16-bdbe-c8ab11392400")
    store.saved.append(
        {
            "sample_id": sample_id,
            "submitted_by": SUBJECT,
            "filename": "reads.fastq",
            "site_code": "boreal-7",
            "observed_at": datetime(2026, 10, 25, 14, 30, tzinfo=UTC),
            "status": "completed",
        }
    )
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    own_token = make_token(token_keys[0])
    other_token = make_token(token_keys[0], sub="another-user")
    try:
        own_list = request_app(
            "GET",
            "/samples",
            headers={"Authorization": f"Bearer {own_token}"},
        )
        other_list = request_app(
            "GET",
            "/samples",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        own_data = request_app(
            "GET",
            f"/samples/{sample_id}/data",
            headers={"Authorization": f"Bearer {own_token}"},
        )
        other_data = request_app(
            "GET",
            f"/samples/{sample_id}/data",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        own_report = request_app(
            "GET",
            f"/samples/{sample_id}/report",
            headers={"Authorization": f"Bearer {own_token}"},
        )
        other_report = request_app(
            "GET",
            f"/samples/{sample_id}/report",
            headers={"Authorization": f"Bearer {other_token}"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert own_list.status_code == 200
    assert len(own_list.json()["samples"]) == 1
    assert own_list.json()["samples"][0]["filename"] == "reads.fastq"
    assert other_list.status_code == 200
    assert other_list.json()["samples"] == []
    assert own_data.status_code == 200
    assert own_data.content == b"@PANGOLIN\nACGT\n+\nIIII\n"
    assert (
        own_data.headers["content-disposition"] == 'attachment; filename="reads.fastq"'
    )
    assert own_data.headers["cache-control"] == "private, no-store"
    assert other_data.status_code == 404
    assert own_report.status_code == 200
    assert own_report.json() == {"read_count": 1, "base_count": 4}
    assert other_report.status_code == 404


def test_sample_download_is_unavailable_until_processing_completes(
    token_keys: tuple[object, object],
) -> None:
    store = MemoryBlobStore()
    sample_id = UUID("2dbf85de-daa5-4e16-bdbe-c8ab11392400")
    store.saved.append(
        {
            "sample_id": sample_id,
            "submitted_by": SUBJECT,
            "filename": "reads.fastq",
            "site_code": "boreal-7",
            "observed_at": datetime(2026, 10, 25, 14, 30, tzinfo=UTC),
            "status": "processing",
        }
    )
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    try:
        response = request_app(
            "GET",
            f"/samples/{sample_id}/data",
            headers={"Authorization": f"Bearer {make_token(token_keys[0])}"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "Sample processing is not complete."


def test_create_sample_uploads_to_storage_dependency(
    token_keys: tuple[object, object],
) -> None:
    store = MemoryBlobStore()
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    try:
        response = request_app(
            "POST",
            "/samples",
            headers={"Authorization": f"Bearer {make_token(token_keys[0])}"},
            data={
                "sample_id": "2dbf85de-daa5-4e16-bdbe-c8ab11392400",
                "site_code": " boreal-7 ",
                "observed_at": "2026-10-25T10:30:00-04:00",
            },
            files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["sample_id"] == "2dbf85de-daa5-4e16-bdbe-c8ab11392400"
    assert response.json()["data_blob_name"].endswith("/data/reads.fastq")
    assert len(store.saved) == 1
    assert store.saved[0]["site_code"] == "boreal-7"
    assert store.saved[0]["observed_at"] == datetime(2026, 10, 25, 14, 30, tzinfo=UTC)
    assert store.saved[0]["submitted_by"] == SUBJECT


def test_create_sample_requires_bearer_token() -> None:
    response = request_app(
        "POST",
        "/samples",
        data={
            "sample_id": "2dbf85de-daa5-4e16-bdbe-c8ab11392400",
            "site_code": "boreal-7",
            "observed_at": "2026-10-25T10:30:00-04:00",
        },
        files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
    )

    assert response.status_code == 401


def test_create_sample_rejects_wrong_audience(
    token_keys: tuple[object, object],
) -> None:
    store = MemoryBlobStore()
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    try:
        response = request_app(
            "POST",
            "/samples",
            headers={
                "Authorization": f"Bearer {make_token(token_keys[0], aud='other-api')}"
            },
            data={
                "sample_id": "2dbf85de-daa5-4e16-bdbe-c8ab11392400",
                "site_code": "boreal-7",
                "observed_at": "2026-10-25T10:30:00-04:00",
            },
            files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 401
    assert store.saved == []


def test_create_sample_requires_upload_scope(
    token_keys: tuple[object, object],
) -> None:
    store = MemoryBlobStore()
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    try:
        response = request_app(
            "POST",
            "/samples",
            headers={
                "Authorization": f"Bearer {make_token(token_keys[0], scp='profile.read')}"
            },
            data={
                "sample_id": "2dbf85de-daa5-4e16-bdbe-c8ab11392400",
                "site_code": "boreal-7",
                "observed_at": "2026-10-25T10:30:00-04:00",
            },
            files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 403
    assert store.saved == []


def test_create_sample_rejects_unregistered_client(
    token_keys: tuple[object, object],
) -> None:
    store = MemoryBlobStore()
    token = make_token(token_keys[0], azp="another-mobile-app")
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    try:
        response = request_app(
            "POST",
            "/samples",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "sample_id": "2dbf85de-daa5-4e16-bdbe-c8ab11392400",
                "site_code": "boreal-7",
                "observed_at": "2026-10-25T10:30:00-04:00",
            },
            files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 403
    assert store.saved == []


def test_create_sample_rejects_missing_authorized_client(
    token_keys: tuple[object, object],
) -> None:
    private_key, _ = token_keys
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": SUBJECT,
        "scp": SCOPE,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int(datetime.now(UTC).timestamp()) + 300,
    }
    token = jwt.encode(
        claims, private_key, algorithm="RS256", headers={"kid": "test-key"}
    )
    response = request_app(
        "POST",
        "/samples",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "sample_id": "2dbf85de-daa5-4e16-bdbe-c8ab11392400",
            "site_code": "boreal-7",
            "observed_at": "2026-10-25T10:30:00-04:00",
        },
        files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
    )

    assert response.status_code == 403


def test_create_sample_fails_closed_when_auth_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "ENTRA_EXTERNAL_ID_ISSUER",
        "ENTRA_EXTERNAL_ID_JWKS_URL",
        "ENTRA_API_AUDIENCE",
        "ENTRA_ALLOWED_CLIENT_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    response = request_app(
        "POST",
        "/samples",
        headers={"Authorization": "Bearer placeholder"},
        data={
            "sample_id": "2dbf85de-daa5-4e16-bdbe-c8ab11392400",
            "site_code": "boreal-7",
            "observed_at": "2026-10-25T10:30:00-04:00",
        },
        files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
    )

    assert response.status_code == 503


def test_create_sample_rejects_timezone_naive_timestamp(
    token_keys: tuple[object, object],
) -> None:
    store = MemoryBlobStore()
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    try:
        response = request_app(
            "POST",
            "/samples",
            headers={"Authorization": f"Bearer {make_token(token_keys[0])}"},
            data={
                "sample_id": "2dbf85de-daa5-4e16-bdbe-c8ab11392400",
                "site_code": "boreal-7",
                "observed_at": "2026-10-25T10:30:00",
            },
            files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert store.saved == []


def test_create_sample_rejects_blank_site_code(
    token_keys: tuple[object, object],
) -> None:
    store = MemoryBlobStore()
    main.app.dependency_overrides[main.get_blob_store] = lambda: store
    try:
        response = request_app(
            "POST",
            "/samples",
            headers={"Authorization": f"Bearer {make_token(token_keys[0])}"},
            data={
                "sample_id": "2dbf85de-daa5-4e16-bdbe-c8ab11392400",
                "site_code": "   ",
                "observed_at": "2026-10-25T10:30:00-04:00",
            },
            files={"file": ("reads.fastq", b"ACGT", "application/octet-stream")},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert store.saved == []
