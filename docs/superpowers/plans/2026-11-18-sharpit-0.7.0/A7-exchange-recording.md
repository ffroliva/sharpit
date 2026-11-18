# Lane A7: HTTP exchange recording never disrupts a response (BootUI 2.4.0 #1615)

## Goal

Ensure that HTTP exchange recording failures never disrupt, alter, or fail an application response in sharpit, matching the behaviour of BootUI 2.4.0 (#1615).

## Scenario mapping

The test scenarios from BootUI 2.4.0 (`BootUiHttpExchangesFilterTests`, `BootUiHttpExchangesWebFilterTests`, and `SpringHttpExchangeStreamingTest`) map to the FastAPI/Starlette ASGI capture path (`CaptureMiddleware` and `CaptureWiring` in `src/sharpit/fastapi/capture.py`) as follows:

| BootUI 2.4.0 test case | Sharpit capture scenario | Expected behaviour |
|---|---|---|
| `BootUiHttpExchangesFilterTests.skipsNullRequestHeaderNamesWithoutLosingValidHeaders` | Scope request header iteration with null header name | In ASGI 3.0, request headers in `scope["headers"]` are binary `bytes` pairs; null header names cannot occur in valid ASGI. Not applicable; recorded as an adapted deviation. |
| `BootUiHttpExchangesFilterTests.skipsNullResponseHeaderNamesWithoutLosingValidHeadersOrTheServedBody` | Response header iteration with null header name | In ASGI 3.0, response headers in `http.response.start` are binary `bytes` pairs; null header names cannot occur in valid ASGI. Not applicable; recorded as an adapted deviation. |
| `BootUiHttpExchangesFilterTests.metadataFailureDoesNotAlterACommittedResponse` | Metadata extraction (`exchange_row`, `_route_template`, or header processing) raises an exception on a committed response | Response status (e.g. 206) and body are served without alteration. The exchange is not stored. Only the exception class name is logged at `WARNING` level; the exception message and request query data are never logged. |
| `BootUiHttpExchangesFilterTests.repositoryFailureDoesNotAlterTheServedResponse` | Exchange buffer insertion (`buffer.add`) raises an exception on a served response | Response status (e.g. 201) and body are served without alteration. Only the exception class name is logged at `WARNING` level; the exception message is never logged. |
| `BootUiHttpExchangesFilterTests.preservesEveryApplicationExceptionEvenWhenRecordingAlsoFails` | Application endpoint raises an exception while exchange recording (`buffer.add` or metadata assembly) also raises | The application's original exception propagates out unaltered. Recording failures never mask, replace, or swallow application exceptions. When the buffer is operational, the exchange is recorded with status 500. |
| `BootUiHttpExchangesFilterTests.setupFailureStillInvokesTheApplicationExactlyOnce` | Pre-request capture setup before `self.app` invocation raises an exception | The application is invoked exactly once and completes normally. No exchange is recorded. A warning is logged with the exception class name. |
| `BootUiHttpExchangesWebFilterTests.callbackRegistrationFailureStillServesTheResponse` | Processing failure during response capture in `capture_send` | `CaptureMiddleware` logs a warning with the exception class name and forwards the message to `send`. Response status, headers, and body are delivered without disruption. |
| `SpringHttpExchangeStreamingTest.streamsTheFullPdfDespiteMalformedMetadataAndRepositoryFailures` | Endpoint serves a chunked `StreamingResponse` while metadata assembly or `buffer.add` raises | Client receives status 200, `Content-Type: application/pdf`, and the full stream body without truncation. No 500 error is dispatched; no sensitive exception messages are logged. |

## Tasks

- [ ] **Step 1:** Implement ported test cases in `tests/fastapi/test_capture_wiring.py` with `# ported:` citations for each scenario.
- [ ] **Step 2:** Run `scripts/dev/red_check.py` on the ported tests to evaluate behaviour on the untouched codebase.
- [ ] **Step 3:** Apply minimal fixes to `src/sharpit/fastapi/capture.py` or the exchange buffer if any test fails.
- [ ] **Step 4:** Record the adapted deviation row in `docs/reference/matrix-updates/a7-exchange-recording.tsv` for ASGI null header invariants.
- [ ] **Step 5:** Run repository gates (`tests/fastapi` with `-n 2`, ruff check, ruff format, pyright).
