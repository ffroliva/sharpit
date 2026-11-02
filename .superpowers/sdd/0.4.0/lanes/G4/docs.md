# Lane G4: Out-of-scope documentation references

The following files contain stale "not on PyPI" references but are outside lane G4's May-touch list. They are flagged here for the final integration step:

1. `website/docs/installation.md:3`:
   ```markdown
   sharpit is not on PyPI yet. Install it from git:
   ```
   *Action for integration:* Update installation instructions to reference published PyPI package `pip install "sharpit[fastapi]"`.

2. `skills/sharpit/SKILL.md:25`:
   ```bash
   # from a local checkout (no PyPI release yet)
   ```
   *Action for integration:* Update skill installation section to reference published PyPI package rather than checkout-only.
