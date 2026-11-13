# External ID configuration

Reference values for the Pangolin development External ID tenant. These IDs
and endpoints are not credentials. Never store client secrets, tokens, or SAS
URLs in this file.

## Tenant and applications

| Setting | Value |
|---|---|
| Tenant | `Pangolincustomers.onmicrosoft.com` |
| Tenant ID | `09611948-7df4-4927-800d-f707197bab70` |
| API client ID and token audience | `d0000cca-0900-4c3f-92cf-45e320e62112` |
| API delegated scope | `samples.write` |
| Public client ID (native app and local demo) | `927109f8-f2d7-4e2d-94b2-eb26f3d02cba` |
| User flow | `fieldusersignin` (email one-time passcode) |
| Redirect URIs | Native: `com.pangolinapp://oauthredirect`; local SPA: `http://localhost:8081/` (register as Single-page application) |

The API registration's application ID URI is
`api://d0000cca-0900-4c3f-92cf-45e320e62112`; the observed access-token
audience is the bare application ID above.

## OpenID Connect values

Discovery URL:

`https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0/.well-known/openid-configuration?p=fieldusersignin`

| Setting | Value |
|---|---|
| Issuer | `https://09611948-7df4-4927-800d-f707197bab70.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0` |
| JWKS URI | `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/discovery/v2.0/keys` |
| Authorization endpoint | `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/oauth2/v2.0/authorize` |
| Token endpoint | `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/oauth2/v2.0/token` |

## Verification

A real authorization-code-with-PKCE token was previously accepted by the API
validator. Verified claims were `aud` = API client ID, `scp` = `samples.write`,
and `azp` = mobile client ID. The API now enforces that `azp`; no subject value
or token was retained.

The Flutter app and platform callback handling remain to be implemented and
tested. See the [authentication guide](./external-user-auth.md).
