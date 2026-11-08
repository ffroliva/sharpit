# Spike: Unbounded Reads Beyond Paged Routes (sharpit 0.5.0, Lane T-unbounded-read-2)

- **Date:** 2026-11-03
- **Branch:** `spike/0.5.0-unbounded-read-2`
- **Target Lane:** `T-unbounded-read-2` (Task 0)
- **Time Box:** 2 hours
- **Machine State:** Loaded by concurrent agents (all timings marked "loaded", medians reported over 5 runs with min/max spread)

---

## 1. Frame

- **Question:** How should sharpit measure returned item counts on non-paged routes to detect unbounded reads (where entities loaded ≫ items returned; bench defects D09–D11, D16, D18):
  - **(a)** From the endpoint response model before serialization (FastAPI route wrapper reading return value length)?
  - **(b)** By scanning body bytes for top-level commas in ASGI middleware (`capture_send`)?
  - Does either method respect the capture overhead budget (`BUDGET_MS = 0.2` ms / 200 µs)?
- **Why it matters:** Determines whether Lane `T-unbounded-read-2` proceeds to implementation (Task 1–3) or closes with a documented gap in spec §14.
- **Done when:** Empirical overhead measurements across payload sizes (0 to 10,000 items) for both methods, edge-case behavior documented, and a definitive verdict with build inputs produced.

---

## 2. Executive Verdict

### **Verdict: GO-WITH-CONDITIONS (Method (a) Chosen; Method (b) Rejected)**

