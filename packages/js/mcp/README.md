# anosys-sdk-mcp

Connect <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Anosys-AI/anosys-sdk/main/assets/logos/claude-dark.svg"><img src="https://raw.githubusercontent.com/Anosys-AI/anosys-sdk/main/assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> Claude Code, <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Anosys-AI/anosys-sdk/main/assets/logos/openai-dark.svg"><img src="https://raw.githubusercontent.com/Anosys-AI/anosys-sdk/main/assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> Codex, <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Anosys-AI/anosys-sdk/main/assets/logos/google-dark.svg"><img src="https://raw.githubusercontent.com/Anosys-AI/anosys-sdk/main/assets/logos/google-light.svg" width="16" height="16" alt=""></picture> Antigravity and <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Anosys-AI/anosys-sdk/main/assets/logos/cursor-dark.svg"><img src="https://raw.githubusercontent.com/Anosys-AI/anosys-sdk/main/assets/logos/cursor-light.svg" width="16" height="16" alt=""></picture> Cursor to the Anosys.ai MCP server (`https://console.anosys.ai/mcp`) and install the `anosys-platform-intelligence` skill.

Your coding agent can then read your Anosys.ai workspace: the architecture of your pipelines, tables and evals, active problems and regressions, eval results, trace trees, and read-only SQL over your telemetry. Every tool is read-only.

## 1. Create an MCP key

