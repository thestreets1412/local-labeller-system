# ADR 0002: Phase 2 account and membership administration

Status: accepted implementation of the first Phase 2 increment (PR09, PR18).

The user accepted the local rectangle/classification workflow, reopen persistence,
and DPI operation, and explicitly requested Phase 2. Preserve that milestone while
adding team capabilities in runnable increments.

System administrators create non-admin accounts and change display name, password,
disabled state or session revocation. This increment does not expose administrator
promotion. A new account has no project membership by default. Usernames are
case-insensitive ASCII login identifiers; display names and user data remain Unicode.

`PATCH /users/{id}` requires `expected_user_revision`. Migration 0002 only adds the
revision column with default 1 and does not rewrite immutable artifacts. User
mutations recheck administrator/session authority inside the commit transaction.
Password hashing occurs outside the write transaction; login rechecks account and
password state before issuing a token so an in-flight login cannot bypass a reset.

Account mutation idempotency fingerprints passwords using a server-keyed HMAC
before hashing the request. Passwords and password hashes are excluded from public
responses, audit details and replay responses. Reset, disable and explicit session
revocation invalidate tokens and increment lease generations in the same transaction.

Project maintainers manage membership with `expected_project_revision`. Both role
changes and removals invalidate the user's project leases atomically, without
revoking unrelated project leases. Removing/demoting the last active maintainer is
rejected; disabling an account cannot leave a project without an active maintainer
or remove the last active administrator. Admin status never bypasses these checks
or revision validation. Removal accepts a JSON body and an Idempotency-Key on DELETE.

GET /users is administrator-only and paginated. Project members may list only their
project's members. Maintainers can add an account using its exact user ID supplied
by an administrator; no global user directory is exposed to them. /me reports the
current project roles. Project responses expose can_edit/can_manage_members for UI
affordances; server checks remain authoritative.

Team & users is a modal desktop panel. Its text entry cannot trigger canvas
shortcuts. Transient mutation failures can retry the same request/key. Conflicts
require an explicit refresh; the client never silently changes expected revisions.

Assignments, claim-next, revision-bound reviews, audit browsing, LAN HTTPS and
share mappings remain open Phase 2 work; this increment does not claim that exit gate.
