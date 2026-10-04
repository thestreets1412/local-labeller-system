# Phase 2 implementation sequence

Status: started with explicit user authorization after Phase 1 pilot acceptance.
Increment 1 (users and project roles) is implemented and verified. Items 2–5 remain
open within Phase 2; no requirement has been deferred to another phase. LAN exposure
and the complete Phase 2 exit gate are not yet implemented/claimed.

The user tested increment 1 and requested Phase 3 next. Continue independent polygon
and working-QC development on the home PC; retain items 2–5 as open Phase 2 work.
Actual two-machine/LAN/SMB acceptance is explicitly deferred to the company setup,
not treated as passed. See `phase3-plan.md` for the sequencing override. The user
also reported confusing member onboarding; the administrator now chooses a user
directly in the Project members tab before selecting a role.

1. **Users and project roles (PR09, PR18):** freeze the permission matrix and
   API contracts; add migrations and administrator/maintainer management UI.
   Verify denied access, session revocation, and project isolation through the API.
   **Implemented:** Team & users UI, account create/update/reset/disable/revoke,
   membership list/set/remove, optimistic revisions, scoped lease invalidation,
   last-active-admin/maintainer protection, migration 0002, and API/UI smoke checks.
2. **Assignments and atomic claim-next (PR09, PR04):** persist assignments,
   choose assigned work before unassigned work in a deterministic order, and add
   audited revoke/reassign operations. Add desktop queue actions and assignee
   filters. Verify independent-client claim races and stale-generation rejection.
3. **Completion and review (PR08, PR10):** implement complete/submit/approve/
   reject/reopen with revision-bound review evidence, required rejection comments,
   and default self-review prevention. Add reviewer queue and conflict states.
   Verify rejection -> edit -> resubmit and stale approval rejection.
4. **Audit/history (PR12):** expose authorized history and audit browsing;
   restoring an earlier annotation creates a new revision through normal save
   validation. Verify actors, revisions, object changes, and permission checks.
5. **LAN deployment and asset access (PR18):** configure authenticated HTTPS and
   client trust, read-only SMB mappings with API fallback, and scoped share access.
   Keep loopback defaults until deployment is configured. Verify with two actual
   machines, including denied API/share access, expired claim recovery, and the
   full Engineer/Junior review journey.

Use small runnable API + desktop increments; the existing leases, fencing,
idempotency, immutable publication, and encrypted recovery remain the persistence
foundation. The full Phase 2 exit gate requires two-machine evidence, not only
in-process or same-machine clients. No requirement is moved to another phase.

## Increment 1 evidence

- Full automated suite: 54 passed (the original 46 plus 8 team tests).
- Ruff formatting/lint and mypy passed.
- Rendered desktop against a real local HTTP server: create an account, assign
  annotator role, and update the account; rectangle save/reload/recovery also pass.
- Independent wheel install outside the repository includes migration 0002 and
  renders the desktop. This is still a development-machine smoke test.
- Concurrency: simultaneous membership updates produce one winner and one
  revision conflict; a role downgrade between annotation publish and commit
  prevents the stale write. Removing membership leaves other-project leases intact.
- Password reset/disable invalidates sessions and leases; re-enabling does not
  resurrect revoked tokens. Existing Phase 1 account records survive migration.

See `contracts/phase2-openapi.json` and `verification-artifacts/team-members.png`.
The Phase 1 OpenAPI snapshot is preserved. The known Starlette TestClient HTTPX
deprecation warning remains; it does not fail the suite.
