# Release Verification — Beta 8.49

This repository contains a **sanitized public audit snapshot**, not the complete production build.

## Binary / release verification

Use the SHA-256 values shipped with the matching official GitHub Release assets for the distributed ZIP/EXE.
Do **not** reuse Beta 8.46 hashes for Beta 8.49.

## Public source verification

The integrity of the files published in this repository is recorded in `SOURCE_MANIFEST.sha256`.

### Windows PowerShell

```powershell
Get-FileHash .\path\to\file -Algorithm SHA256
```

### macOS / Linux

```bash
shasum -a 256 path/to/file
# or
sha256sum path/to/file
```

A matching hash verifies file identity/integrity. It does not by itself establish that software is safe; source review and security scanning remain complementary controls.
