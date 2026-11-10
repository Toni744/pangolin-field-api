# Pangolin Field Data API

A local-first DevOps practice project for a small field-data ingestion service. The FastAPI service accepts sample metadata and a data file, and can store the file and a JSON sidecar in private Azure Blob Storage.

See [architecture.mmd](./architecture.mmd) for the component and identity/data-flow diagram.

## Current status

- **No project Azure resources are deployed.** The project resource group, Storage account, private container, and signed-in user's `Storage Blob Data Contributor` role assignment were deleted to stop ongoing charges. The uploaded sample files and metadata were deleted with them.
- **No user-assigned managed identity has been created.** Terraform contains a conditional definition for one, but it has not been applied.
- **External ID is partially configured.** The API and public mobile registrations, delegated `samples.write` permission, email-OTP `fieldusersignin` flow, and native `com.pangolinapp://oauthredirect` callback are configured. A one-off authorization-code-with-PKCE test acquired an API access token and passed it through the API's JWT validator; the observed audience and claims are recorded in [the tenant setup record](./docs/external-id-tenant-setup.md). The temporary localhost test redirect has been removed. The Flutter integration is not implemented.
- `GET /healthz` is unauthenticated. `POST /samples` requires a valid bearer access token and the configured `samples.write` scope; it returns an error when authentication is not configured.
- The Docker image has been built and local API tests have passed. GitHub Actions configuration exists, but no Azure deployment pipeline is set up.

Terraform configuration remains in this repository. Applying it can recreate billable Azure resources. Review the plan and expected charges before applying.

## What this first milestone covers

- Python/FastAPI REST API with a health endpoint and sample upload.
- A live Blob upload was verified previously through Azure RBAC, not storage keys; that Azure storage and uploaded data have since been deleted.
- Container image running as a non-root user.
- Terraform definitions for the Storage foundation and optional ACR, managed identity, Container Apps, and Log Analytics stack.
- GitHub Actions CI for tests, image build, Terraform formatting, and validation; no Azure login or deployment.

The planned Container App ingress is internal-only. Do not enable public ingress until an External ID tenant and app registrations are configured, caller authorization is reviewed, and the token flow has been tested end to end.

See [docs/external-user-auth.md](./docs/external-user-auth.md) for tenant setup, API claims configuration, and the Flutter authorization-code-with-PKCE flow. See [docs/external-id-tenant-setup.md](./docs/external-id-tenant-setup.md) for the tenant and API registration IDs.
See [docs/production-readiness-gap-register.md](./docs/production-readiness-gap-register.md) for the production gaps, open design decisions, and suggested delivery order.

## Local API and tests

Python 3.12 or newer is recommended. Create an isolated environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest -q
```

The API health endpoint works without Azure credentials or authentication:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/healthz
```

To upload to Azure Blob Storage, first recreate the storage resources and grant the local developer identity the required Blob data role. No Blob account or role assignment currently exists. After provisioning, set the storage URL and container name, then configure the External ID token-validation settings using values from the tenant's OpenID Connect metadata:

```bash
az login
export AZURE_STORAGE_ACCOUNT_URL="<your storage account blob endpoint>"
export BLOB_CONTAINER_NAME="samples"
export ENTRA_EXTERNAL_ID_ISSUER="https://09611948-7df4-4927-800d-f707197bab70.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0"
export ENTRA_EXTERNAL_ID_JWKS_URL="https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/discovery/v2.0/keys"
export ENTRA_API_AUDIENCE="d0000cca-0900-4c3f-92cf-45e320e62112"
export ENTRA_API_SCOPE="samples.write"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Create a tiny synthetic FASTQ file in the current directory, acquire an access token for the API, then send it with a timezone-aware observation time:

```bash
cat > reads.fastq <<'EOF'
@demo-read
ACGTACGT
+
!!!!!!!!
EOF

curl -X POST http://127.0.0.1:8000/samples \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F 'sample_id=2dbf85de-daa5-4e16-bdbe-c8ab11392400' \
  -F 'site_code=boreal-7' \
  -F 'observed_at=2026-10-25T10:30:00-04:00' \
  -F 'file=@reads.fastq;type=application/octet-stream'
```

The `cat` command creates demo input only. If you have a real file elsewhere, use its path after `file=@` instead. The client supplies a UUID sample ID so retries target stable blob names instead of creating a new copy. Existing blob names are never overwritten; a retry after a completed upload receives a conflict response. The default upload limit is 100 MiB and can be changed with `MAX_UPLOAD_BYTES`. Files and metadata are written as private blobs under the authenticated user's hashed subject namespace. Treat uploaded biological/location data as sensitive; site/organization authorization, ownership-based reads, and data-retention controls are not yet implemented.

When provisioned, the example Storage account configuration uses Standard LRS, requires HTTPS, disables Shared Key authorization and anonymous Blob access, and creates a private container. Data-plane access is controlled by Azure RBAC. These are configuration settings, not currently deployed resources.

## Container

Docker is required to build and run the image locally. The API listens on port 8000:

```bash
docker build -t field-data-api:local .
docker run --rm -p 127.0.0.1:8000:8000 \
  -e AZURE_STORAGE_ACCOUNT_URL \
  -e BLOB_CONTAINER_NAME \
  -e ENTRA_EXTERNAL_ID_ISSUER \
  -e ENTRA_EXTERNAL_ID_JWKS_URL \
  -e ENTRA_API_AUDIENCE \
  -e ENTRA_API_SCOPE \
  field-data-api:local
```

## Terraform

The infrastructure is scoped to the subscription in `subscription_id`. `terraform.tfvars` is local and ignored by Git. The Storage account, container, and developer role assignment are defined in Terraform. `deploy_platform` and `deploy_api` default to `false`; setting `deploy_platform = true` adds ACR, a user-assigned identity, Log Analytics, and the Container Apps environment. The managed identity is granted `AcrPull` and Blob data access in the Terraform configuration. After provisioning and reviewing that foundation, build and push the image, provide the External ID issuer, JWKS URL, audience, and scope, and set `deploy_api = true` with `container_image` to create the Container App.

Before future deployments, verify regional availability, review the Terraform plan and expected charges, and confirm the resources and access model. Blob capacity, transactions, and data transfer can incur charges; ACR, Log Analytics ingestion, and Container Apps can also incur charges.

```bash
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan
```

When you clone this project and `terraform.tfvars` is absent, copy `terraform.tfvars.example` and fill in the subscription and unique names before planning or applying. Always inspect the full plan: an apply can create chargeable resources. The Container App is configured to use its user-assigned identity for `AcrPull` and Blob Storage data access. Storage Shared Key access and anonymous Blob access are disabled in the Terraform configuration. Terraform state can contain sensitive values; keep state private and never commit state or `terraform.tfvars`.

## Follow-up learning milestones

1. Configure External ID app registrations and test OAuth 2.0 token acquisition from a Flutter PKCE client before exposing the API.
2. Move long-running bioinformatics work to an asynchronous queue and Container Apps Jobs; compare with AKS for scheduling, GPU, and operational needs.
3. Add CI security scanning and a separate OIDC-based deployment workflow after a GitHub repository and Azure environments are selected.
4. Add dashboards, actionable alerts, retention controls, and a cost/scale review.
