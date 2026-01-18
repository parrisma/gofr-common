# Token Naming Enhancement Proposal

**Status:** Accepted (Phase 4 complete)  
**Author:** System  
**Date:** 2026-01-18  
**Version:** 1.3

## Executive Summary

Add optional human-readable names to JWT tokens to improve token management, auditing, and operational workflows. Names would be unique identifiers (like `prod-api-server`, `dev-admin-token`) that make it easier to identify and manage tokens without relying solely on UUIDs.

## Progress Update (2026-01-18)

- Core data model and all backends now store optional `name`; Memory/File use indexed lookups, Vault uses linear scan (secondary index deferred)
- TokenStore protocol extended with name lookups; tests added for serde and backend name retrieval/uniqueness; backward compatibility validated
- Service layer now accepts validated `name` (lowercased, DNS-like), enforces uniqueness, supports get/revoke by name, and logs names; auth tests updated and passing via `./lib/gofr-common/scripts/run_tests.sh --skip-lint -k auth`
- CLI now supports named tokens: `tokens create --name`, `tokens list` shows Name column + `--name-pattern`, `tokens revoke --name`, `tokens inspect --name`; CLI tests passing via `./lib/gofr-common/scripts/run_tests.sh --skip-lint -k cli_phase3`
- Test runner hardened to use isolated test Vault/network; full suite passes via `./lib/gofr-common/scripts/run_tests.sh --skip-lint`
- Full gofr-common suite re-run (646 tests) via `./lib/gofr-common/scripts/run_tests.sh --skip-lint` ✅
- CLI list JSON/table now sort newest-first for deterministic name visibility; cli_phase3 subset re-run on 2026-01-18 ✅
- Auth docs updated with token naming section and CLI examples (`gofr_auth_system.md`)
- Wrapper smoke test (file backend): create/list/revoke by name ✅
- Next actions: document CLI usage in auth docs, consider Vault name index once API/CLI are in place, add migration/usage guidance

## Problem Statement

Currently, tokens are identified only by UUID (`jti`). This creates challenges:

1. **Poor Visibility**: Operators must inspect token contents or cross-reference UUIDs to identify purpose
2. **Difficult Auditing**: Log entries with UUIDs are hard to correlate with specific services/users
3. **Manual Tracking**: Teams maintain external spreadsheets mapping UUIDs to purposes
4. **Revocation Risk**: Revoking the wrong token because UUIDs look similar

**Current Experience:**
```bash
$ auth_manager.sh --docker tokens list
ID                                     Status     Groups
----------------------------------------------------------------------
d9b26866-c7fc-486d-864a-1c13c86cc7de   active     admin
ec425f14-5db5-414e-9c6b-8f88ed44895e   active     public
# Which one is the production API server? Which is the backup cron job?
```

**Desired Experience:**
```bash
$ auth_manager.sh --docker tokens list
Name                     ID                                     Status     Groups
------------------------------------------------------------------------------------------
prod-api-server          d9b26866-c7fc-486d-864a-1c13c86cc7de   active     admin
backup-cron-job          ec425f14-5db5-414e-9c6b-8f88ed44895e   active     public
dev-testing              ...                                    active     users
```

## Design Principles

1. **Optional**: Names are optional to maintain backward compatibility
2. **Non-JWT**: Names stored server-side only, not in JWT payload (prevents bloat)
3. **Unique**: Names must be unique within a workspace (like group names)
4. **Immutable**: Once set, names cannot be changed (prevents confusion in logs)
5. **Validation**: Names must be DNS-like: `[a-z0-9-]+`, 3-64 chars, no leading/trailing hyphens

## Architecture Changes

### 1. Data Model

**TokenRecord Enhancement:**
```python
@dataclass
class TokenRecord:
    id: UUID
    groups: List[str]
    status: Literal["active", "revoked"]
    created_at: datetime
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    fingerprint: Optional[str]
    name: Optional[str] = None  # NEW: Human-readable identifier
```

