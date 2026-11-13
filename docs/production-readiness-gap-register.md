# Remaining product and operational gaps

This project is a tested portfolio implementation, not a deployed or
production-ready service. Checked items describe code/configuration only, not
live Azure verification.

## Deployment

- [x] FastAPI upload/status API, External ID token validation, async FASTQ QC
  worker, retries, and poison queue.
- [x] Local External ID browser demo and Azurite-backed API/worker stack.
- [x] Helm chart, opt-in AKS Terraform, workload identity definitions, CI and
  manual OIDC deployment workflow.
- [ ] Azure deployment, Terraform plan/apply, and GitHub workflow execution
  remain unverified. Review costs and quotas before deployment.
- [ ] Public TLS ingress, DNS, Prometheus/Grafana dashboards, and alert delivery
  are not included. Helm ingress is disabled by default.
- [ ] Terraform state is local unless a private backend is configured.

## Product and data protection

- [ ] Build and test the Flutter client and native PKCE callback handling; the
  local browser demo is not a deployed production portal.
- [ ] Define site/organization membership and authorization; `site_code` is
  currently user-supplied and does not grant access.
- [ ] Add streaming upload limits, quotas/rate limits, durable idempotency, and
  recovery for a Blob write that succeeds before queue submission fails.
- [ ] Decide data retention, deletion, residency, and backup/recovery rules.
- [ ] Add a database if durable user/site/sample records or transactional
  upload/queue state are required.
- [ ] Define and test scientifically reviewed QC metrics and representative
  datasets. The current worker provides basic FASTQ QC only.
- [ ] The optional GPU Job is a hook; no GPU application or image is provided.

## Before claiming production readiness

1. Validate the Azure plan, deploy a low-cost test environment, and verify
   workload identity, Storage access, queue processing, and rollback.
2. Complete user/site authorization, mobile sign-in/upload, public ingress,
   monitoring, alerts, and incident procedures.
3. Add Azure-backed integration coverage, data lifecycle controls, and tested
   backup/recovery.
4. Add a real GPU workload only if measured requirements justify its cost and
   operational complexity.

See the [README](../README.md), [authentication guide](./external-user-auth.md),
and [architecture diagram](../architecture.mmd).
