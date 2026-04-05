# Investigation: account-data-trace

## What Was Investigated

This investigation traced what account or identity information can actually be captured from the on-disk storage used by each supported agent: Claude, Codex, Copilot, Gemini, and Vibe. The goal was to distinguish real account-identifying data present in native agent files from local hacks, config-only hints, workspace metadata, and hardcoded labels currently used by `pai`.

## Files and Entry Points

- `/Users/dhspl/.local/bin/pai-cli/src/pai/common/accounts.py` — current account-label logic; shows which labels are hardcoded today.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/claude.py` — Claude adapter entry point; reads session files and the custom account mapping file.
- `/Users/dhspl/.claude/custom-user-work/session-accounts.jsonl` — custom session-to-email mapping created outside native Claude session storage.
- `/Users/dhspl/.claude/settings.json` — Claude settings; used to confirm the custom hook setup exists outside normal session files.
- `/Users/dhspl/.copilot/config.json` — Copilot global config with persisted login information.
- `/Users/dhspl/.copilot/session-state/0ba66a17-9cce-4509-abae-a8205379c2ba.jsonl` — sample Copilot session log showing authentication events inside session history.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/copilot.py` — Copilot adapter; currently ignores available account data and returns a fixed label.
- `/Users/dhspl/.codex/.codex-global-state.json` — Codex global state with repo-owner and creator identifiers.
- `/Users/dhspl/.codex/sessions/2026/03/14/rollout-2026-03-14T11-16-27-019ceae1-bae8-7663-9e0c-9ffb524e5857.jsonl` — sample Codex session log showing session metadata fields.
- `/Users/dhspl/.codex/state_5.sqlite` — Codex local state DB; checked for user/login/email/account/auth/profile columns.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/codex.py` — Codex adapter; currently hardcodes account.
- `/Users/dhspl/.gemini/settings.json` — Gemini global config showing auth mode only.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/gemini.py` — Gemini adapter; currently hardcodes account.
- `/Users/dhspl/.vibe/config.toml` — Vibe config showing provider/env-var setup.
- `/Users/dhspl/.vibe/logs/session/session_20260326_065106_ab45c15c/meta.json` — sample Vibe session metadata showing `username` but not provider account identity.
- `/Users/dhspl/.local/bin/pai-cli/src/pai/agents/vibe.py` — Vibe adapter; currently hardcodes account.

## Trace

1. The current CLI account layer starts in [`accounts.py`](/Users/dhspl/.local/bin/pai-cli/src/pai/common/accounts.py:1). It has two hardcoded paths:
   - Claude emails are mapped through `CLAUDE_EMAIL_LABELS` at lines 13-16.
   - Codex, Copilot, Gemini, and Vibe are mapped through `AGENT_FIXED_ACCOUNTS` at lines 19-24.
   This means current output is not derived generically from agent-native storage.

2. Claude’s adapter in [`claude.py`](/Users/dhspl/.local/bin/pai-cli/src/pai/agents/claude.py:1) explicitly reads `_LOCATION.files["accounts"]` as `ACCOUNTS_FILE` at lines 20-22, then resolves the session account from `load_claude_accounts()` at lines 31-35 and `resolve_claude_account()` at lines 44-47.

3. The actual Claude account data used by `pai` is in [`session-accounts.jsonl`](/Users/dhspl/.claude/custom-user-work/session-accounts.jsonl:1), where each row is `{session_id, email, timestamp}`. Sample rows at lines 1-20 show direct session-to-email mappings such as `pareekshithbompally@gmail.com` and `tech@tatvacare.in`.

4. Claude’s general settings file [`settings.json`](/Users/dhspl/.claude/settings.json:1) does not itself expose an account label in the viewed section, but Claude-wide grep results showed it references `capture-session-account.py`, confirming the email mapping is part of a custom hook pipeline and not a guaranteed native Claude file.

5. Copilot exposes account data in two places:
   - Global config [`config.json`](/Users/dhspl/.copilot/config.json:29) contains `logged_in_users` and `last_logged_in_user` with `host` and `login`; lines 29-38 show `pareekshithbompally`.
   - Session log [`0ba66a17-...jsonl`](/Users/dhspl/.copilot/session-state/0ba66a17-9cce-4509-abae-a8205379c2ba.jsonl:1) contains a `session.info` authentication event at line 2: `Logged in as user: pareekshithbompally`.
   The current Copilot adapter in [`copilot.py`](/Users/dhspl/.local/bin/pai-cli/src/pai/agents/copilot.py:1) does not parse either and instead returns `fixed_account(self.name)`.

