## sharpit report

- **Status:** fail
- **Mode:** gate
- **Tests:** 2
- **Queries:** 14
- **Findings:** 2

### Findings (showing 2 of 2)

| Severity | Rule | Target | Message | Baseline |
| --- | --- | --- | --- | --- |
| CRITICAL | max-queries | tests/test\_b.py::test\_y | 12 queries \| budget 10 | - |
| HIGH | n-plus-one | tests/test\_a.py::test\_1 | Repeated query \`SELECT 1\` | - |