1. Sign in to the [Console](https://console.anosys.ai).
2. Open **My Profile → MCP Keys** and create a key. MCP keys start with `ak_mcp_`.

The ingestion key you use for the SDKs and hooks (`ANOSYS_API_KEY`, a UUID) does not work here; the server rejects it with `INGESTION_KEY_NOT_SUPPORTED`.

## 2. Install

Put the key in your environment, then register the server and the skill for every tool you use:

```bash
export ANOSYS_MCP_API_KEY=ak_mcp_...
npx -y anosys-sdk-mcp install --target all -y
npx -y anosys-sdk-mcp status --target all
```

To keep the key out of your shell history, read it without echo instead of typing it in the `export` line:

```bash
(trap 'stty echo' EXIT INT TERM; stty -echo; printf "Anosys.ai MCP key: "; IFS= read -r ANOSYS_MCP_API_KEY; stty echo; echo; export ANOSYS_MCP_API_KEY; npx -y anosys-sdk-mcp install --target all -y)
```

Other ways to run it:

```bash
# One tool: claude-code, codex, antigravity or cursor (comma-separated lists work)
npx -y anosys-sdk-mcp install --target claude-code -y

# Only the skill, no key needed
npx -y anosys-sdk-mcp install --target all --skill-only -y

# Together with a coding-assistant hook
npx -y anosys-sdk-claude-code install --api-key YOUR_INGESTION_KEY --with-mcp -y
anosys-codex install --api-key YOUR_INGESTION_KEY --with-mcp --auto-update --yes
anosys-antigravity install --api-key YOUR_INGESTION_KEY --with-mcp --yes

# From a hook CLI you already have (JavaScript or Python)
anosys-claude-code mcp install -y
anosys-codex mcp install -y
anosys-antigravity mcp install -y

# Remove it
npx -y anosys-sdk-mcp uninstall --target all
```

The key is read from `--mcp-key`, then `ANOSYS_MCP_API_KEY` (or `ANOSYS_MCP_KEY`). Without either, the installer asks for it without echoing it.

Restart the coding tool after installing.

## 3. Where it writes

Every install keeps your other MCP servers and settings, makes a backup (`<file>.<time>.bak`, readable only by you) before it changes a file, and writes atomically.

| Tool (`--target`) | User config (default) | Project config (`--workspace`) | Skill (user / project) |
| --- | --- | --- | --- |
| `claude-code` | `~/.claude.json` | `.mcp.json` | `~/.claude/skills/…` / `.claude/skills/…` |
| `codex` | `$CODEX_HOME/config.toml` (`~/.codex/config.toml`) | `.codex/config.toml` | `$CODEX_HOME/skills/…` / `.agents/skills/…` |
| `antigravity` | `~/.gemini/config/mcp_config.json` | user config (see below) | `~/.gemini/config/skills/…` / `.agents/skills/…` |
| `cursor` | `~/.cursor/mcp.json` | `.cursor/mcp.json` | `~/.cursor/skills/…` / `.cursor/skills/…` |

The skill file is `anosys-platform-intelligence/SKILL.md` in each skills folder.

**The key never goes into a project file.** Project config is often committed, so with `--workspace` the installer writes a reference to `ANOSYS_MCP_API_KEY` instead of the key: `${ANOSYS_MCP_API_KEY}` for Claude Code, `${env:ANOSYS_MCP_API_KEY}` for Cursor, and `bearer_token_env_var = "ANOSYS_MCP_API_KEY"` for Codex. Export the variable in the shell that starts the tool. Antigravity cannot read a key from the environment, so its MCP server always goes in your user config; only the skill goes in the project.

The user configs hold the key itself, in files readable only by you.

<details>
<summary>Manual configuration</summary>

Claude Code (`~/.claude.json`, or `.mcp.json` with the variable reference):

```json
{
  "mcpServers": {
    "anosys-intelligence": {
      "type": "http",
      "url": "https://console.anosys.ai/mcp",
      "headers": { "Authorization": "Bearer ${ANOSYS_MCP_API_KEY}" }
    }
  }
}
```

Codex (`~/.codex/config.toml` or `.codex/config.toml`):

```toml
[mcp_servers.anosys-intelligence]
url = "https://console.anosys.ai/mcp"
bearer_token_env_var = "ANOSYS_MCP_API_KEY"
```

Antigravity (`~/.gemini/config/mcp_config.json`):

```json
{
  "mcpServers": {
    "anosys-intelligence": {
      "serverUrl": "https://console.anosys.ai/mcp",
      "headers": { "Authorization": "Bearer ak_mcp_YOUR_KEY" }
    }
  }
}
```

Cursor (`~/.cursor/mcp.json` or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "anosys-intelligence": {
      "url": "https://console.anosys.ai/mcp",
      "headers": { "Authorization": "Bearer ${env:ANOSYS_MCP_API_KEY}" }
    }
  }
}
```

</details>

## 4. Ask your agent to set it up

Export `ANOSYS_MCP_API_KEY` in your terminal first, so the key never appears in the chat, then paste:

```text
Set up the Anosys.ai MCP server and the anosys-platform-intelligence skill for my coding
tools. ANOSYS_MCP_API_KEY is already exported; do not print it. Run
npx -y anosys-sdk-mcp install --target all -y, then npx -y anosys-sdk-mcp status --target all,
and tell me which config and skill files were written.
```

## 5. Tools

| Area | Tools |
| --- | --- |
| Context and architecture | `export_context_pack`, `get_architecture`, `get_linked_parts` |
| Health, insights and evals | `list_problems`, `get_insights`, `get_eval_summary` |
| Schemas, traces and SQL | `list_tables_and_schemas`, `get_cardinalities`, `get_trace_graph`, `query_readonly`, `resolve_ip` |
| Playbooks and diagnostics | `load_skill` (and `anosys://playbooks/*` resources), `get_auth_and_health` |

`query_readonly` accepts a single `SELECT` or `WITH` statement over your own tables, with a time filter and a scan budget.

## 6. Options

| Option | Description |
| --- | --- |
| `--mcp-key <ak_mcp_...>` | MCP key (default: `ANOSYS_MCP_API_KEY` or `ANOSYS_MCP_KEY`) |
| `--mcp-url <url>` | MCP endpoint (default `https://console.anosys.ai/mcp`) |
| `--target <tool>` | `claude-code`, `codex`, `antigravity`, `cursor` or `all`; comma-separated lists work (default `claude-code`) |
| `--workspace` | Write project config; the key is referenced through `ANOSYS_MCP_API_KEY`, not stored |
| `--skill-only` | Install only the skill (no key needed) |
| `--no-skill` | Register the server without the skill |
| `-y`, `--yes` | Do not prompt |

Requires Node.js 18 or later. License: Apache-2.0.
