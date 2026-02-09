# Auth Backend Removal Plan (Memory + File)

Goal: remove the memory and file auth backends because they are no longer used.
Focus: code removal, configuration cleanup, tests, and docs.


## Priority Order (force-ranked)

1) Remove backend selection paths that allow memory/file
2) Remove memory/file backend implementations and tests
3) Migrate env/config and docs to Vault-only
4) Clean up CLI and scripts that still reference memory/file
5) Add regression tests for Vault-only behavior


## Step-by-step plan

### 1) Lock backend selection to Vault-only (highest priority)

Problem:
- create_stores_from_env currently accepts "memory" and "file" and defaults to
  "memory" when unset. This allows unintended insecure modes.

Plan:
1.1 Update create_stores_from_env to require GOFR_*_AUTH_BACKEND="vault".
1.2 If unset or not vault, raise a FactoryError with remediation:
    - "Set {PREFIX}_AUTH_BACKEND=vault"
    - "Set {PREFIX}_VAULT_URL / token or AppRole creds"
1.3 Update any callers expecting memory/file fallbacks.

Targets:
- src/gofr_common/auth/backends/factory.py


### 2) Remove memory and file backend implementations

Problem:
- Memory and file stores are still importable and used in tests/fixtures.

Plan:
2.1 Remove memory backend:
    - src/gofr_common/auth/backends/memory.py
    - exports in src/gofr_common/auth/backends/__init__.py
    - references in docs and tests
2.2 Remove file backend:
    - src/gofr_common/auth/backends/file.py
    - exports in src/gofr_common/auth/backends/__init__.py
    - references in docs and tests
2.3 Remove any usage of FileTokenStore/FileGroupStore or MemoryTokenStore/MemoryGroupStore.

Targets:
- src/gofr_common/auth/backends/memory.py
- src/gofr_common/auth/backends/file.py
- src/gofr_common/auth/backends/__init__.py
- src/gofr_common/auth/__init__.py


### 3) Migrate configuration and docs to Vault-only

Problem:
- Docs still describe memory/file options and default to memory.
- Config helpers allow non-Vault backends.

Plan:
3.1 Update auth docs to remove memory/file references.
3.2 Update config resolution docs to require Vault env vars.
3.3 Add a Vault-only configuration example.

Targets:
- src/gofr_common/auth/readme.md
- src/gofr_common/auth/spec.md
- src/gofr_common/auth/vault_spec.md
- docs/auth/* (as needed)


### 4) Clean up CLI and scripts

Problem:
- Some CLIs/tests still use memory/file stores for convenience.

Plan:
4.1 Update CLI utilities to use Vault-only config.
4.2 Remove any CLI args that support file paths for token storage.
4.3 Update scripts to set required Vault env vars for local/dev usage.

Targets:
- scripts/auth_manager.py (if it supports non-vault paths)
- scripts/token_manager.sh (service repos)


### 5) Tests and migration safeguards

Problem:
- Tests rely on memory/file stores.
- Need coverage for Vault-only behavior and clearer failure modes.

Plan:
5.1 Update tests to use ephemeral Vault (already supported by run_tests.sh).
5.2 Add tests asserting FactoryError when backend != vault.
5.3 Add tests for missing Vault env vars with remediation messages.

Targets:
- tests/auth/*
- tests/mcp/* (if they create auth stores)


## Deliverables

- Vault-only backend creation path with clear remediation errors.
- Memory and file backend code removed.
- Docs updated to remove memory/file references.
- Tests updated for Vault-only behavior and error messaging.
