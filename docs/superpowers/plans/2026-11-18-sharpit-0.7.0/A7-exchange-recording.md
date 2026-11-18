# Lane A7: HTTP exchange recording never disrupts a response (BootUI 2.4.0 #1615)

## Goal

Ensure that HTTP exchange recording failures never disrupt, alter, or fail an application response in sharpit, matching the behaviour of BootUI 2.4.0 (#1615), and that no capture-setup failure invokes the application twice or lets a client-forged probe header reach the host.

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

### Every test method added by #1615

| BootUI 2.4.0 test method | Disposition |
|---|---|
| `BootUiHttpExchangesFilterTests.skipsNullRequestHeaderNamesWithoutLosingValidHeaders` | n-a: ASGI header names are `bytes`, never null |
| `BootUiHttpExchangesFilterTests.skipsNullResponseHeaderNamesWithoutLosingValidHeadersOrTheServedBody` | n-a: same |
| `BootUiHttpExchangesFilterTests.metadataFailureDoesNotAlterACommittedResponse` | ported (`test_metadata_failure_does_not_alter_a_committed_response`) |
| `BootUiHttpExchangesFilterTests.repositoryFailureDoesNotAlterTheServedResponse` | ported (`test_hook_failure_leaves_response`) |
| `BootUiHttpExchangesFilterTests.preservesEveryApplicationExceptionEvenWhenRecordingAlsoFails` | ported, with a metadata-failure leg |
| `BootUiHttpExchangesFilterTests.setupFailureStillInvokesTheApplicationExactlyOnce` | ported over each fallible setup step, plus sharpit's own routes |
| `BootUiHttpExchangesFilterTests.preservesActuatorsQuietSkipForAnUnrecordableRequestUrl` | n-a: Spring Actuator URL handling; an ASGI `path` is always a string |
| `BootUiHttpExchangesFilterTests.preservesIncludeRulesQueryEncodingAndSessionSemantics` | n-a: Spring include rules and session ids; sharpit has no include rules and records no session id |
| `BootUiHttpExchangesFilterTests.retainsInheritedAsyncAndErrorDispatchExclusion` | n-a: servlet ASYNC and ERROR dispatches do not exist in ASGI; one pass per request |
| `BootUiHttpExchangesWebFilterTests.skipsNullResponseHeaderNamesAndRecordsValidHeadersWithoutMutatingTheResponse` | n-a: null header names |
| `BootUiHttpExchangesWebFilterTests.skipsNullRequestHeaderNamesBeforeCaseInsensitiveNormalization` | n-a: null header names |
| `BootUiHttpExchangesWebFilterTests.metadataFailureDoesNotPreventResponseCommitment` | ported (the metadata test above) |
| `BootUiHttpExchangesWebFilterTests.repositoryFailureDoesNotPreventResponseCommitment` | ported (`test_hook_failure_leaves_response`) |
| `BootUiHttpExchangesWebFilterTests.preservesApplicationErrorsAndLetsTheErrorHandlerCommitDespiteARecordingFailure` | ported (`test_the_error_handler_commits_despite_a_recording_failure`) |
| `BootUiHttpExchangesWebFilterTests.doesNotSwallowSynchronousApplicationOrApplicationCommitFailures` | ported (`test_application_and_send_failures_propagate_unchanged`) |
| `BootUiHttpExchangesWebFilterTests.preparationFailuresStillInvokeTheApplicationExactlyOnce` | ported (the setup-failure test, one case per setup step) |
| `BootUiHttpExchangesWebFilterTests.callbackRegistrationFailureStillServesTheResponse` | ported, adapted: the response stamp fails once and the row is still recorded (deviation row) |
| `BootUiHttpExchangesWebFilterTests.preservesIncludeRulesRemoteAddressPrincipalAndStartedSession` | n-a: Spring include rules and session; remote address and principal are covered by the `exchange_row` tests |
| `SpringHttpExchangeStreamingTest.streamsTheFullPdfDespiteMalformedMetadataAndRepositoryFailures` | ported, without the null-header leg |
| `WebFluxHttpExchangeStreamingTest.streamsTheFullPdfDespiteARepositoryFailureDuringCommit` | ported as the repository leg of the streaming test |

## Tasks

- [x] **Step 1:** Implement ported test cases in `tests/fastapi/test_capture_wiring.py` with `# ported:` citations for each scenario.
- [x] **Step 2:** Run the tests on the untouched code. Three are red: an exception raised by one of sharpit's own routes invokes the application a second time, a setup failure lets a client-forged probe header reach the host, and an application exception raised after a setup failure carries the setup failure as its context. The other ported tests pass and stay as regression guards.
- [x] **Step 3:** Fix them in `src/sharpit/fastapi/capture.py`: the probe header is removed before any fallible step, only the setup steps sit inside the fail-open `try`, and the application is called once, outside it.
- [x] **Step 4:** Record the adapted deviation rows in `docs/reference/matrix-updates/a7-exchange-recording.tsv`.
- [ ] **Step 5:** Run the gates: `tests/fastapi` with `-n 2` (the machine is short on memory), the capture overhead budget tests alone with `-n 0` (a budget test must not share cores), ruff check, ruff format check and pyright.
