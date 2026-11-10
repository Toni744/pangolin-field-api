import asyncio
from datetime import datetime, timezone
from uuid import UUID

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import main
from app import auth
from app.storage import SampleReceipt


ISSUER = "https://pangolin-test.ciamlogin.com/tenant-id/v2.0"
JWKS_URL = f"{ISSUER}/discovery/v2.0/keys"
AUDIENCE = "api-client-id"
SCOPE = "samples.write"
SUBJECT = "external-user-subject"


def request_app(method: str, path: str, **kwargs: object) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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


@pytest.fixture
def token_keys(monkeypatch: pytest.MonkeyPatch) -> tuple[object, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    monkeypatch.setenv("ENTRA_EXTERNAL_ID_ISSUER", ISSUER)
    monkeypatch.setenv("ENTRA_EXTERNAL_ID_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("ENTRA_API_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("ENTRA_API_SCOPE", SCOPE)

    class SigningKey:
        key = public_key

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token: str) -> SigningKey:
            _ = _token
            return SigningKey()

    monkeypatch.setattr(auth, "_jwks_client", lambda _: FakeJwksClient())
    return private_key, public_key


def make_token(private_key: object, **overrides: object) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": SUBJECT,
        "scp": SCOPE,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def test_healthz_is_ready_without_azure_configuration() -> None:
    response = request_app("GET", "/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
    assert store.saved[0]["observed_at"] == datetime(2026, 10, 25, 14, 30, tzinfo=timezone.utc)
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
            headers={"Authorization": f"Bearer {make_token(token_keys[0], aud='other-api')}"},
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
            headers={"Authorization": f"Bearer {make_token(token_keys[0], scp='profile.read')}"},
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


def test_create_sample_fails_closed_when_auth_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "ENTRA_EXTERNAL_ID_ISSUER",
        "ENTRA_EXTERNAL_ID_JWKS_URL",
        "ENTRA_API_AUDIENCE",
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


def test_create_sample_rejects_blank_site_code(token_keys: tuple[object, object]) -> None:
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
