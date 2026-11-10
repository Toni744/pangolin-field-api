# Production-readiness gap register

This is a living checklist of the work required to turn the current learning
prototype into a production-oriented field-data ingestion service. It records
gaps and decisions, not a claim that the items are already implemented.

## Current baseline

- The FastAPI API accepts a multipart sample upload and writes the file plus a
  JSON metadata blob to Azure Storage.
- `POST /samples` validates a bearer access token's signature, issuer,
  audience, required claims, and configured delegated scope. Its behavior has
  unit-test coverage and passed a one-off External ID access token acquired
  using authorization code with PKCE.
- The current API-proxy upload is the only implemented upload path. The
  External ID tenant, API/mobile registrations, and email-OTP user flow exist,
  but the Flutter app, direct-to-Blob grant, and upload-finalization API do not.
- Terraform describes Storage, a conditional user-assigned managed identity,
  ACR, Container Apps, and Log Analytics. The managed identity and other
  project Azure resources were not deployed; all project resources were
  deleted after the test upload, including its uploaded data.
- The implementation has no durable upload-session database, business-level
  authorization, queue/worker, production deployment pipeline, or operational
  alerting.

## P0 — Make the upload and authorization design production-safe

### External identity and caller authorization

- [x] Create a dedicated Microsoft Entra External ID tenant.
- [x] Register the API and expose the delegated `samples.write` scope.
- [x] Record and verify the tenant ID and primary domain in the setup record.
- [ ] Confirm the selected data-residency region; it is not yet confirmed.
- [x] Configure a sign-up/sign-in user flow using email one-time passcodes,
  collect email address only, and assign the mobile app to the flow.
- [ ] Configure account recovery, consent/privacy text, and support/incident
  procedures.
- [x] Register a native/public mobile client and grant its delegated
  `samples.write` permission; no client secret is configured.
- [ ] Integrate the selected `flutter_appauth` library with authorization code
  + PKCE and system-browser sign-in. No Flutter app or package manifest exists
  in this repository yet.
- [x] Register `com.pangolinapp://oauthredirect` for the native mobile client.
- [ ] Configure Android and iOS to dispatch that exact URI to AppAuth and
  verify the callback in a running Flutter app.
- [ ] Integrate the Flutter app with External ID, including Android/iOS
  secure token storage, token refresh/revocation handling, sign-out, and safe
  authentication error UX.
- [x] Verify actual access-token claims from the chosen External ID flow:
  issuer, audience, tenant, subject presence, scope, token version, and client
  application identifier. Observed values are recorded in
  `docs/external-id-tenant-setup.md`; the API validator accepted the token.
- [x] Remove the temporary localhost test redirect URI from the mobile app
  registration and verify the native redirect is the only remaining URI.
- [ ] Decide whether to allow only the registered mobile app and enforce the
  appropriate client claim in the API. Current validation does not restrict
  callers to a particular client app.
- [ ] Map the stable identity `(issuer, subject)` to an internal user record.
  Avoid treating an unqualified subject string as a globally unique identity.
- [ ] Define authorization beyond sign-in: which users belong to which
  organizations/sites, who can submit to each site, administrative roles,
  account suspension, and how access is revoked. Do not trust a client-supplied
  `site_code` as proof of permission.
- [ ] Define whether the API should accept only delegated user tokens or also
  service-to-service identities, and authorize those as a separate path.
- [ ] Test invalid signature, wrong issuer/audience/client, expired/not-yet-valid
  token, absent subject/scope, key rotation, JWKS outage/recovery, clock skew,
  and revoked/disabled users where the platform supports it.

### Direct-to-Blob upload flow

- [ ] Replace the proxy upload for mobile clients with a two-phase API flow:
  authenticated upload-session creation, direct Blob transfer, then
  authenticated completion/finalization.
- [ ] On session creation, validate sample metadata and the user's site or
  organization access; generate the sample ID and immutable server-controlled
  Blob path. Never accept a client-selected container or arbitrary Blob name.
- [ ] Issue a short-lived **user-delegation SAS** for exactly the intended
  Blob. Use the API's managed identity to obtain the user-delegation key;
  assign only the required Blob data permissions and delegation-key action.
  Confirm the minimum role/scope required for the chosen Azure SDK/API.
- [ ] Restrict the SAS to HTTPS, a single object, only the upload operations
  needed by the selected upload method, and a short validity window. Do not
  grant read, list, delete, or container-wide access. Keep the Storage
  container private and Shared Key access disabled.
- [ ] Treat the SAS URL as a bearer secret: return it only over HTTPS, never
  log it or include it in analytics/crash reports, keep it out of persisted
  app state where possible, and provide a safe refresh path for expired grants.
