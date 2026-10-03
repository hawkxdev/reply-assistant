# Specification 003: public deploy with multi-KB registry

**Status:** agreed with the owner (bearer token, key on VPS, SSH-only registry). Implementation runs through the standard pipeline.
**Result of the block:** the prototype is reachable at `https://reply.hawkxdev.dev` from a browser, serves multiple client knowledge bases from one deployment, and the model key lives only on the VPS in a root-only env file.

## 1. Purpose

Turn the local prototype into a demonstration a potential client can open by link, and a skeleton a real client can be onboarded onto by adding one knowledge-base file. No new AI behaviour: the generation, checks and reply flow of specification 001 are unchanged.

## 2. Decisions agreed with the owner

1. **Bearer token** on the API: when `REPLY_ASSISTANT_API_TOKEN` is set in settings, `/api/suggest` and `/webhooks/crm/messages` require the `X-API-Token` header with the matching value; unset means no check (local development). The token is one shared secret the owner gives out with the demo link; rotation is one env change and restart.
2. **The model key lives on the VPS** in `/opt/reply-assistant/.env` (root-only), transferred by the owner by hand during deployment; the value never appears in chat, logs or the repository.
3. **Knowledge bases are added only by the owner over SSH**: a KB file into `/opt/reply-assistant/kb/<client_id>.yaml` plus a line in the registry. No public upload API — loading foreign YAML is not an attack surface.
4. **nginx rate limit** on the suggest endpoint as a second layer against token burn.

## 3. Multi-KB registry

- Registry file `/opt/reply-assistant/registry.json`: `{"default": "kb/example-en.yaml", "<client_id>": "kb/<client_id>.yaml", ...}`. The `default` base is the bundled English example so the demo link works in a browser without headers.
- `POST /api/suggest` reads the optional `X-Client-Id` header; unknown or absent client resolves to the default base. Unknown client is not an error (demo friendly); a wrong base breaks nothing.
- A KB file is accepted into the registry only after `load_knowledge_base` validates it (the existing R1-R4 checks); a broken file never enters rotation.
- Hot reload: the registry and KB files are re-read per request — adding a client is a file plus a registry line, no restart.
- In the repository: only the code and tests with a fixture registry; the production registry file never enters git.

## 4. Deployment (VPS hawkxdev)

- Per-app isolation per the infra skill: system user `reply-assistant`, `/opt/reply-assistant/`, uv service bound to `127.0.0.1:<free port>` (check `ss -tlnp` before bind), systemd unit with `Restart=on-failure`.
- nginx: `sites-available/reply-assistant.conf` + symlink; LE certificate for `reply.hawkxdev.dev` via the existing certbot; `limit_req` on the suggest path.
- UFW: no new public ports (nginx already serves 80/443).
- Inventory: update `references/projects.md` and `references/network.md` of the infra skill after deployment.

## 5. Out of scope

User accounts and per-client tokens, billing, conversation storage, CRM write-back, the holdout evaluator run (that is stage 4 of block 002), Docker (uv + systemd is enough for one app; revisit on demand).

## 6. Acceptance

1. `https://reply.hawkxdev.dev` serves the demo page over TLS.
2. The page answers a demo question end to end (model reply visible).
3. Without the token the API answers the page; with a wrong token the API returns 401 in the error envelope.
4. An unknown `X-Client-Id` falls back to the default base; a registered client id picks its own base.
5. A KB file that fails validation is refused at registry load.
6. The service survives restart (`systemctl restart reply-assistant`).
7. The VPS inventory of the infra skill is updated.
