# Profile header overlap fix — 26 October 2026

Deployed to https://trace.musfiqurtuhin.me/profile at 21:31 Asia/Dhaka.

The profile header previously placed the avatar, flexible account details, and participant-code/member-since cards in one wrapping flex row. The metadata could consume the available width and collapse the account-details column, causing text to overflow beneath the cards.

The header now uses a grid with an explicit shrinking text column. Below the extra-large breakpoint, the metadata occupies a separate full-width row. Long identity text and metadata can wrap; school icons keep their size. The display name is no longer truncated to an ellipsis. Wide layouts retain the metadata beside the account details.

Only the header block of production's `frontend/src/pages/Profile.jsx` was replaced. Other production source files and profile copy were retained. The existing expert-portal fixes are included in the production baseline and remain deployed. No dependency, backend, environment, or participant-data changes were made.

Validation: isolated production staging passed 112 existing regression tests, lint, and build. All 44 emitted JS/CSS assets matched staged bytes over public HTTPS with correct MIME types, the home/profile index matched the new build, and API database health remained OK. `verify-public.py` independently checks that the public profile bundle and stylesheet contain the new grid and text-wrapping rules.

Browser automation was unavailable, so a rendered screenshot comparison and interactive viewport checks were not performed.

Verified rollback backup: `/srv/trace-tutor/deployment-backups/profile-header-20261026-20094c27ce41`.

Staging: `/tmp/trace-profile-header-20261026-c8d420`. `publish.py` includes automatic rollback and is guarded against rerunning this release over later source changes.
