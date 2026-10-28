# Public Audit Scope — RL Overlay Studio Beta 8.46

This repository publishes a sanitized security-review copy of RL Overlay Studio.

## Purpose

The goal is to let users inspect the application's non-sensitive behavior, dependencies, local networking, file access, Windows integration, update flow and authentication structure without disclosing proprietary ranking infrastructure or credentials.

## Included

- Main Python application structure derived from Beta 8.46.
- PyQt6 window/control flow outside protected modules.
- Local StatsAPI client structure.
- Local HTTP/WebSocket infrastructure where it does not disclose protected backend logic.
- Windows process/window interaction.
- Configuration, session persistence, logging and diagnostics.
- Discord OAuth structure with secrets and IDs removed.
- GitHub update/release logic.
- Dependency manifest.

## Redacted / omitted

- MMR retrieval and private backend client implementation.
- Ranking/MMR/division thresholds and lookup tables.
- Private identity-resolution logic used for MMR requests.
- Production API keys, tokens, client secrets, Discord IDs and private endpoints.
- Original embedded overlay HTML/CSS/JS templates.
- Original app logos, icons, rank images, platform graphics and other PNG/JPG/SVG/ICO files.
- Original fonts and font bundle.
- Release protection/signing internals.
- Historical internal patch notes that disclose protected implementation details.

## Audit limitation

This tree is intentionally non-buildable. It cannot be used to reproduce the production executable and therefore cannot establish byte-for-byte equivalence with the distributed binary. It is a transparency/audit view of the exposed components, not a reproducible-source release.

All intentional code removals are marked `[PUBLIC AUDIT REDACTION]`.