- [ ] Select an upload protocol based on file size and field connectivity:
  single request for small objects or resumable staged block uploads for large
  objects. Define chunk sizing, retries, timeouts, backoff, checksum/ETag
  handling, and behavior when a SAS expires mid-upload.
- [ ] Implement completion/finalization so the API independently checks the
  expected Blob path, existence, size, ETag, and available integrity data
  before marking the sample complete. A client callback alone is not proof of
  a successful or valid upload.
- [ ] Use durable upload-session state to track owner, site, expected metadata,
  blob path, SAS expiry, upload status, idempotency key, and completion result.
  Make create/finalize/retry behavior safe under duplicate and concurrent
  requests.
- [ ] Clean up abandoned sessions and orphaned or partial blobs. Define a
  lifecycle/retention policy for incomplete uploads and finalized data.
- [ ] Decide how external mobile devices reach Blob Storage. A private endpoint
  is not directly reachable from ordinary mobile networks; public Blob
  endpoints require carefully scoped SAS access and appropriate storage
  network controls. Document this trade-off before enabling direct upload.
- [ ] If a browser-based client is added, configure narrowly scoped Blob CORS
  rules for its exact origins, methods, and headers. Native mobile clients do
  not use browser CORS enforcement.

### Data integrity, privacy, and abuse controls

- [ ] Enforce limits before issuing upload grants: authorized user, per-file
  maximum, per-user/site quotas, allowed metadata, and rate limits.
- [ ] Validate file signatures/content where applicable; do not trust filename
  extensions or client-provided MIME types. Decide whether bioinformatics
  formats require structural validation or malware scanning.
- [ ] Define whether client-provided checksums are required and which digest
  algorithms are accepted. Verify integrity server-side before processing.
- [ ] Decide whether metadata should be stored in Blob JSON, a database, or
  both; define the authoritative source and consistency/reconciliation model.
- [ ] Classify sample, location, and account data; document purpose, lawful
  basis/consent where required, retention, deletion requests, data residency,
  and access/export processes.
- [ ] Define encryption requirements. Azure Storage provides encryption at
  rest; determine whether platform-managed keys meet the data policy or
  customer-managed keys, key rotation, and recovery are required.
- [ ] Design audit events for sign-in, authorization decisions, upload-session
  creation, grant issuance, completion, rejection, and deletion. Keep
  credentials, bearer tokens, SAS query strings, and sensitive biological or
  location data out of logs.

## P1 — Build the production service foundation

### Azure resources and identities

- [ ] Recreate infrastructure only after reviewing a costed Terraform plan.
  All resources were deleted; nothing in Azure is currently hosting this
  project.
- [ ] Deploy the user-assigned managed identity and attach it only to the API
  workload. Use Microsoft Entra authentication for Storage; do not add storage
  account keys or connection strings.
- [ ] Scope Blob data access to the smallest practical resource. Add only the
  additional user-delegation-key permission needed for SAS issuance; review
  whether built-in roles are too broad and whether a custom role is justified.
- [ ] Use managed identity for ACR image pulls; keep ACR admin credentials
  disabled and anonymous pull disabled.
- [ ] Decide Storage network exposure and Container Apps ingress together.
  Keep the API private until authentication, authorization, TLS, abuse
  controls, and monitoring are verified. Public mobile access requires a
  deliberate secure ingress design.
- [ ] Add consistent ownership, environment, service, and cost-allocation tags.
- [ ] Decide if the prototype's scale-to-zero and single-replica settings meet
  availability and cold-start requirements. Define availability targets before
  paying for higher minimum capacity.

### Durable state and background processing

- [ ] Select a durable datastore for upload sessions, user/site membership,
  sample records, idempotency, and audit references. Define unique keys,
  transactions, retention, backup, and restore behavior.
- [ ] Add an asynchronous queue and worker for post-upload validation and
  bioinformatics processing. The upload API should acknowledge validated
  intake rather than synchronously run long jobs.
- [ ] Make workers idempotent and safe to retry; use poison/dead-letter
  handling, bounded concurrency, resource limits, and status reporting.
- [ ] Evaluate Container Apps Jobs versus AKS for workload scheduling,
  reproducibility, GPU needs, and operational burden. Do not introduce AKS/GPU
  resources until a measured workload requires them.

### Reliability, networking, and recovery

- [ ] Set service objectives (availability, latency, upload completion rate),
  API timeouts, retry budgets, throttling, and dependency-failure behavior.
