# Repository History Sanitization (260424)

## Summary

This session sanitized repository history after accidental commit of `.env.secrets` in the past.

## Actions Completed

1. Created a single squashed commit (`73bcee6`) representing the current project state.
2. Force-updated `cpar/master` to the squashed commit.
3. Deleted `cpar/feature/ritm`.
4. Force-updated `gitea/master` to the squashed commit.
5. Deleted `gitea/feature/ritm`.
6. Cleaned local branches to `master` only and hard-reset local `master` to `73bcee6`.
7. Azure cleanup was intentionally skipped due to branch policy restrictions.

## Current State

- Local:
  - `master` only
  - tip at `73bcee6`
- cpar:
  - `master` only
  - tip at `73bcee6`
- gitea:
  - `master` at `73bcee6`
  - `dev` still exists because it is configured as default branch
- azure:
  - still has old history (cleanup deferred)

## Remaining Manual Step

In Gitea UI, set default branch to `master`, then delete `dev`:

- URL: `http://gitea.ancf.win/anton/FPCR/settings/branches`
- Command after default-branch switch:
  - `git push gitea --delete dev`

## Notes

- Multiple SSH operations printed `C_GetSlotList failed: 48`; pushes still succeeded where policy allowed.
- Sensitive credential rotation remains recommended if not already done.
