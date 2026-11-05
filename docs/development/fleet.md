# Running the full suite on a sandbox fleet

`scripts/ci/fleet.py` runs the suite on up to 5 Docker cloud sandboxes (`sbx --cloud`), one `SHARPIT_SHARD=i/n` slice
per box, and prints one verdict. **CI remains the gate.** The fleet is the fast Linux check and the fallback.

## When

Once per ship, on the pushed commit you will merge. Never during work: during work run the affected tests.

## Setup

The `sbx` CLI, signed in. Nothing else: the repository is public, so boxes clone it with no token, and no local file
(`.env`, working tree) reaches a box.

## Run

```bash
git push                                   # boxes clone the pushed commit from GitHub
GODEBUG=tlsmlkem=0 MSYS_NO_PATHCONV=1 uv run python scripts/ci/fleet.py --sha HEAD --boxes 5 --out <dir> > <dir>/fleet.log 2>&1
```

Run it in the background and read `<dir>/fleet.log` when it exits. Never stop a live run with `kill` or `TaskStop`:
that strands the boxes. Ctrl+C and SIGTERM remove every box.

`--boxes` is 1 to 5 (5 boxes of 8 vCPU fill the account's 40-vCPU quota; a sixth is refused, exit 2).

| Exit | Meaning |
|---|---|
| 0 | green: every box ran its shard, pytest exited 0 |
| 1 | red: the log names the box; read `<dir>/box<k>/out/pytest.log` and `pytest.xml` |
| 2 | not runnable: the sha is not a pushed ref tip, or a bad box count |
| 3 | no verdict: no box ran its tests (credit, quota, outage). Use CI. Never retry in a loop; it is not a red run |

A box that dies, times out or returns nothing is red, never rerun. Each box returns `timeline.txt` (epoch and
`/proc/stat` at start, cloned, synced, tests_begin, tests_end), `pytest.log`, `pytest.xml`, `overhead.jsonl`. The log
ends with per-box wall, setup seconds, test seconds and CPU-seconds (user+nice+system+irq+softirq from `/proc/stat`,
steal reported apart): the CPU-seconds are the floor, divide by 40 vCPUs.

The clone is a full clone: a partial clone broke Kliper tests that read git history.

## Cost

Billed per second by box shape: 5 boxes of 8 vCPU / 16 GiB. At Kliper's rate (about $0.00015556 per box-second) a run
costs box-seconds x that rate. The CLI shows no balance; read it at agentic-platform.docker.com/usage.

## Fallback

CI. An exit 3 says nothing about the code.

## Recovery

A hard kill (Windows `TerminateProcess`) cannot clean up; the boxes then run until their 30-minute TTL and bill.

```bash
sbx --cloud ls                  # fleet-<sha>-<pid>-<k>of<n>
sbx --cloud rm -f <name>        # each one
```

The next run also removes every `fleet-*` box at its start. Afterwards confirm `sbx --cloud ls` shows none.

## Spend ledger

The run calls the machine-wide ledger of sharpit-bench (`sbx_ledger.py`, found through `SBX_LEDGER_DIR`) before it
creates a box and records each box's seconds after removing it (a box it could not remove is charged its full TTL). A
run the ledger refuses exits 2; do not work around it.