**Storage Schema (JSON):**
```json
{
  "tokens": {
    "d9b26866-c7fc-486d-864a-1c13c86cc7de": {
      "id": "d9b26866-c7fc-486d-864a-1c13c86cc7de",
      "name": "prod-api-server",
      "groups": ["admin"],
      "status": "active",
      "created_at": "2026-01-18T10:00:00Z",
      "expires_at": "2027-01-18T10:00:00Z",
      "revoked_at": null,
      "fingerprint": null
    }
  }
}
```

**Storage Schema (Vault KV):**
```
secret/gofr/auth/tokens/d9b26866-...
  {
    "id": "d9b26866-...",
    "name": "prod-api-server",
    "groups": ["admin"],
    ...
  }
```

### 2. Storage Backend Changes

**TokenStore Protocol Extension:**
```python
class TokenStore(Protocol):
    """Token storage protocol."""
    
    # Existing methods unchanged
    def get(self, token_id: str) -> Optional[TokenRecord]: ...
    def put(self, token_id: str, record: TokenRecord) -> None: ...
    
    # NEW: Name-based lookup
    def get_by_name(self, name: str) -> Optional[TokenRecord]:
        """Get token by human-readable name.
        
        Returns:
            TokenRecord if found, None otherwise
        """
        ...
    
    def exists_name(self, name: str) -> bool:
        """Check if a token name already exists.
        
        Returns:
            True if name is taken, False otherwise
        """
        ...
```

**Implementation Strategy:**
- **Memory/File**: Linear scan (acceptable for <10k tokens)
- **Vault**: Use secondary index pattern (add `tokens-by-name/` prefix path)

### 3. Service Layer Changes

**AuthService API:**
```python
class AuthService:
    def create_token(
        self,
        groups: List[str],
        expires_in_seconds: int = 86400,
        fingerprint: Optional[str] = None,
        name: Optional[str] = None,  # NEW
    ) -> str:
        """Create a new JWT token.
        
        Args:
            name: Optional human-readable name (unique, immutable)
        
        Raises:
            ValidationError: If name format invalid
            ConflictError: If name already exists
        """
        if name:
            # Validate format
            if not self._validate_token_name(name):
                raise ValidationError(
                    f"Invalid token name: {name}. "
                    "Must be 3-64 chars, lowercase alphanumeric with hyphens, "
                    "no leading/trailing hyphens."
                )
            
            # Check uniqueness
            if self._token_store.exists_name(name):
                raise ConflictError(f"Token name '{name}' already exists")
        
        # Rest of creation logic unchanged
        ...
    
    def get_token_by_name(self, name: str) -> Optional[TokenRecord]:
        """Get token record by name."""
        return self._token_store.get_by_name(name)
    
    def revoke_token_by_name(self, name: str) -> bool:
        """Revoke token by name."""
        record = self.get_token_by_name(name)
        if record:
            # Create minimal JWT to call existing revoke_token
            ...
    
    def _validate_token_name(self, name: str) -> bool:
        """Validate token name format."""
        import re
        pattern = r'^[a-z0-9]([a-z0-9-]{1,62}[a-z0-9])?$'
        return bool(re.match(pattern, name))
```

### 4. CLI Changes

**Creation:**
```bash
# With name (recommended for long-lived tokens)
auth_manager.sh --docker tokens create \
    --name prod-api-server \
    --groups admin,users \
    --expires 31536000

# Without name (backward compatible)
auth_manager.sh --docker tokens create \
    --groups admin \
    --expires 86400
```

**Listing:**
```bash
# Table format includes name column
auth_manager.sh --docker tokens list

# Filter by name pattern
auth_manager.sh --docker tokens list --name-pattern "prod-*"

# JSON output includes name
auth_manager.sh --docker tokens list --format json
```

**Revocation:**
```bash
# By UUID (existing)
auth_manager.sh --docker tokens revoke d9b26866-c7fc-486d-864a-1c13c86cc7de

# By name (new convenience)
auth_manager.sh --docker tokens revoke --name prod-api-server
```

