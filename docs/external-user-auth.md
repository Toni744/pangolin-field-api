# External field-user authentication

The upload API uses Microsoft Entra External ID as its customer identity provider. The API accepts a delegated OAuth access token for this API; it never accepts an ID token as API authorization. Flutter is a public client and must not contain a client secret.

## Trust and upload flow

1. The Flutter app signs the field user in with authorization code flow and PKCE through the system browser.
2. The app requests the delegated `samples.write` scope for this API.
3. Flutter sends the access token as `Authorization: Bearer <access-token>` with its multipart sample upload over HTTPS.
4. The API validates the token's RS256 signature against the tenant's OpenID Connect signing keys, as well as issuer, audience, required claims, expiration, and delegated scope.
5. The API uses its own managed identity (or the developer's credential during local testing) to write the file and JSON metadata to the private Blob container.
6. Blob paths are partitioned by a SHA-256 hash of the token subject. The original subject is recorded in metadata for audit attribution.

The API authenticates callers but does not yet implement site/organization membership, ownership-based reads, or a consent flow. Do not expose public API ingress until the External ID tenant and app registrations are fully configured, caller authorization is reviewed, and the token flow is tested end to end.

## External ID tenant and app registrations

A Microsoft Entra External ID **external tenant** has been created for the field-user population, separate from the workforce directory. The API and public mobile client are registered, the API exposes and grants the delegated `samples.write` scope to the client, the `fieldusersignin` sign-up/sign-in flow uses email one-time passcodes and is assigned to the mobile app, and the native redirect URI is registered. A one-off authorization-code-with-PKCE test acquired an API access token and passed it through the API JWT validator. Flutter integration remains incomplete. See [the tenant setup record](./external-id-tenant-setup.md) for non-secret IDs and observed token claims.

In that tenant:

1. The `fieldusersignin` user flow is created with email one-time passcode and email address as its only collected attribute. The `Pangolin Field Mobile` app is assigned to this flow.
2. The REST API registration exposes delegated `samples.write` with application ID URI `api://d0000cca-0900-4c3f-92cf-45e320e62112`; the mobile client has that delegated permission.
3. The Flutter app is registered as a **mobile/public client**. Do not create or ship a client secret. The user selected `com.pangolinapp` for Android and iOS identifiers.
4. The user selected `flutter_appauth`. The Entra app registration now contains `com.pangolinapp://oauthredirect` under the Mobile and desktop applications platform. Configure Android and iOS to dispatch that exact URI to AppAuth; the repository currently has no Flutter app or `pubspec.yaml`, so app-side callback handling remains untested.
5. The OpenID Connect metadata document for `fieldusersignin` and the claims observed in a verified API access token are recorded below. Configure the API audience from the observed `aud` claim, not from an assumed application ID URI or an ID token.

Use the tenant and user-flow-specific OIDC authority and discovery metadata shown by the Entra admin center. Token issuer and audience values must match the access token issued for the API exactly.

The verified discovery document is
`https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0/.well-known/openid-configuration?p=fieldusersignin`.
It reports the following values:

| Metadata value | Verified value |
|---|---|
| `issuer` | `https://09611948-7df4-4927-800d-f707197bab70.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0` |
| `jwks_uri` | `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/discovery/v2.0/keys` |
| `authorization_endpoint` | `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/oauth2/v2.0/authorize` |
| `token_endpoint` | `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/oauth2/v2.0/token` |

The discovery metadata was verified independently. A subsequent one-off
authorization-code-with-PKCE flow requested `api://d0000cca-0900-4c3f-92cf-45e320e62112/samples.write`.
The returned access token passed the project's `app/auth.py` JWT validation.
Only non-secret claim values were retained; no token or subject value was
logged or recorded.

| Access-token check | Observed result |
|---|---|
| API validator | Passed (`validated_by_api_auth: true`) |
| `iss` | `https://09611948-7df4-4927-800d-f707197bab70.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0` |
| `aud` | `d0000cca-0900-4c3f-92cf-45e320e62112` |
| `tid` | `09611948-7df4-4927-800d-f707197bab70` |
| `scp` | `samples.write` |
| `azp` (authorized client) | `927109f8-f2d7-4e2d-94b2-eb26f3d02cba` |
| `appid` | Not present |
| `ver` | `2.0` |
| `sub` | Present; value intentionally not recorded |

The configured API audience must therefore be the bare application ID above,
without the `api://` prefix. The test used a temporary `http://localhost:8400/callback` redirect, which was
removed after testing. The mobile registration now retains only the native
`com.pangolinapp://oauthredirect` redirect URI.

## API configuration

Set these environment variables for local execution. For an Azure Container App, set the corresponding Terraform variables before setting `deploy_api = true`:

| API setting | Value |
|---|---|
| `ENTRA_EXTERNAL_ID_ISSUER` | `https://09611948-7df4-4927-800d-f707197bab70.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0` |
| `ENTRA_EXTERNAL_ID_JWKS_URL` | `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/discovery/v2.0/keys` |
| `ENTRA_API_AUDIENCE` | `d0000cca-0900-4c3f-92cf-45e320e62112` |
| `ENTRA_API_SCOPE` | `samples.write` |

With the API running locally, make a request using an **access token acquired for the API**:

```bash
curl -X POST http://127.0.0.1:8000/samples \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F 'sample_id=2dbf85de-daa5-4e16-bdbe-c8ab11392400' \
  -F 'site_code=boreal-7' \
  -F 'observed_at=2026-10-25T10:30:00-04:00' \
  -F 'file=@reads.fastq;type=application/octet-stream'
```

Missing or invalid auth settings fail closed: health checks remain unauthenticated, while an upload request with a bearer token returns 503 until validation is configured. A request without a token, or with an invalid/expired token, returns 401; a valid token without the required scope returns 403. Signing keys are retrieved from the configured HTTPS JWKS endpoint and cached by PyJWT.

## Flutter client

Use `flutter_appauth` for native authorization code flow with PKCE and External ID's user-flow authority. The registered redirect URI is `com.pangolinapp://oauthredirect`; configure the Android scheme/host and iOS URL scheme to match it exactly. The Flutter app and platform callback configuration are not present in this repository yet.

- Use the system browser, not an embedded web view.
- Request the API's delegated `samples.write` scope and send the returned access token only to this API.
- Never store a client secret in the app. Keep refresh-token storage in platform-protected secure storage if offline sign-in is required.
- Upload using HTTPS and a stable client-generated UUID. On network failure, retry the same sample ID; the API does not overwrite completed objects.
- Do not log access/refresh tokens or sensitive sample metadata.

For large files and unreliable connectivity, a follow-up iteration can introduce an API-authorized, short-lived, per-blob upload grant and direct resumable upload to Blob Storage. Keep the current authenticated API-proxy upload until that grant's permissions, expiry, retry/finalization, and cleanup behavior are designed and tested.

## Microsoft references

- [Microsoft Entra External ID overview](https://learn.microsoft.com/en-us/entra/external-id/customers/overview-customers-ciam)
- [Add a redirect URI to an app registration](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-redirect-uri)
- [flutter_appauth package documentation](https://pub.dev/packages/flutter_appauth)
- [OAuth 2.0 authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Protected web API overview](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-protected-web-api-overview)
- [Create a user-delegation SAS for Blob Storage](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-user-delegation-sas-create-python)