- [ ] Define recovery objectives (RPO/RTO) and implement tested backup/restore
  for metadata and required Blob data. Versioning, soft delete, replication,
  and backups can add cost; select them according to data criticality.
- [ ] Define cleanup and deletion behavior across database records, original
  blobs, versions, queue messages, and backups.
- [ ] Add health/readiness checks that distinguish process liveness from
  dependency readiness without exposing sensitive diagnostics.
- [ ] Review TLS, DNS, ingress, egress, storage firewall/private networking,
  and any required private connectivity as one end-to-end design.

## P1 — Delivery, security operations, and governance

- [ ] Store Terraform state in a private remote backend with encryption,
  versioning, locking, restricted RBAC, and recovery procedures. Current
  Terraform state is local; protect it and never commit state or `tfvars`.
- [ ] Separate development, test/staging, and production subscriptions or
  resource boundaries, identities, data, and configuration.
- [ ] Configure GitHub Actions-to-Azure workload identity federation (OIDC)
  with environment protections and least privilege. Do not use long-lived
  service-principal secrets.
- [ ] Add deployment stages: formatting/validation, unit and integration
  tests, dependency and container vulnerability scanning, secret scanning,
  Terraform plan review, protected approval, deployment, and post-deploy
  smoke test/rollback.
- [ ] Pin GitHub Actions to immutable commit SHAs where required by policy;
  keep CI permissions minimal and prevent untrusted pull requests from gaining
  deployment credentials.
- [ ] Define image provenance, SBOM, vulnerability remediation, base-image
  update policy, and immutable image references/digests for production.
- [ ] Create a threat model covering stolen tokens/SAS, malicious users,
  cross-site data access, oversized uploads, replay, compromised mobile
  devices, compromised dependencies, and Azure control-plane access.
- [ ] Establish security incident response, access reviews, account recovery,
  vulnerability response, audit retention, and any SOC 2 / ISO 27001 evidence
  requirements before claiming compliance.

## P1 — Observability and cost management

- [ ] Add structured application logs, traces, and metrics with correlation
  IDs across API, storage, queue, and workers. Redact secrets and personal or
  sensitive sample data.
- [ ] Build dashboards for request/error rates, latency, authorization
  failures, upload starts/completions/abandonment, bytes, storage throttles,
  queue depth, worker failures, and dependency health.
- [ ] Configure actionable alerts and an on-call/incident process; test alert
  delivery and operational runbooks.
- [ ] Configure budgets and cost alerts before deployment. Review Storage
  capacity/transactions/egress, Container Registry, Container Apps compute,
  Log Analytics ingestion/retention, database, and queue costs.
- [ ] Set log retention and daily ingestion limits; verify alerts for quota
  exhaustion and avoid silently dropping security/audit events.
- [ ] Add lifecycle rules for incomplete uploads and retained data, subject to
  approved retention and recovery requirements.

## P2 — Client and product readiness

- [ ] Implement the Flutter application and field workflow, including offline
  queueing, resumable transfer, progress display, cancellation, retry, and
  explicit pending/complete/failed states.
- [ ] Ensure queued work survives app restarts without persisting SAS URLs or
  tokens longer than necessary. Re-authorize before obtaining refreshed upload
  grants.
- [ ] Add localization/accessibility, device support policy, app signing and
  release controls, privacy disclosures, and a support path for field users.
- [ ] Define sample-ID ownership, duplicate policy, corrections, resubmission,
  and whether users can view or delete their own uploads.
- [ ] Add end-to-end tests across real test users, token acquisition, API
  authorization, SAS issuance, direct upload, finalization, failure/retry,
  and cleanup. Keep synthetic data in non-production environments.

## Suggested delivery order

1. Make and document the external-user authorization model, tenant/app setup,
   site membership rules, and data-residency decision.
2. Deploy a low-cost development foundation with managed identity, private
   Blob container, secure state, and cost alerts.
3. Implement upload-session creation, narrowly scoped user-delegation SAS,
   resumable direct upload, server-side finalization, and orphan cleanup.
4. Build the Flutter PKCE client and test complete upload/retry flows with
   synthetic data and real test users.
5. Add durable metadata/session state, asynchronous processing, monitoring,
   backups, recovery tests, and CI/CD protections.
6. Conduct threat-model/security review, verify authorization boundaries and
   operational runbooks, then decide whether and how to enable public ingress.
7. Reassess AKS/GPU only when representative job measurements show that
   Container Apps Jobs or another simpler execution model is insufficient.

## Related project documents

- [External field-user authentication](./external-user-auth.md)
- [Architecture diagram](../architecture.mmd)
- [Project setup and current status](../README.md)
