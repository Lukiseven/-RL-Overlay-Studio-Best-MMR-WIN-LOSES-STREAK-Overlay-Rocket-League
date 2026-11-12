# RL Overlay Studio — Beta 8.49 (Public Audit Notes)

This file documents the public-safe changes represented by the Beta 8.49 Standard audit snapshot.

## Beta 8.47

- Added a local MMR fallback when the protected primary MMR service is unavailable.
- The public audit intentionally omits the Launch.log acquisition/conversion implementation and protected MMR pipeline details.

## Beta 8.48

- Added the automatic stream visibility guard.
- Private matches and tournaments temporarily hide OBS/TikTok Browser Sources.
- Direct In-Game overlays are dimmed in restricted match contexts.
- Stream outputs hide when Rocket League is closed or loses foreground focus and restore automatically when the game becomes active again.

## Beta 8.49

- `PlaylistID 53` is treated as Honor Duel / Grudge Match.
- Honor Duel matches are **NO-STATS**: no Win, Loss, Streak or session-stat modification.
- The match remains technically detectable without being reclassified as a tournament or private match.

## Security / redactions

The public repository does not publish production API keys, private MMR endpoints, Discord IDs/tokens, VPS details, proprietary MMR/rank thresholds, embedded overlay templates, protected assets, signing/protection tooling or other production secrets.