- **Method (a) (Route Wrapper):** **GO.** Adds only **0.34 µs (sync)** / **0.47 µs (async)** per request (<0.25% of the 200 µs budget). Scales **O(1)** regardless of payload size (40 ns on 10,000 items). Accurately captures list lengths for standard FastAPI endpoints and separates unbounded reads (D09/D10) from legitimate bulk exports.
- **Method (b) (Byte Scanner):** **NO-GO.** Catastrophic overhead scaling with response size. At 10 items (1.8 KB), it already breaches the 200 µs budget (223.57 µs). At 100 items (18.7 KB), scanning takes 1.53 ms (7.7x budget). At 10,000 items (1.93 MB, D09/export scale), scanning takes **210.47 ms (1,052x budget)**. Even stdlib C-based `json.loads` takes 32.37 ms on 10,000 items (161x budget). Naive `bytes.count(b',')` is both invalid (counts commas in strings and nested objects) and exceeds the budget (473.6 µs).
- **Conditions for Build:**
  1. **Defensive Route Wrapping:** Wrap routes at `install()` and hook `APIRouter.add_api_route` plus re-scan on `on_startup` and `on_first_request` (defensive against `_IncludedRouter` in FastAPI 0.162+).
  2. **Strict Limitations (Review Focus #3):** Non-list return values, direct `Response`/`JSONResponse` objects, and streaming responses (`StreamingResponse`, generators) must NOT be parsed or scanned; they record `item_count = None` with an explicit limitation reason.
  3. **Export Protection (Review Focus #2):** Rule in `gates.py` requires `loaded >= min_loaded` (default 50) AND `loaded >= (returned * factor)` (default factor 2). When `returned` is large (export endpoints returning 10,000 items), ratio is 1.0x and no finding is emitted.
  4. **Quiet-Window Re-measure:** The 0.2 ms budget test must be confirmed in a quiet window without concurrent agent contention (contention added 10–30 µs noise during this spike).

---

## 3. The Five Key Numbers

1. **210.47 ms (1,052x budget):** Median time for Method (b) byte scanning on a 10,000-item array (1.93 MB), completely disqualifying byte scanning in request middleware.
2. **1.53 ms (7.7x budget):** Median time for Method (b) byte scanning on just 100 items (18.7 KB), breaching the 200 µs budget by nearly an order of magnitude.
3. **0.47 µs (<0.25% budget):** Median per-request overhead of Method (a) async route wrapper, scaling O(1) irrespective of response payload size.
4. **175.75 µs vs 223.57 µs:** Paired on/off capture overhead on `list(10)`: Method (a) captures comfortably within the 200 µs budget (175.75 µs, +3.93 µs over baseline), whereas Method (b) breaches the budget (223.57 µs).
5. **1,000x vs 1.0x:** Rule discrimination ratio between defect D09 (10,000 loaded vs 10 returned = 1,000x ratio) and legitimate bulk export (10,000 loaded vs 10,000 returned = 1.0x ratio), ensuring zero false positives on export endpoints.

---

## 4. Question 1: Method (b) Body Byte Scanning in Middleware

### Method
Implemented pure Python byte state machine `scan_top_level_commas_py` tracking bracket depth, double-quoted strings, and escape sequences `\"`. Evaluated in `CaptureMiddleware.capture_send` when `content-type: application/json` is returned. Compared against stdlib `json.loads` and C `bytes.count(b',')`.

### Standalone Scanning Timings (5 runs, loaded machine)

| Payload Items | Payload Size | Method | Median (µs) | Min (µs) | Max (µs) | Spread (µs) | Overhead Budget Status (200 µs) |
|---|---|---|---|---|---|---|---|
| **0 (empty array)** | 2 B | State Machine (B1) | 0.18 | 0.18 | 0.29 | 0.11 | OK |
| 0 (empty array) | 2 B | `json.loads` (B2) | 1.51 | 1.51 | 1.96 | 0.45 | OK |
| **10 items** | 1.84 KB | State Machine (B1) | 175.01 | 157.20 | 180.96 | 23.76 | High (~88% of budget) |
| 10 items | 1.84 KB | `json.loads` (B2) | 17.50 | 15.32 | 23.75 | 8.43 | OK |
| **100 items** | 18.72 KB | State Machine (B1) | **1,534.03** | 1,432.61 | 1,596.42 | 163.82 | **VIOLATION (7.7x budget)** |
| 100 items | 18.72 KB | `json.loads` (B2) | **197.86** | 139.39 | 259.99 | 120.60 | **VIOLATION (at budget cap)** |
| **1,000 items** | 190.17 KB | State Machine (B1) | **15,743.08** | 14,535.04 | 20,925.77 | 6,390.74 | **VIOLATION (78.7x budget)** |
| 1,000 items | 190.17 KB | `json.loads` (B2) | **2,452.36** | 2,396.05 | 5,091.63 | 2,695.58 | **VIOLATION (12.3x budget)** |
| **10,000 items** | 1.93 MB | State Machine (B1) | **210,470.28** | 203,015.20 | 215,214.04 | 12,198.84 | **VIOLATION (1,052x budget)** |
| 10,000 items | 1.93 MB | `json.loads` (B2) | **32,369.26** | 29,136.36 | 35,352.88 | 6,216.52 | **VIOLATION (161x budget)** |
| **Non-array object** | 49 B | State Machine (B1) | 0.15 | 0.15 | 0.19 | 0.05 | OK (early exit) |
| Non-array object | 49 B | `json.loads` (B2) | 3.39 | 3.37 | 3.77 | 0.40 | OK |

### Answer
**Method (b) is completely unviable.**
1. Scanning scales $O(N)$ with response byte length. For 100 items, scanning in Python takes 1.53 ms. For 10,000 items (standard export or batch load), scanning takes 210 ms.
2. `json.loads` in C is faster than Python loops but deserializes the entire object tree back into memory, taking 32.4 ms on 10,000 items (161x budget) and consuming massive heap memory.
3. Naive byte counting `bytes.count(b',')` takes 473.6 µs on 10,000 items (still over budget) and yields incorrect results because commas frequently appear inside strings and nested objects.

---

## 5. Question 2: Method (a) Route Wrapper Reading Model Length

### Method
Inspects `route.endpoint` and `route.dependant.call` on registered `APIRoute`s. Wraps the endpoint to inspect the returned Python object before FastAPI's serialization pipeline runs. If `isinstance(res, (list, tuple))`, records `len(res)` into the current `REQUEST` context.

### Microbenchmark Timings (50,000 iterations x 5 runs, loaded machine)

| Endpoint Type | State | Median Time (ns) | Min (ns) | Max (ns) | Net Wrapper Overhead (ns) | Net Overhead (µs) |
|---|---|---|---|---|---|---|
| **Sync Endpoint** | Unwrapped | 126.3 | 121.1 | 139.9 | — | — |
| Sync Endpoint | Wrapped | 467.9 | 458.6 | 583.0 | **+341.6 ns** | **0.342 µs** |
| **Async Endpoint** | Unwrapped | 253.9 | 226.4 | 262.4 | — | — |
| Async Endpoint | Wrapped | 721.3 | 598.3 | 802.9 | **+467.4 ns** | **0.467 µs** |

*Note: `len(res)` is an O(1) integer attribute read in CPython, requiring ~30–50 ns regardless of whether the list has 10 or 10,000 items.*

---

## 6. Paired Capture Overhead Benchmark (Against 0.20 ms Budget)

Tested using the repository's `tests/overhead.py` paired alternating harness (5 rounds of 1,000 requests each; 500 requests for 100 items).

| Scenario | Capture State | Method | Overhead (µs) | Noise (µs) | Off Median (µs) | On Median (µs) | Verdict |
|---|---|---|---|---|---|---|---|
| `/bare` (PlainText) | Baseline | None | 153.73 | 12.42 | 84.66 | 246.96 | OK (< 200 µs) |
| `/bare` (PlainText) | With item count | **Method (a)** | **173.47** | 11.31 | 88.73 | 264.83 | **OK (< 200 µs)** |
| `/bare` (PlainText) | With item count | Method (b) | 162.39 | 25.46 | 91.39 | 273.11 | OK (skipped by header) |
| `/items` (10 items) | Baseline | None | 171.82 | 12.90 | 116.13 | 297.16 | OK (< 200 µs) |
| `/items` (10 items) | With item count | **Method (a)** | **175.75** | 9.31 | 120.79 | 301.83 | **OK (< 200 µs)** |
| `/items` (10 items) | With item count | Method (b) | **223.57** | 9.45 | 121.86 | 351.04 | **OVER BUDGET** |
| `/items` (100 items) | Baseline | None | 158.16 | 19.11 | 193.60 | 367.69 | OK (< 200 µs) |
| `/items` (100 items) | With item count | **Method (a)** | **149.37** | 15.24 | 181.79 | 334.96 | **OK (< 200 µs)** |
| `/items` (100 items) | With item count | Method (b) | **587.60** | 33.59 | 193.40 | 788.80 | **CATASTROPHIC (2.94x budget)** |

### Answer
- **Method (a)** respects the 0.20 ms overhead budget across all payload sizes. On `list(10)`, Method (a) overhead is **175.75 µs**, adding less than **4 µs** over baseline capture.
- **Method (b)** fails the overhead budget immediately once a JSON array response is returned (223.57 µs on 10 items, 587.60 µs on 100 items).

---

## 7. Edge Cases & Review Focus Analysis

### Review Focus 1: Capture middleware cost stays inside existing budget
- Preserved without raising `BUDGET_MS = 0.2`.
- Method (a) wrapper adds less than half a microsecond of compute.

### Review Focus 2: Large export route false positives
- **Rule Formulation:**
  $$\text{Flagged if: } \text{entities\_loaded} \ge \text{min\_loaded} \quad \text{AND} \quad \text{entities\_loaded} \ge (\text{items\_returned} \times \text{factor})$$
- **Simulation against scenarios:**

| Scenario | Entities Loaded | Items Returned | Ratio | Status (`min_loaded=50`, `factor=2`) |
|---|---|---|---|---|
| **D09 (slice 10,000 -> 10)** | 10,000 | 10 | 1,000x | **FLAGGED (Defect caught)** |
| **D10 (python filter 1,000 -> 5)** | 1,000 | 5 | 200x | **FLAGGED (Defect caught)** |
| **D11 (len of all 1,000 -> 1 count)** | 1,000 | 1 | 1,000x | **FLAGGED (Defect caught)** |
| **D16 (python paging 500 -> 20)** | 500 | 20 | 25x | **FLAGGED (Defect caught)** |
| **D18 (python search 200 -> 4)** | 200 | 4 | 50x | **FLAGGED (Defect caught)** |
| **Export route (10,000 -> 10,000)** | 10,000 | 10,000 | 1.0x | **NOT FLAGGED (Protected)** |
| **Export route (500 -> 500)** | 500 | 500 | 1.0x | **NOT FLAGGED (Protected)** |
| **Single item lookup (2 -> 1)** | 2 | 1 | 2.0x | **NOT FLAGGED (loaded < 50)** |
| **Small collection (15 -> 15)** | 15 | 15 | 1.0x | **NOT FLAGGED (loaded < 50)** |
| **Small list with 2 filtered (10 -> 8)** | 10 | 8 | 1.25x | **NOT FLAGGED (loaded < 50)** |

### Review Focus 3: Streaming or non-JSON responses skipped with limitations
- When the endpoint returns a `StreamingResponse` or generator: Method (a) sees non-list return value; `CaptureMiddleware` sees `more_body=True`. No parsing is attempted. `item_count` is set to `None` with `item_count_limitation="streaming_response"`.
- When the endpoint directly returns a `JSONResponse` or `Response`: Method (a) sees `isinstance(res, Response)`. `item_count` is set to `None` with `item_count_limitation="direct_response"`.
- Non-JSON responses (HTML, plain text): `item_count = None`.

---

## 8. Inputs for Later Build Tasks (Tasks 1–3)

### 1. Configuration & Defaults
In `src/sharpit/settings.py` and `src/sharpit/engine/testsession/gates.py`:
- `activity_unbounded_read_factor: int = 2` (already present from `T-unbounded-read`)
- `activity_unbounded_read_min_loaded: int = 50` (new default threshold to suppress false positives on small lists)

### 2. Implementation Architecture for Task 1
- **Route Wrapping Site:** `src/sharpit/fastapi/capture.py` (inside `CaptureWiring`).
  - At `attach_at_install()`: scan `app.routes` and wrap `APIRoute.endpoint` + `APIRoute.dependant.call`.
  - Hook `router.add_api_route` to catch routes registered after `install(app)`.
  - In `on_startup()` and `on_first_request()`: re-scan defensively.
  - Traverse `_IncludedRouter` recursively for FastAPI 0.162+ compatibility.
- **Context Storage:** In `src/sharpit/engine/capture/correlation.py`:
  - Add `response_item_count: int | None = None` and `item_count_limitation: str | None = None` to `RequestInfo`.
- **Budget Constant for Task 1:**
  - Create `tests/fastapi/test_capture_item_count_overhead.py` with `BUDGET_MS = 0.20` ms.

### 3. Implementation Architecture for Task 2
- In `src/sharpit/engine/testsession/facts.py`:
  - Add `items_returned: int | None` and `item_count_limitation: str | None` to the captured request facts.
- In `src/sharpit/engine/testsession/gates.py` (`_unbounded_read_findings`):
  - Extend to check non-paged routes where `fact.page_size is None`.
  - Condition: `fact.loaded >= budget.unbounded_read_min_loaded` AND `fact.loaded >= (fact.items_returned or 1) * budget.unbounded_read_factor`.
  - Message format: `{route} loaded {loaded} {entity} entities but returned {items_returned} items; masked statement: {statement}`.

### 4. Platform Matrix
- FastAPI: 0.100.0 through 0.162.0+ (defensive inspection of `APIRoute` and `_IncludedRouter`).
- Python: 3.12, 3.13, 3.14.
- Handlers: Sync (`def`) and async (`async def`) endpoints returning Pydantic models, dicts, or ORM entities in lists/tuples.

---

## 9. Quiet-Window Confirmation Requirement

During this spike, the machine was under load from concurrent agent executions.
- Baseline noise ranged from **9.3 µs to 33.6 µs**.
- While Method (a) comfortably passed the 200.0 µs budget under load (**175.75 µs** on `list(10)` and **149.37 µs** on `list(100)`), the paired overhead test for Task 1 should be re-measured in a quiet window prior to final PR approval to confirm the quiescent baseline margin.
