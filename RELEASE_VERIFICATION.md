# Release Verification — Beta 8.46

Use SHA-256 to verify the release archive and executable.

## Official hashes used for this audit package

```text
Overlay_Studio_DoublePC_Beta_8.46_.zip
SHA256: fcced4298a0952b109b4e657c82aa1c79c911f9875a43cc7974e862731adb4f6

RL-Overlay-Studio.exe
SHA256: c7aaea996bbfafb9fe1c2aa11e2f8cd75a8a4557c7c847cc1dfc2418fb9f7e87
```

## Windows PowerShell

```powershell
Get-FileHash .\Overlay_Studio_DoublePC_Beta_8.46_.zip -Algorithm SHA256
Get-FileHash .\RL-Overlay-Studio.exe -Algorithm SHA256
```

## macOS / Linux

```bash
shasum -a 256 Overlay_Studio_DoublePC_Beta_8.46_.zip
sha256sum RL-Overlay-Studio.exe
```

A matching hash verifies file integrity/identity. It does not by itself establish that a program is safe; source review, code signing and security scanning are complementary controls.