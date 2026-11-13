# Pangolin Field Data Platform

Pangolin is a DevOps portfolio project for authenticated field-data uploads and
asynchronous FASTQ quality-control processing. It uses FastAPI, Azure Blob and
Queue Storage, AKS, Helm, Terraform, Microsoft Entra External ID, and GitHub
Actions.

For a concise walkthrough, local demo instructions, architecture, and honest
scope/limitations, see the [interviewer demo guide](./docs/interviewer-demo.md).

## Status

The application and deployment configuration are **not deployed to Azure**.
Terraform is opt-in; enabling it creates billable resources. The current code
provides:

- An API that validates External ID access tokens and queues uploads.
- A worker that validates four-line FASTQ records and reports basic read,
  base, GC, and mean-quality statistics.
- Retry and poison-queue handling, owner-scoped sample status, and Prometheus
  metrics.
- An AKS Helm chart, Terraform foundation, CI checks, and a manual OIDC
  deployment workflow.

The Flutter client, site/organization authorization, public TLS ingress,
operational dashboards/alerts, remote Terraform state, and a production
bioinformatics pipeline are not implemented. Processing uses CPU only. The
root Container Apps Terraform is retired; use only
[`infra/terraform/aks`](./infra/terraform/aks) and
[`deploy/helm/pangolin`](./deploy/helm/pangolin).

## Local development

Python 3.12 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Interview demo (local)

Docker Compose runs the API, worker, and Azurite Blob/Queue emulator; it does
not provision Azure compute or Storage resources. Browser sign-in still uses
the Pangolin External ID tenant and requires internet access. Check that
tenant's billing terms before inviting additional users.

Before the first sign-in, add `http://localhost:8081/` as a **Single-page
application** redirect URI on the existing Pangolin public client registration
(`927109f8-f2d7-4e2d-94b2-eb26f3d02cba`) in the External ID tenant. Keep its
existing native redirect URI and client type; do not add a client secret. The
app must remain assigned to the `fieldusersignin` user flow and have the
`samples.write` delegated API permission.

```bash
docker compose up --build -d
docker compose ps
```

Open [http://localhost:8081](http://localhost:8081), sign in with email, then
choose **Use a synthetic demo sample** or select a small plain-text `.fastq`
file. The page shows the upload, queue, worker, and QC result. Watch worker
logs with `docker compose logs -f worker`.

All Blob and Queue data stays in the local `azurite-data` volume. Stop the
services with `docker compose down`; remove the demo data as well with
`docker compose down -v`. Do not upload real patient or location data.

The emulator-backed API → Blob → Queue → worker test can also be run with
`bash scripts/test-azurite-e2e.sh`.

Run the API and check its unauthenticated health endpoint:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/healthz
```

For Azure-backed development outside the local demo, provision a private
`samples` container and the `sample-jobs` and `sample-jobs-poison` queues. Grant
the developer identity the API's Blob and Queue roles, then follow
[External ID setup](./docs/external-user-auth.md) for API settings. Run
`python -m app.worker` in a second terminal.

## AKS deployment

The AKS configuration defaults to `deploy_platform = false`. Before enabling
it, confirm the subscription, region and quotas, unique resource names,
dedicated Entra admin group, trusted API-server CIDR, and expected cost. AKS
uses a minimum two-node CPU system pool and incurs charges while running.

```bash
cd infra/terraform/aks
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars locally.
terraform init
terraform fmt -check
terraform validate
terraform plan
```

Review the full plan before applying. Keep Terraform state, plans, credentials,
and `terraform.tfvars` private. The release workflow is manual and requires a
protected GitHub `aks-deploy` environment, Azure OIDC configuration, and a
stable-egress self-hosted runner labeled `pangolin-aks`. Bootstrap the
restricted `pangolin` namespace before deploying. Public access additionally
requires a TLS-capable ingress controller and DNS; chart ingress is disabled
by default.

If GitHub's OIDC token subject uses immutable owner and repository IDs, set
`github_oidc_repository` to the exact `owner@ID/repository@ID` subject value.

The browser demo is also disabled by default in Helm. To enable it, set
`demo.enabled=true` and provide `demo.tenantId`, `demo.tenantDomain`,
`demo.userFlow`, and `demo.publicClientId`, then register the public HTTPS
origin as a single-page application redirect URI in the customer tenant.

The interview-specific cleanup workflow is scheduled for November 15, 2026,
at 6 p.m. Mountain Standard Time. It requires `enable_demo_cleanup=true` and
the `aks-cleanup` GitHub environment's `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
and `AZURE_SUBSCRIPTION_ID` variables. Its identity has Contributor access
only to the dedicated `rg-pangolin-aks-interview` resource group. Deletion
permanently removes its uploaded data. GitHub schedules can be delayed or
missed; monitor the run and costs, and use the workflow's manual delete option
if necessary. The Entra administrator group is outside that resource group.

## Verification

Locally verified: unit tests, the Azurite-backed API → Blob → Queue → worker
integration test, Docker Compose build and health/readiness checks, Ruff,
Bandit, `pip-audit`, Terraform formatting and validation, Helm lint/render,
workflow lint, and Pylance diagnostics. Azure deployment, Terraform plan/apply,
and a GitHub Actions run have not been verified.

See the [architecture diagram](./architecture.mmd), [tenant setup record](./docs/external-id-tenant-setup.md), and [remaining product and operational gaps](./docs/production-readiness-gap-register.md).
