# CR-030 Local Agent Orchestrator Review

Date: 2026-03-10
Status: Hardened

## Scope

Review and harden the local agent-heartbeat flow so it can do more than print `go`.

## Findings

- `scripts/agent_heartbeat.py` correctly detects idle git state and emits a local `go` signal.
- That monitor alone cannot resume Codex work because it has no execution bridge into the local Codex client.
- A local Codex CLI is present on this machine and supports non-interactive execution through:
  - `codex exec`
- Without a rate-limited bridge, a naive loop would be noisy and unsafe:
  - repeated prompts for the same idle window
  - no durable state about the last trigger
  - no audit trail of what was invoked

## Actions Taken

- Added `scripts/agent_orchestrator.py` as the execution bridge:
  - reads the heartbeat JSON
  - computes runtime idle minutes
  - applies idle threshold + reprompt window
  - invokes `codex exec` when the repo is truly idle
  - writes orchestrator state and the last command/output paths under `output/`
- Added unit coverage for:
  - new idle-window trigger
  - reprompt suppression
  - command construction
  - dry-run state persistence

## Safety Model

- Default prompt is intentionally minimal: `go`
- Re-triggering is blocked for the same `last_change_at` window until the reprompt threshold elapses
- `--dry-run` is supported for safe local verification
- The script records the last command and trigger timestamps in `output/agent-orchestrator.json`

## Limits

- This is still a local automation bridge, not a scheduler.
- It depends on a callable local `codex.exe`.
- It does not solve higher-level task selection or result triage; it only automates the "resume/continue" handoff.

## Evidence

- `scripts/agent_orchestrator.py`
- `tests/unit/scripts/test_agent_orchestrator.py`
- `codex.exe --help`
- `codex exec --help`
