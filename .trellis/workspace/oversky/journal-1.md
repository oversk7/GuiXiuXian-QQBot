# Journal - oversky (Part 1)

> AI development session journal
> Started: 2026-04-24

---



## Session 1: Continue multi-server shard implementation

**Date**: 2026-05-16
**Task**: Continue multi-server shard implementation
**Branch**: `main`

### Summary

WIP sync: multi-server shard implementation is code-complete enough for test deployment checks, but not recommended for full production rollout yet. Verified compileall for plugins/xiuxian_game and the focused attribute calculator test. Fixed account transfer cancellation/admin transfer server-binding checks, sponsor alt-account same-server checks, and guild application applicant lookup by server. Remaining rollout work: configure servers/server_profiles, run migration on a database copy, and manually validate registration, identity binding, market/auction/stall/guild/world/ranking isolation.

### Main Changes

- Continued multi-server shard implementation and release-readiness review.
- Confirmed core shard code compiles across `plugins/xiuxian_game`.
- Fixed account-transfer cancellation server binding logic and admin transfer same-server enforcement.
- Fixed sponsor alt-account binding so request/confirm flows stay within the same server.
- Fixed guild applicant UID lookup so approval/rejection uses the operator's server.

### Git Commits

(No commits - WIP sync only)

### Testing

- [OK] `python -m compileall plugins/xiuxian_game`
- [OK] `python -m pytest tests/test_attribute_calculator_simple.py` (4 passed)
- [WARN] `tests/test_basic_framework.py` still has an existing collection/import-path issue: attempted relative import beyond top-level package

### Status

[WIP] **Check / gray-deploy readiness**

Not recommended for full production rollout yet. Safe next step is test or gray deployment only.

### Next Steps

- Add explicit `servers` / `server_profiles` entries to `plugins/xiuxian_game/data/config.yaml` before opening a new server.
- Run database migration against a production database copy and confirm `server_id` fields plus `platform_server_binding` are created.
- Manually smoke test registration, identity binding, transfer/switching, sponsor alt binding, rankings, market, auction, stall, guild, mansion, nearby players, and maps across server boundaries.

---

## Session 2: Close cross-shard resource transfer gaps

**Date**: 2026-05-16
**Task**: Re-audit under rule: legacy-server resources must not be transferable into a new server
**Branch**: `main`

### Summary

Patched another set of player-to-player resource paths that still resolved targets by global UID or group only. The main principle now enforced in these paths is: resolve the actor first, then resolve target/account/envelope records inside the actor's `server_id`.

### Main Changes

- Scoped red envelopes by `server_id`: model, repository, send/grab/recent-record queries, and average-gold cache now operate per shard.
- Scoped invitation rewards by `server_id`: records now include shard, inviter lookup is same-server only, and legacy JSON invite records use `server_id:uid` keys.
- Scoped relationship resource paths: favorability gifts, face-to-face item gifts, equipment/inscription transfer, marriage/sworn/mentorship request flows, and favorability target lookup.
- Scoped other direct resource flows: spirit-field steal/visit, divine-punishment PvP drops, VIP carry teleport targets, guild kick target lookup, account-switching UID command entrypoints, and admin item transfer.
- Added auto-migration fields/indexes for `red_envelope.server_id` and `invite_reward.server_id`.

### Testing

- [OK] `python -m compileall plugins/xiuxian_game`
- [OK] `git diff --check`
- [OK] `python -m pytest tests/test_attribute_calculator_simple.py` (4 passed)
- [WARN] SQLite auto-migration smoke could not run in this environment because importing the plugin loads the configured MySQL engine and `aiomysql` is missing.

### Status

[WIP] **Shard isolation audit improved**

Not full production-ready yet. The high-risk player-driven resource transfer paths found in this pass have been patched, but a database-copy migration run and manual cross-server smoke test are still required before opening a new shard.

### Remaining Notes

- New-server UID restart is possible but is a separate migration: `player.uid` is still globally unique. Restarting UID per shard requires changing the unique constraint to `(server_id, uid)` and ensuring every UID command resolves within a server.
- Remaining unscoped UID lookups are mostly admin/monthly-card/help/message-board/ban paths. They are not normal player resource-transfer paths, but they should be scoped before implementing per-shard UID restart.


## Session 2: Record multi-server shard rollout

**Date**: 2026-05-16
**Task**: Record multi-server shard rollout
**Branch**: `main`

### Summary

Committed multi-server shard isolation code, kept server 2 registration closed by default, and prepared workflow records for deployment.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `bfdd7644` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
