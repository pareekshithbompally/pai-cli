# Investigation: pai-cli-status-readiness

## What Was Investigated

This investigation reviewed the overall status of `pai-cli` as a shippable CLI package: command surface, session/cache flow, billing flow, install/packaging path, and code-quality risks. The goal was to determine what already works, what is missing for release readiness, and where the most likely bugs or maintenance problems sit without changing code.

## Files and Entry Points

- `/Users/dhspl/.local/bin/pai-cli/README.md` — documented install path, command surface, and claims about billing/setup behavior.
- `/Users/dhspl/.local/bin/pai-cli/pyproject.toml` — package metadata, dependencies, optional extras, and console entry point.
- `/Users/dhspl/.local/bin/pai-cli/install.sh` — curl-to-shell installer using `pipx` plus Google dependency injection.
- `/Users/dhspl/.local/bin/pai-cli/.gitignore` — ignored junk/build artifacts policy.
- `/Users/dhspl/.local/bin/pai-cli/docs/investigations/account-data-trace.md` — existing investigation format reference.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/__main__.py` — module execution entry point.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/main.py` — root Click group; wires all top-level commands.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/sessions.py` — sessions command group registration.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/history.py` — recent session listing flow.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/stats.py` — aggregate per-identity session reporting.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/messages.py` — per-session message inspection flow.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/plans.py` — plan discovery and display flow.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/cache.py` — cache info/clear commands.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/identity.py` — alias management and telemetry-backed identity clearing.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/setup.py` — interactive identity setup flow.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/doctor.py` — runtime/storage/agent/billing diagnostics.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/commands/sync.py` — sync orchestration before session queries.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/common/cache.py` — SQLite session cache, schema, sync, and query logic.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/common/paths.py` — XDG path helpers used by cache/config/data storage.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/common/types.py` — `SessionRecord`, `MessageRecord`, `PlanRecord`, identity display formatting.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/common/accounts.py` — identity helper functions used by adapters.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/common/identity_config.py` — identity setup/config file locations.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/common/identity_ingest.py` — incremental telemetry ingestion for Claude/Gemini.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/common/identity_store.py` — SQLite identity DB and alias/setup state.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/__init__.py` — adapter registry.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/base.py` — adapter interface.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/catalog.py` — filesystem mapping for all supported agents.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/claude.py` — Claude session/plan parsing.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/codex.py` — Codex session/plan parsing.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/copilot.py` — Copilot session/plan parsing.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/gemini.py` — Gemini session parsing.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/vibe.py` — Vibe session parsing.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/billing/__init__.py` — billing command group registration.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/billing/pricing.py` — LiteLLM pricing fetch/cache/lookup logic.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/billing/pricing_cmd.py` — pricing table display command.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/billing/report.py` — billing report flow and aggregation.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/billing/providers/base.py` — shared HTTP helper and provider base type.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/billing/providers/openai.py` — OpenAI org usage fetcher.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/billing/providers/anthropic.py` — Anthropic usage fetcher.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/billing/providers/google.py` — BigQuery billing fetcher.

## Trace

1. Packaging starts in `pyproject.toml:5-24`, where the project is named `pai-cli`, requires Python `>=3.10`, depends only on `click`, `rich`, `requests`, and `python-dateutil`, and exposes the console script `pai = "pai.main:main"` at `pyproject.toml:18-20`.

2. Runtime entry begins at `src/pai/__main__.py:1-5`, which imports `main()` from `src/pai/main.py`. The root Click group is defined in `src/pai/main.py:33-47`, and it registers `sessions`, `cache`, `identity`, `billing`, `setup`, and `doctor` at `main.py:38-43`.

3. Session-facing commands branch through `src/pai/commands/sessions.py:13-21`, which wires `history`, `stats`, `messages`, and `plans`.

4. The main “read session data” flow is:
   - `history.py:33-40` or `stats.py:24-31` resolve agent filters and instantiate `SessionCache`.
   - `commands/sync.py:12-16` calls `ingest_identity_telemetry(agents)` before any cache work.
   - `commands/sync.py:17-47` walks agent files, compares on-disk `(mtime, size)` against cached rows by directly querying `cache._conn`.
   - If parsing is needed, `commands/sync.py:49-64` calls `SessionCache.sync()`.
   - `common/cache.py:66-128` discovers files through each adapter, deletes removed rows, parses changed files, and upserts rows into SQLite.
   - Querying then happens via `common/cache.py:132-160`, which returns `SessionRecord` objects sorted by `last_ts DESC NULLS LAST`.

5. The per-agent parsing boundary is declared in `agents/base.py:22-41` and backed by the registry in `agents/__init__.py:12-30`. Filesystem roots/globs come from `agents/catalog.py:37-90`, which maps Claude, Codex, Copilot, Gemini, and Vibe into their hidden home-directory storage.

6. Adapter implementations are thin and file-format specific:
   - Claude parses JSONL and counts user messages in `agents/claude.py:44-93`; plans come from `claude.py:113-125`.
   - Codex parses `turn_context`, `response_item`, and token-count events in `agents/codex.py:51-125`; plans come from `codex.py:158-170`.
   - Copilot parses `user.message` and `session.shutdown` in `agents/copilot.py:38-94`; plans come from `copilot.py:115-129`.
   - Gemini parses a single JSON session file in `agents/gemini.py:45-108`.
   - Vibe parses JSONL plus sibling `meta.json` in `agents/vibe.py:32-71`.

7. `messages` is slightly different from the other session commands. After sync it performs a raw SQL lookup directly against `cache._conn` in `commands/messages.py:38-47`, then streams message text through the owning adapter at `messages.py:66-77`.

8. Identity setup/storage flows are split across:
   - `commands/setup.py:34-197` for interactive setup and config writing,
   - `common/identity_config.py:11-40` for config/raw path resolution,
   - `common/identity_ingest.py:16-80` for incremental raw-log ingestion into SQLite,
   - `common/identity_store.py:12-267` for alias/event/offset/setup tables,
   - `commands/identity.py:35-184` for alias CRUD and clearing telemetry state,
   - `commands/doctor.py:92-110` for reporting configured identity status.

9. The installer path is:
   - `install.sh:28-48` finds Python `>=3.10`,
   - `install.sh:50-66` hard-fails if `pipx` is missing,
   - `install.sh:70-73` runs `pipx install --force --python "$PYTHON" "$INSTALL_SPEC"`,
   - `install.sh:75-78` injects `google-cloud-bigquery` and `db-dtypes`,
   - `install.sh:80-86` checks whether `$PIPX_BIN_DIR/pai` exists and otherwise tells the user to run `pipx ensurepath`.

10. Billing branches through `billing/__init__.py:11-17` into:
    - `pricing_cmd.py:11-56`, which loads or refreshes the LiteLLM-derived pricing cache,
    - `report.py:69-189`, which parses dates, filters available providers, loads pricing, fetches usage, computes cost, aggregates, and renders tables.

11. Provider behavior is layered as follows:
    - `providers/base.py:39-56` uses `requests.get()` with retry/backoff and returns parsed JSON or `None`.
    - `providers/openai.py:24-67` paginates 31-day windows over OpenAI org usage.
    - `providers/anthropic.py:27-102` pages through Anthropic organization usage buckets.
    - `providers/google.py:40-106` discovers the BigQuery export table, queries summed net cost, and returns precomputed USD cost.
    - `billing/pricing.py:30-103` fetches LiteLLM pricing JSON, transforms it into provider tables, and caches to `~/.cache/pai/api_pricing.json`.

12. Repository-level readiness checks performed during this investigation:
    - `python3 -m pai --help`, `python3 -m pai doctor`, `python3 -m pai sessions history -n 2`, `python3 -m pai sessions stats --agent claude`, `python3 -m pai sessions plans --agent copilot`, `python3 -m pai sessions messages <current-session-events.jsonl>`, `python3 -m pai cache info`, `python3 -m pai billing pricing`, `python3 -m pai setup --help`, and `python3 -m pai identity alias list` all executed successfully from source using `PYTHONPATH=src`.
    - `python3 -m pai billing report --provider openai --last 1d` returned `No billing data found.` rather than an explicit API error.
    - `bash -n install.sh` succeeded.
    - `python3 -m pip wheel . --no-deps -w /tmp/pai-wheel` succeeded and produced `pai_cli-0.1.0-py3-none-any.whl`.
    - `python3 -m pip install . --dry-run` resolved dependencies cleanly.
    - `glob("**/test*")` found no tests, and `glob("**/.github/**/*")` found no CI/workflow files.
    - `git log --oneline -5` showed only two commits on `main`, and `git ls-files` showed 46 tracked files total.

## Findings

1. Confirmed: the package entry point, source-layout packaging, and local wheel build are working. `pyproject.toml` is coherent with the `src/` layout, and a wheel can be built successfully.
2. Confirmed: the installer script is syntactically valid and matches the README’s documented `pipx`-first install path.
3. Confirmed: the core command surface is functional in the current environment. Help, doctor, session inspection, cache inspection, identity listing, and pricing display all ran successfully from source.
4. Confirmed: the project is still early-stage from a release-process perspective. The repo has no test files, no GitHub Actions/workflows, and only two visible commits.
5. Confirmed: the storage model is simple and understandable — one SQLite cache for sessions (`common/cache.py:28-63`) and one SQLite DB for identity state (`identity_store.py:10-53`) under XDG paths.
6. Confirmed: `doctor` provides a useful readiness snapshot by checking runtime, storage, agent roots, identity setup, and billing env/provider availability in one place (`commands/doctor.py:23-138`).
7. Suspected issue: several important paths suppress failures instead of surfacing them. Examples:
   - session parsing failures are swallowed in `common/cache.py:114-125`,
   - pricing fetch/load/write failures are swallowed in `billing/pricing.py:30-37`, `74-82`, and `97-102`,
   - Google billing query/discovery failures collapse to empty results in `providers/google.py:75-100`,
   - generic HTTP failures collapse to `None` in `providers/base.py:39-56`.
   In practice this means “partial data” and “broken data/API” can look identical to the user.
8. Suspected issue: the billing report path cannot distinguish “no usage” from “fetch failed” for some providers. The observed `No billing data found.` output for OpenAI is consistent with genuine zero usage, but the current provider/base helper design would also produce the same end result for several non-200 or request-failure scenarios.
9. Suspected issue: pricing table transformation is over-broad. `billing/pricing.py:52-59` classifies a model as OpenAI if `provider == "openai" or "gpt" in model`, which pulls Azure-prefixed and image-size pseudo-model entries into the OpenAI pricing table. This does not prove wrong cost output for real OpenAI models, but it does make the pricing surface noisy and weakens provider separation.
10. Suspected issue: command code is coupled to cache internals. Both `commands/sync.py:33-39` and `commands/messages.py:40-47` directly query `cache._conn`, bypassing `SessionCache`’s public API and making future refactors riskier.
11. Suspected issue: portability/install readiness has only been partially exercised. The current investigation confirmed packaging and dry-run install locally, but did not find automated validation for clean-machine installs, Python-version matrix coverage, or smoke tests after `pipx install`.

## Open Questions

1. Should `pai billing report` surface provider/API errors explicitly instead of collapsing them into the same “No billing data found.” outcome?
2. Is the broad-model inclusion in `billing/pricing.py` intentional for cross-provider cost lookup, or is the displayed OpenAI table meant to exclude Azure and image-size entries?
3. What minimum release bar do you want for this tool: personal-use CLI, team-internal utility, or publicly installable package with CI and tests?
4. Is `install.sh` expected to support only macOS/Linux with preinstalled `pipx`, or should first-run bootstrap of `pipx` also be handled?

## Recommended Next Step

Decide the intended release tier for `pai-cli`, then add the smallest matching validation layer first — at minimum a smoke-test path that proves install, core commands, and failure reporting behave correctly on a clean environment.
