# Definition of done checklist (0.4.0 spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane (no route, no DTO) |
| 2. BootUI port citations | N/A — sharpit-only behaviour (pytest sink memo), nothing ported |
| 3. Safety, no side effects, masking | `tests/engine/testsession/test_sink.py` (`test_masked_fingerprint_memo_never_returns_an_unmasked_value`, `test_masked_fingerprint_memo_keys_on_masker_settings`) |
| 4. Optional dependency gatekeeper | N/A — stdlib `functools` only |
| 5. Overhead budget | `tests/engine/testsession/test_sink_overhead.py` (new budget, 30 µs per repeated statement) |
| 6. MCP read-only | N/A — no MCP tool added |
| 7. Svelte view | N/A — no UI change |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs; lane run in `.superpowers/sdd/0.5.0/lanes/P-sink-mask-memo/handoff.md` |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/P-sink-mask-memo/findings.md` (§Scratch suite, paired wall time) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/P-sink-mask-memo/handoff.md` |
