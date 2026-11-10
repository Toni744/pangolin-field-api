# External ID tenant setup record

This file records non-secret identifiers for the External ID development
tenant and API registration. Never add client secrets, access tokens, refresh
tokens, or SAS URLs here.

## Tenant

- Tenant display name: `Pangolin_bio-app customers`
- Primary domain: `Pangolincustomers.onmicrosoft.com`
- Directory (tenant) ID: `09611948-7df4-4927-800d-f707197bab70`
- Workforce tenant ID (different directory): `9b71f7ba-a682-4e9c-85fc-4f20c658777e`

## API app registration

- Display name: `Pangolin Field Data API`
- Application (client) ID: `d0000cca-0900-4c3f-92cf-45e320e62112`
- Application object ID: `f7e2c20a-033e-46d0-83f5-32d003d4302c`
- Enterprise application (service principal) object ID:
  `2caa99cc-267e-47f6-8b64-050afa392961`
- Application ID URI: `api://d0000cca-0900-4c3f-92cf-45e320e62112`
- Verified API access-token audience (`aud`):
  `d0000cca-0900-4c3f-92cf-45e320e62112`
- Requested access-token version: `2`
- Enabled delegated scope: `samples.write`
- Scope ID: `572bb510-96b5-4f88-8f0e-36bdd4a328c5`

## Mobile app registration

- Display name: `Pangolin Field Mobile`
- Application (client) ID: `927109f8-f2d7-4e2d-94b2-eb26f3d02cba`
- Application object ID: `99ea002d-42d8-409f-bfd3-22c4185fb9c5`
- Public/native client; no client secret is used.
- Delegated API permission: `samples.write`
- Android application ID and iOS bundle ID selected by the user:
  `com.pangolinapp`
- Registered Mobile and desktop applications redirect URI:
  `com.pangolinapp://oauthredirect`
- Flutter OAuth library selected: `flutter_appauth`

## Sign-up/sign-in user flow

- User-flow name: `fieldusersignin`
- Flow type: sign up and sign in
- Sign-in method: email one-time passcode
- Collected user attribute: email address only
- Associated application: `Pangolin Field Mobile`

## OpenID Connect discovery

The discovery document for this tenant and user flow was retrieved
successfully. These are non-secret protocol endpoints:

- Discovery URL:
  `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0/.well-known/openid-configuration?p=fieldusersignin`
- Issuer:
  `https://09611948-7df4-4927-800d-f707197bab70.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0`
- JWKS URI:
  `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/discovery/v2.0/keys`
- Authorization endpoint:
  `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/oauth2/v2.0/authorize`
- Token endpoint:
  `https://pangolincustomers.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/oauth2/v2.0/token`

The API registration's application ID URI is not the literal audience observed
in the API access token. A one-off authorization-code-with-PKCE flow requested
the API's delegated scope and produced a token that passed the project's
`app/auth.py` validator. The observed `aud` is the bare API application ID,
`d0000cca-0900-4c3f-92cf-45e320e62112`.

## One-off access-token verification

The token was acquired through `fieldusersignin` using authorization code with
PKCE and the API's `samples.write` delegated scope. The token passed signature,
issuer, audience, required-claim, lifetime, and scope validation in the API.
Only these non-secret results were retained; the access token and subject value
were not logged or recorded.

| Check/claim | Verified result |
|---|---|
| API validator | Passed |
| `iss` | `https://09611948-7df4-4927-800d-f707197bab70.ciamlogin.com/09611948-7df4-4927-800d-f707197bab70/v2.0` |
| `aud` | `d0000cca-0900-4c3f-92cf-45e320e62112` |
| `tid` | `09611948-7df4-4927-800d-f707197bab70` |
| `scp` | `samples.write` |
| `azp` | `927109f8-f2d7-4e2d-94b2-eb26f3d02cba` |
| `appid` | Not present |
| `ver` | `2.0` |
| `sub` | Present; value intentionally not recorded |

The temporary `http://localhost:8400/callback` redirect was used for this
one-off test and has been removed. The mobile app registration was read back
after cleanup and now retains only `com.pangolinapp://oauthredirect`.

## Still to configure

- [ ] Implement the Flutter app with `flutter_appauth` and configure Android
  and iOS to handle `com.pangolinapp://oauthredirect`. This workspace has no
  Flutter app or `pubspec.yaml` yet, so the app-side callback handling cannot
  be tested here.
- [ ] Decide whether the API must enforce the registered Flutter client ID in
  addition to validating the signature, issuer, audience, subject, and scope.

## Setup trail

The directory was verified using the signed-in Microsoft Graph context before
the app registrations were created. API registration and scope were read back
from Microsoft Graph. The email-OTP user flow and mobile app assignment were
verified in the Entra admin center. The redirect URI was added through the
app's Mobile and desktop applications platform; the one-slash form
`com.pangolinapp:/oauthredirect` was rejected by the portal validator, while
`com.pangolinapp://oauthredirect` was accepted and read back successfully.
The user selected `flutter_appauth`; app-side handling still needs to be
implemented and tested.
