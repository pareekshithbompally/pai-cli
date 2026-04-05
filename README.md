<p align="center">
  <h1 align="center">pai-cli</h1>
  <p align="center">Terminal-first observability CLI for AI coding workflows — inspect sessions, messages, plans, billing, cache, and diagnostics across Claude, Codex, Copilot, Gemini, and Vibe.</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/pipx-2C7BE5?logo=python&logoColor=white" alt="pipx" />
  <img src="https://img.shields.io/badge/Claude-D97757?logo=anthropic&logoColor=white" alt="Claude" />
  <img src="https://img.shields.io/badge/OpenAI-412991?logo=openai&logoColor=white" alt="OpenAI" />
  <img src="https://img.shields.io/badge/GitHub_Copilot-181717?logo=github&logoColor=white" alt="GitHub Copilot" />
  <img src="https://img.shields.io/badge/Google_Gemini-8E75B2?logo=googlegemini&logoColor=white" alt="Google Gemini" />
</p>

---

## What it does

- Inspect session history across Claude, Codex, Copilot, Gemini, and Vibe
- Read saved prompts/messages and plans
- Report API billing for OpenAI, Anthropic, and Google
- Manage local cache state
- Run `doctor` diagnostics for storage, agents, and billing environment readiness

## Installation

### Recommended

Install directly from GitHub with the packaged installer:

```bash
curl -fsSL https://raw.githubusercontent.com/pareekshithbompally/pai-cli/main/install.sh | bash
```

The installer:

1. Checks for Python 3.10+
2. Verifies `pipx` is available
3. Installs `pai-cli` into a pipx-managed virtual environment
4. Injects Google billing dependencies into the same environment
5. Leaves you with a native `pai` command on your PATH

### Local development

```bash
pipx install .
pipx inject pai-cli google-cloud-bigquery db-dtypes
```

## Command surface

| Area | Purpose |
|---|---|
| `pai sessions` | Inspect session history, messages, plans, and summary stats |
| `pai billing` | Pricing and billing reports across providers |
| `pai cache` | Inspect and clear local cached session metadata |
| `pai identity` | Manage identity aliases and clear telemetry-derived identity state |
| `pai setup` | Guided setup for optional identity telemetry capture |
| `pai doctor` | Diagnose runtime, storage, agents, and billing env setup |

## Examples

```bash
pai sessions history --agent claude
pai sessions stats --agent all
pai sessions messages ~/.copilot/session-state/<session>/events.jsonl
pai sessions plans --agent copilot

pai setup identity
pai identity alias set --agent claude tech@tatvacare.in Work
pai identity alias list
pai identity clear --agent claude

pai billing report --provider openai --provider anthropic --from 2025-06-01
pai billing report --provider google
pai billing pricing --refresh

pai cache info
pai doctor
```

## Billing requirements

Provider support is environment-driven:

| Provider | Required setup |
|---|---|
| OpenAI | `OPENAI_ADMIN_API_KEY` |
| Anthropic | `ANTHROPIC_ADMIN_API_KEY` |
| Google | `GOOGLE_BILLING_PROJECT_ID`, `GOOGLE_BILLING_DATASET_ID`, BigQuery libraries |

The installer already injects the Google BigQuery libraries into the pipx environment.

## Identity telemetry setup

Identity display is honest by default:

- if `pai` can only prove auth mode or provider, it shows that
- if `pai` can join a session to telemetry identity, it shows the real session identity
- telemetry-backed identity setup is currently only for **Claude** and **Gemini**

### Guided setup

Run:

```bash
pai setup identity
```

That flow:

1. shows current Claude/Gemini identity status
2. offers numbered choices
3. writes XDG-managed config under `~/.config/pai/identity/`
4. writes raw telemetry output under `~/.local/share/pai/identity/raw/`
5. prints the exact env/settings snippet you need

### Claude

Claude identity capture uses OTLP telemetry and a local collector config managed by `pai`.

`pai` stores ingested Claude identity in its own XDG-managed database under `~/.local/share/pai/`.
If an older `~/.claude/custom-user-work/` telemetry/session-map setup still exists, `pai`
will import that legacy data during sync so you can migrate off the old hook-based flow.

Minimal env:

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Important:

- a configured collector is **not enough** by itself
- the collector must be running while Claude emits telemetry
- `pai setup identity` supports:
  - background service
  - manual start/stop
  - config-only

### Gemini

Gemini should use native local file-output telemetry instead of an external collector.

Minimal env:

```bash
export GEMINI_TELEMETRY_ENABLED=true
export GEMINI_TELEMETRY_TARGET=local
export GEMINI_TELEMETRY_OUTFILE="$XDG_DATA_HOME/pai/identity/raw/gemini-telemetry.jsonl"
```

Equivalent `settings.json` shape:

```json
{
  "telemetry": {
    "enabled": true,
    "target": "local",
    "outfile": "/absolute/path/to/gemini-telemetry.jsonl"
  }
}
```

### Aliases

Aliases let you keep a readable label without hiding the raw identity value.

```bash
pai identity alias set --agent claude tech@tatvacare.in Work
pai identity alias list
pai identity alias remove --agent claude tech@tatvacare.in
```

Display example:

- `Work [tech@tatvacare.in] (session)`

### Clearing telemetry-derived identity state

To clear ingested telemetry identity state and raw telemetry files:

```bash
pai identity clear --agent claude
pai identity clear
```

Defaults:

- clears ingested identity events and offsets
- clears raw telemetry files for Claude/Gemini
- clears cached session rows so fallback identity is rebuilt cleanly
- keeps aliases and setup config unless you explicitly add:
  - `--include-aliases`
  - `--include-setup`

## Packaging notes

- Python package name: `pai-cli`
- Console entry point: `pai`
- Source layout: `src/`
- Cache/config/data paths follow XDG-style separation

## Repo

- GitHub: <https://github.com/pareekshithbompally/pai-cli>
