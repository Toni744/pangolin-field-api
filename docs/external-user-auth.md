# External ID authentication

The API accepts delegated Microsoft Entra External ID **access tokens** for
the Pangolin API. It does not accept ID tokens for API authorization.

## Token validation

The API verifies the RS256 signature, issuer, audience, required claims,
expiration, `samples.write` scope, and `azp` against the registered public
client. Configure:

| Environment variable | Purpose |
|---|---|
| `ENTRA_EXTERNAL_ID_ISSUER` | Exact token issuer |
| `ENTRA_EXTERNAL_ID_JWKS_URL` | HTTPS signing-key endpoint |
| `ENTRA_API_AUDIENCE` | API audience (`aud`) |
| `ENTRA_API_SCOPE` | Required delegated scope |
| `ENTRA_ALLOWED_CLIENT_ID` | Allowed client (`azp`) |

Use the verified values in the [tenant setup record](./external-id-tenant-setup.md).
Missing auth configuration fails closed. Requests without a valid token receive
401; a token with insufficient scope or a missing/mismatched `azp` receives
403. Health checks do not require authentication.

## Browser application

The local browser app is a same-origin application using MSAL Browser, authorization
code with PKCE, and the existing public client registration. It requests the
delegated `api://<API-client-ID>/samples.write` scope and sends only the
resulting access token to the API. No client secret is used or exposed.

Register `http://localhost:8081/` under the client's **Single-page
application** redirect URIs, retain the native redirect URI, and ensure the
client is assigned to `fieldusersignin` with the API's `samples.write`
permission. Start the local stack with `docker compose up --build -d`; the page
is at `http://localhost:8081/`. The browser UI is disabled unless
`PANGOLIN_WEB_UI_ENABLED=true`.

## Mobile sign-in

The registered client is a public/native app; never add a client secret. The
selected library is `flutter_appauth`, with authorization code + PKCE through
the system browser and redirect URI `com.pangolinapp://oauthredirect`.

The Flutter app and Android/iOS callback handling do not exist in this
repository yet. When implemented, use secure platform storage for tokens, send
the access token only to the API over HTTPS, and never log tokens or sensitive
sample data.

## Authorization and data handling

Blob paths use a hash of the token subject. The status endpoint is scoped to
that submitter. Site/organization membership and authorization are not
implemented; a client-supplied `site_code` is not proof of access. Do not expose
the API publicly until authorization and TLS ingress are in place.

Uploads currently pass through the API. Direct-to-Blob upload grants,
resumable transfer, and server-side upload finalization are not implemented.
