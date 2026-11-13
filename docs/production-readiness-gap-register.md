# Remaining product and operational gaps

This project includes a tested implementation and a temporary Azure
deployment. Checked items indicate implemented or verified capabilities.

## Deployment

- [x] FastAPI upload/status API, External ID token validation, async FASTQ QC
  worker, retries, and poison queue.
- [x] Local External ID browser demo and Azurite-backed API/worker stack.
- [x] Helm chart, opt-in AKS Terraform, workload identity definitions, CI and
  manual OIDC deployment workflow.
- [x] Azure deployment, Terraform plan/apply, and GitHub Actions CI have been
  exercised. Review costs and quotas before deployment.
- [ ] Public TLS and DNS are configured separately for the temporary hosted
  instance; Helm ingress is disabled by default. Prometheus/Grafana dashboards
  and alert delivery are not included.
- [ ] Terraform state is local unless a private backend is configured.

## Product and data protection

- [ ] Build and test the Flutter client and native PKCE callback handling.
- [ ] Define site/organization membership and authorization; `site_code` is
  currently user-supplied and does not grant access.
- [ ] Add streaming upload limits, quotas/rate limits, durable idempotency, and
  recovery for a Blob write that succeeds before queue submission fails.
- [ ] Decide data retention, deletion, residency, and backup/recovery rules.
- [ ] Add a database if durable user/site/sample records or transactional
  upload/queue state are required.
- [ ] Define and test scientifically reviewed QC metrics and representative
  datasets. The current worker provides basic FASTQ QC only.

## Remaining operational work

1. Verify deployment rollback and repeat Azure checks after changes.
2. Complete user/site authorization, mobile sign-in/upload, public ingress,
   monitoring, alerts, and incident procedures.
3. Add Azure-backed integration coverage, data lifecycle controls, and tested
   backup/recovery.

See the [README](../README.md), [authentication guide](./external-user-auth.md),
and [architecture diagram](../architecture.mmd).
