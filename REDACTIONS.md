# Redactions

The public audit copy is generated from the Beta 8.46 source and then sanitized before publication.

The sanitization removes or replaces:

1. Production credentials, tokens and private service endpoints.
2. Long internal account/server/role identifiers.
3. MMR/rank acquisition logic and backend request functions.
4. Rank/MMR/division lookup tables and thresholds.
5. Player identity-resolution code used by the private MMR pipeline.
6. Embedded overlay HTML/CSS/JS templates.
7. Raw application visual assets and font files.
8. Protection/signing tooling and private build material.

See `redactions_manifest.json` for the generated symbol list.

A redaction marker looks like:

```python
def protected_component(*args, **kwargs):
    """[PUBLIC AUDIT REDACTION] Proprietary MMR/API/ranking logic removed."""
    raise RuntimeError("This proprietary component is not included in the public audit source.")
```