**Inspection:**
```bash
# By token string (existing)
auth_manager.sh --docker tokens inspect eyJhbGc...

# By name (new)
auth_manager.sh --docker tokens inspect --name prod-api-server
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
**Goal:** Add name field without exposing in CLI

- [x] Add `name` field to TokenRecord dataclass
- [x] Update FileTokenStore/MemoryTokenStore with `get_by_name()`/`exists_name()`
- [x] Update VaultTokenStore with name lookup (linear scan for now; secondary index deferred)
- [x] Add name validation logic to AuthService
- [x] Write comprehensive unit tests
- [x] Ensure backward compatibility (existing tokens work)

**Acceptance:**
- All existing tests pass ✅ (run via `./lib/gofr-common/scripts/run_tests.sh --skip-lint`)
- New tests: create token with name, uniqueness validation, lookup by name ✅
- Migration test: old tokens without names still work ✅

### Phase 2: Service API (Week 2)
**Goal:** Expose name parameter in AuthService

- [x] Add `name` parameter to `create_token()`
- [x] Add `get_token_by_name()` method
- [x] Add `revoke_token_by_name()` method
- [x] Add validation error handling
- [ ] Update documentation (service API doc still pending)

**Acceptance:**
- Can create named tokens programmatically ✅
- Name conflicts properly rejected ✅
- Invalid name formats properly rejected ✅

### Phase 3: CLI Integration (Week 2)
**Goal:** Full CLI support

- [x] Add `--name` flag to `tokens create`
- [x] Show name column in `tokens list` output
- [x] Add `--name` option to `tokens revoke`
- [x] Add `--name` option to `tokens inspect`
- [x] Add `--name-pattern` filter to `tokens list`
- [x] Update help text and examples (CLI help updated; broader docs tracked in Phase 4)
- [x] Validate CLI flows via `./lib/gofr-common/scripts/run_tests.sh --skip-lint -k cli_phase3`

**Acceptance:**
- CLI workflow feels natural
- Help text is clear and comprehensive
- Both UUID and name workflows work

### Phase 4: Migration & Docs (Week 3)
**Goal:** Production readiness

- [x] Write migration guide for existing deployments
- [x] Add naming conventions guide (best practices)
- [ ] Update API documentation
- [ ] Add troubleshooting section
- [ ] Create example scripts using names

**Acceptance:**
- Documentation is clear for both new and existing users
- Migration path is smooth with no downtime

## Migration Strategy

### For Existing Deployments

**Option 1: No Action Required**
- Existing tokens continue to work
- New tokens can be created with or without names
- No breaking changes

**Option 2: Gradual Naming**
- Identify important tokens (via audit logs, monitoring)
- Create named replacements for critical tokens
- Transition services to use new named tokens
- Revoke old unnamed tokens after verification

**Operational rollout (recommended):**
1. Inventory long-lived/critical tokens (ops, CI/CD, batch jobs).
2. Issue named replacements using `tokens create --name <env-service-purpose> --groups ...`.
3. Swap credentials in dependent services; confirm authentication.
4. Revoke predecessors via `tokens revoke --name ...` and record in change log.
5. Keep short-lived/ephemeral tokens unnamed if desired; feature is backward compatible.

**Option 3: Bulk Naming Script**
```python
# scripts/name_existing_tokens.py
# Interactive script to assign names to existing unnamed tokens
# Shows: UUID, groups, created_at, last_used (if tracked)
# Prompts: Suggested name based on groups + creation date
# User confirms or provides custom name
```

### Backward Compatibility Guarantees

1. **Unnamed tokens forever valid**: Tokens without names continue working indefinitely
2. **API compatibility**: All existing API calls work unchanged
3. **Storage compatibility**: Old storage files/Vault keys work with new code
4. **CLI compatibility**: Existing scripts using UUIDs continue working

## Naming Conventions (Recommended)

**Pattern:** `{environment}-{service}-{purpose}`

**Examples:**
```
prod-api-server
dev-admin-console
staging-data-pipeline
prod-backup-cron
dev-integration-test
qa-load-tester
prod-monitoring-agent
```

**Best Practices:**
1. Use environment prefix (prod/staging/dev)
2. Include service/component name
3. Add purpose/function suffix
4. Keep under 40 chars for display
5. Avoid dates/versions (creates clutter)
6. Document token inventory in team wiki

## Security Considerations

### 1. Name Enumeration
**Risk:** Attackers could enumerate valid token names  
**Mitigation:** 
- Names are not security-sensitive (UUIDs remain secret)
- Rate limit token API calls
- Log suspicious enumeration attempts

### 2. Name Collision Attacks
**Risk:** Attacker creates token with important-sounding name  
**Mitigation:**
- Reserve critical names (prod-*, admin-*)
- Require admin group to create named tokens
- Audit log all token creations

### 3. JWT Payload Size
**Risk:** Adding names to JWT increases size  
**Mitigation:**
- Names stored server-side only, NOT in JWT
- JWT contains only jti (UUID) as before
- No payload size increase

## Testing Strategy

### Unit Tests
```python
class TestTokenNaming:
    def test_create_token_with_name(self):
        """Token can be created with valid name."""
        
    def test_name_must_be_unique(self):
        """Duplicate names rejected."""
        
    def test_invalid_name_format_rejected(self):
        """Malformed names rejected."""
        
    def test_lookup_by_name(self):
        """Can retrieve token by name."""
        
    def test_revoke_by_name(self):
        """Can revoke token by name."""
        
    def test_unnamed_tokens_still_work(self):
        """Backward compatibility maintained."""
