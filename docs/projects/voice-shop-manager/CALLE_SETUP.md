# CALL-E setup (demo vs live)

## Demo path (Awwal — complete without auth)

The hackathon demo **does not require** CALL-E authentication. Run:

```bash
cd apps/python/shop-voice-manager
python client.py --request example_request.json --weekly-summary
```

No API key, no MCP, no credits.

## Live path (optional)

Use when recording a real call clip or testing before production.

### 1. Account

- Sign up: https://www.heycall-e.com/
- API key: https://dashboard.heycall-e.com/account/api-keys

### 2. Cursor MCP

In `call-e-integrations` (local only, not committed):

```json
{
  "mcpServers": {
    "calle": {
      "url": "https://seleven-mcp-sg.airudder.com/mcp/openagent_oauth"
    }
  }
}
```

Reload Cursor → authorize `calle` → verify `plan_call`, `run_call`, `get_call_run`.

### 3. CLI

```powershell
npx -y @call-e/cli auth login
npx -y @call-e/cli auth status
```

### 4. Regions for this project

| Market | region | locale |
| --- | --- | --- |
| Nigeria | NG | en |
| India | IN | en or hi |

Pidgin phrasing goes in the **task text**, not the API locale field.

## Status

| Item | Demo submission | Live optional |
| --- | --- | --- |
| CALL-E account | Not required | Recommended for one call clip |
| MCP auth | Not required | For agent-driven testing |
| API key in app | Not required | Rajput R5 when SDK wired |

**Task A1:** Marked **Done (demo)** — demo path documented; live auth optional.
