# Specification 003: multi-KB registry and optional API token

**Status:** agreed with the repository owner. Implementation runs through the standard pipeline.
**Result of the block:** one deployment serves multiple client knowledge bases: a request selects the base by a client identifier, every registered base is validated before entering rotation, and an optional shared token protects the API when it is exposed beyond localhost.

## 1. Purpose

Turn the single-knowledge-base prototype into a deployment that can serve several clients: each client has its own catalogue and reply rules, adding a client is one file plus one registry line with no restart, and the API can be protected by a shared token when the deployment is exposed to the network.

## 2. Multi-KB registry

R1. The registry is a JSON file mapping client identifiers to knowledge-base file paths, with a mandatory `default` entry pointing at the bundled example catalogue.
R2. The registry is read per request: adding or changing a client requires no service restart.
R3. A request picks the base by the `X-Client-Id` request header. An absent or unknown identifier resolves to the default base; an unknown client is not an error.
R4. Every knowledge base referenced by the registry is validated with the existing knowledge-base loader before it can serve; a base that fails validation is refused at load with a named error, never served.
R5. Knowledge-base paths must resolve inside the configured knowledge-base directory; path traversal is rejected.
R6. The production registry file lives outside the repository; the repository ships only a fixture for tests.

## 3. Optional API token

R7. When `REPLY_ASSISTANT_API_TOKEN` is set, `/api/suggest` and `/webhooks/crm/messages` require the `X-API-Token` request header with the matching value; a missing or wrong token is a 401 in the standard error envelope.
R8. When the token is unset, no check happens (local development and the bundled demo page).
R9. The comparison uses a constant-time comparison.
R10. Rate limiting of the suggest endpoint is a deployment-level concern (reverse proxy) and is documented, not implemented in the application.

## 4. Errors

R11. All new failure paths use the existing JSON error envelope with a code and message; no stack traces and no internal paths are exposed.

## 5. Acceptance

1. A registry with a valid default base and two clients serves three distinct bases selected by the header.
2. An invalid knowledge base referenced by the registry is refused at load; the service does not start.
3. An absent client header and an unknown client id both resolve to the default base.
4. With the token set, requests without or with a wrong token get 401; with the right token they pass.
5. With the token unset, the same requests pass without any header.
6. All existing behaviour (specifications 001 and 002) is unchanged.

## Demo language selection

The demo page sends X-Catalogue-Language with en or ru for new suggestion requests. REPLY_ASSISTANT_DEMO_CATALOGUES optionally maps both languages to registered client identifiers. Configured aliases are validated at startup and selected strictly per request; a missing alias or mismatched catalogue language is refused without a model call. The language header cannot be combined with X-Client-Id. Without the language header, existing default/client selection and webhook behaviour are unchanged. A pending request retains its submitted language; switching the interface sends no extra request and does not translate prior results.
