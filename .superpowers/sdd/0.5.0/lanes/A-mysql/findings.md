# Lane A-mysql findings

Implementer: agy-flavio, Gemini 3.8

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/fastapi/test_mysql_api.py::test_report_golden_parity | 0637bf5965d2f0ae18a081749f338829413b771b | `mysql/captured.json parity: localOnly: missing from payload; ...` | Fixed in next commit |

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|

## Rule mutations (each new rule removed in place, the named test run, the file restored with git checkout)

| Rule | File | Mutation | Failing test |
|---|---|---|---|