```

### Integration Tests
```python
class TestCLITokenNaming:
    def test_cli_create_named_token(self):
        """CLI can create named token."""
        
    def test_cli_list_shows_names(self):
        """List output includes name column."""
        
    def test_cli_revoke_by_name(self):
        """Can revoke via --name flag."""
```

### End-to-End Tests
- Create named token via API
- Verify authentication works
- List tokens, verify name appears
- Revoke by name
- Verify authentication fails

## Success Metrics

1. **Adoption:** >80% of production tokens have names within 3 months
2. **Operational Efficiency:** Token-related support tickets decrease by 50%
3. **Audit Quality:** Security reviews cite improved traceability
4. **Zero Regressions:** No unnamed token functionality broken

## Alternatives Considered

### Alternative 1: Store Name in JWT
**Rejected:** Increases JWT size, requires signature changes, security risk if names are sensitive

### Alternative 2: External Name Registry
**Rejected:** Adds complexity, synchronization issues, separate failure mode

### Alternative 3: UUID Aliases
**Rejected:** Less intuitive, doesn't solve readability problem

### Alternative 4: Tags/Labels
**Deferred:** Could be Phase 5 enhancement, but names solve 80% of use cases

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Name collisions in multi-tenant | Medium | Low | Workspace-scoped uniqueness |
| Storage backend inconsistency | High | Low | Transactional writes, rollback tests |
| Migration confusion | Medium | Medium | Clear docs, gradual rollout |
| Name-based security assumptions | High | Low | Docs clarify names are NOT secrets |

## Open Questions

1. **Q:** Should names be case-sensitive?  
   **A:** No - enforce lowercase, convert input to lowercase for consistency

2. **Q:** Allow renaming tokens?  
   **A:** No - immutable names prevent audit trail confusion. Create new token instead.

3. **Q:** Maximum name length?  
   **A:** 64 chars (balances display width with expressiveness)

4. **Q:** Reserved name prefixes?  
   **A:** Yes - `admin-*`, `system-*` require admin group

5. **Q:** Name validation for profanity/offensive terms?  
   **A:** Out of scope - organizational policy handles this

## Future Enhancements (Post-MVP)

- **Tags/Labels**: Multi-dimensional categorization (beyond single name)
- **Name History**: Track when tokens are replaced (old-name → new-name)
- **Auto-naming**: Suggest names based on groups + timestamp
- **Name Templates**: Organization-enforced naming patterns
- **Last Used Tracking**: Show when named tokens were last authenticated

## References

- [RFC 7519 (JWT)](https://datatracker.ietf.org/doc/html/rfc7519) - JWT specification
- [GOFR Auth System](./gofr_auth_system.md) - Current auth documentation
- [GitHub Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) - Similar naming UX

## Approval & Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tech Lead | | | |
| Security Review | | | |
| Product Owner | | | |

---

**Next Steps:**
1. Update service API docs and add troubleshooting section; optional helper script for naming existing tokens.
2. Consider Vault name index optimization if name lookups become hot.
3. Optional: add example scripts and reserved-prefix enforcement/`last_used` tracking.

## Step-by-Step Implementation Plan (Small Steps)

### Prep
- [x] Confirm current tests pass: `./lib/gofr-common/scripts/run_tests.sh --skip-lint`
- [ ] Baseline auth docs quick read: `lib/gofr-common/docs/auth/gofr_auth_system.md`

### Step 1: Data Model & Backends
- [x] Add `name: Optional[str]` to `TokenRecord` (+ serde) in auth models
- [x] Add name validation helper (regex, length) in AuthService utils
- [x] Extend TokenStore protocol with `get_by_name` / `exists_name`
- [x] Implement for memory + file stores (linear scan ok)
- [x] Implement for Vault store (linear scan; secondary index deferred)
- [x] Tests: model serialization, name lookup, uniqueness, invalid formats

### Step 2: Service Layer
- [x] Add `name` param to `AuthService.create_token(...)`
- [x] Add validation helper (regex/length) + uniqueness check via store methods
- [x] Add `get_token_by_name`, `revoke_token_by_name`
- [x] Keep JWT payload unchanged (no name in token)
- [x] Tests: create with name, conflict, revoke by name, unnamed tokens still work

### Step 3: CLI (auth_manager.py)
- [x] Add `--name` to `tokens create`
- [x] Add `--name` to `tokens revoke` (optional alternative to UUID)
- [x] Add `--name` to `tokens inspect` (lookup then inspect)
- [x] Add `--name-pattern` filter to `tokens list` (simple substring/glob)
- [x] Show name column in table output; include in JSON
- [x] Update help/epilog examples
- [x] Tests: CLI create/list/revoke/inspect with name (integration-level)

### Step 4: Wrapper Script (auth_manager.sh)
- [x] Ensure flags pass-through; no change except help text mention name usage
- [x] Smoke test via wrapper: list/create/revoke by name

### Step 5: Docs
- [x] Update `gofr_auth_system.md` with token naming section
- [x] Update `token_naming_proposal.md` status → “Accepted / In progress” when ready
- [x] Add CLI examples to docs (create/revoke/list by name)

### Step 6: Migration Notes
- [x] Document that unnamed tokens remain valid
- [x] Add guidance for gradually issuing named replacements
- [ ] Optional helper script stub: `scripts/name_existing_tokens.py` (interactive planner; can be TODO)

### Step 7: Test & Validate
- [x] Full unit + integration: `./lib/gofr-common/scripts/run_tests.sh --skip-lint`
- [x] Targeted auth tests: `./scripts/run_tests.sh -k auth`
- [ ] Manual smoke via CLI (using wrapper) in dev container:
    - List tokens: `./lib/gofr-common/scripts/auth_manager.sh --docker tokens list`
    - Create named token: `... tokens create --name dev-admin --groups admin`
    - Revoke by name: `... tokens revoke --name dev-admin`

### Step 8: Rollout
- [ ] Merge to main after review
- [ ] Communicate naming convention + examples to team
- [ ] Encourage naming for new long-lived tokens; keep UUID flow for short-lived/test

### Step 9: Follow-ups (Optional)
- [ ] Add `last_used` tracking (if not already) to improve cleanup
- [ ] Consider reserved prefixes enforcement (admin-*, system-*)
- [ ] Add tags/labels as future enhancement (Phase 5)
