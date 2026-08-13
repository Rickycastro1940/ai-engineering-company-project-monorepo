# MCP Playground — public URL evidence

## Requirement

Exercise MCP Playground using a **public** forwarded HTTPS URL
(Codespaces public port forward or equivalent Cloudflare tunnel) —
**not** `localhost` / `127.0.0.1`.

## URL used

```text
https://metres-grams-heroes-mistress.trycloudflare.com/mcp
```

- Host: `metres-grams-heroes-mistress.trycloudflare.com` (Cloudflare quick tunnel)
- Path: `/mcp` (Streamable HTTP)
- Environment: Cursor cloud agent (public forward equivalent to Codespaces
  public port visibility)
- Auth: `Authorization: Bearer <JWT>` from local OIDC issuer

## Proof (screenshots in this folder)

| Screenshot | Observation |
| ---------- | ----------- |
| `playground-public-url.png` | Connect field contains the public `trycloudflare.com` URL; Local Test Server card shows `localhost` but was not selected |
| `playground-public-connected.png` | Brasaland Company Tools connected (Streamable HTTP, 2 tools, Bearer auth) |
| `playground-server-details.png` | Same public URL + connected status |

## Flows exercised over that public connection

See JSON dumps in this folder (`create_ticket.json`, `get_status.json`,
`update_ticket.json`, `inventory_list.json`, `inventory_update_forbidden.json`).