6. Codex session files do not show direct account identity in the sampled session metadata. In [`rollout-...jsonl`](/Users/dhspl/.codex/sessions/2026/03/14/rollout-2026-03-14T11-16-27-019ceae1-bae8-7663-9e0c-9ffb524e5857.jsonl:1), the `session_meta.payload` includes `cwd`, `originator`, `cli_version`, `source`, and `model_provider="openai"`, but no user email/login.

7. Codex global state in [` .codex-global-state.json`](/Users/dhspl/.codex/.codex-global-state.json:1) contains GitHub-related metadata, including:
   - `repo_map.owner.login = "Yash110601"`
   - `creator_id = "user-hQPRrBDKWTWhaYQoHvJrOebM__..."`
   These are not clearly the authenticated Codex account for the local user and are tied to environment/repo records rather than session records.

8. Codex SQLite state was inspected by querying `/Users/dhspl/.codex/state_5.sqlite`. The DB contains tables such as `threads`, `jobs`, `logs`, and `agent_jobs`, but no table columns matching `user`, `login`, `email`, `auth`, `account`, or `profile`. No obvious account-identifying structured field was found there.

9. Gemini exposes only auth mode, not a concrete user identifier, in the checked local files. [`settings.json`](/Users/dhspl/.gemini/settings.json:2) contains `security.auth.selectedType = "oauth-personal"` at lines 2-5. Broader grep over `.gemini` did not surface a user email/login in the session files that were checked.

10. The Gemini adapter in [`gemini.py`](/Users/dhspl/.local/bin/pai-cli/src/pai/agents/gemini.py:1) parses `sessionId`, `summary`, timestamps, and token data, but does not have a native account source to consume from the traced files.

11. Vibe’s config in [`config.toml`](/Users/dhspl/.vibe/config.toml:36) exposes provider configuration and `api_key_env_var` names, for example `MISTRAL_API_KEY` at lines 36-44, but not a logged-in account identity.

12. Vibe session metadata in [`meta.json`](/Users/dhspl/.vibe/logs/session/session_20260326_065106_ab45c15c/meta.json:1) includes `username = "dhspl"` at line 10. This is a local OS username, not a provider account identifier or email. The Vibe adapter in [`vibe.py`](/Users/dhspl/.local/bin/pai-cli/src/pai/agents/vibe.py:54) ignores it and returns `fixed_account(self.name)`.

## Findings

1. Confirmed: Claude account attribution currently depends on a non-native custom file, [`session-accounts.jsonl`](/Users/dhspl/.claude/custom-user-work/session-accounts.jsonl:1), produced by your own OTEL/hook workflow.
2. Confirmed: Copilot has real account identity available natively, both in global config (`login`) and inside session logs (`Logged in as user: ...`).
3. Confirmed: Gemini exposes only a coarse auth mode (`oauth-personal`) in the traced files, not a user email/login.
4. Confirmed: Vibe exposes provider/env-var configuration and local `username`, but no provider account identity in the traced files.
5. Confirmed: Codex session files do not expose a clear account identifier in the traced session metadata.
6. Confirmed: Codex global state contains GitHub-related owner/creator identifiers, but they are not clearly a reliable local account label and are not linked per session in the same way Claude/Copilot are.
7. Confirmed: The current `pai` account model is partly derived from real files (Claude custom mapping), partly derivable from native files (Copilot), and partly hardcoded despite weak or absent native identity sources (Codex, Gemini, Vibe).
8. Suspected issue: Treating non-Claude agents as fixed single-account tools is a portability shortcut, not a property supported by the traced files.
9. Suspected issue: Any future generic account model will need per-agent capability tiers:
   - session-linked native identity available
   - global identity available but not session-linked
   - auth-mode/provider only
   - no account identity available

## Open Questions

1. Does Codex store authenticated user identity in another local file, keychain, or service-managed cache outside the traced session/global-state files?
2. Does Gemini persist a concrete authenticated identity somewhere outside `settings.json` and session files, or is only auth mode exposed locally?
3. Does Vibe have another local state file beyond `config.toml` and `logs/session/*` that captures provider-account identity rather than OS username?
4. For tools with only global identity and not per-session identity, should `pai` display that value as `account`, or should it reserve `account` only for session-resolved data?

## Recommended Next Step

Define a capability-based account extraction model per agent, using native per-session identity where available, native global identity where defensible, and a neutral fallback when no trustworthy account detail exists.
