# Security Policy

## Reporting a vulnerability

Please do not publish exploitable security issues, secrets, tokens, private endpoints or bypass techniques in a public GitHub Issue.

Preferred reporting path:

1. Use GitHub's private **Report a vulnerability / Security Advisory** feature when available.
2. If that feature is unavailable, contact the project team through the official RL Overlay Studio Discord and request a private security contact.

Please include:

- affected RL Overlay Studio version;
- Windows version;
- reproduction steps;
- logs/screenshots with personal data and tokens removed;
- expected vs actual behavior.

## Supported version

Security fixes target the latest published version. Older builds may no longer receive fixes.

## Public audit source

The `src/` tree is deliberately redacted and non-buildable. Do not treat missing proprietary components as a security defect; consult `AUDIT_SCOPE.md` first.