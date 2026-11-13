# Journal queue: deviation rows for the 0.6.0 spec §14

Fragment for `2026-11-09-sharpit-0.6.0-design.md` §14 (that file lives on `docs/0.6.0-symmetry`; the coordinator folds
these rows in). Source of the design: `briefs-0.6.0/predict-journal-queue.md` (GO-WITH-CONDITIONS), owner ruling
2026-11-13 "stack the measured wins". BootUI lines are `v2.3.0`, `bootui-engine/.../engine/journal/`.

| # | Row(s) | BootUI | sharpit | Status |
|---|---|---|---|---|
| D-JQ1 | journal drain | one dispatcher thread drains the queue (`RuntimeJournal.java:431-470`, batches of 512, :62) | no thread: a producer try-locks and moves at most `PRODUCER_BATCH` (16) events once `wakeAt` are queued (`JournalQueue.java:61`); every read drains all | DEFAULT TAKEN, owner may reverse |
| D-JQ2 | what a read sees | the ring only; queued events stay invisible until the dispatcher runs (:164) | a read drains first and sees every event offered before it; `queueDepth` is the live depth (:943), as BootUI's | DEFAULT TAKEN, owner may reverse |
| D-JQ3 | `recorded` | counted at offer, under the queue's lock (`JournalQueue.java:99-101`) | counted when the event enters the ring: Python `+=` is not atomic, so only the drain writes a counter; reads drain first, so `recorded == retainedEvents + evictedEvents` | forced by Python, DEFAULT TAKEN, owner may reverse |
| D-JQ4 | routine share | check and insert are atomic under the lock (`JournalQueue.java:85-113`, test `routineEventsNeverOvershootTheirShareUnderConcurrentOffers`) | check and append are two steps: a share can be overshot by at most one event per producer offering at that instant; same for the capacity | DEFAULT TAKEN, owner may reverse |
| D-JQ5 | free-threaded Python | n/a | NOT verified (no 3.13t/3.14t here): assumes `deque.append`/`popleft` are atomic per call; known limit | known limit |

Ported without deviation: the reserved queue share (`RuntimeJournalSettings.java:146-149`, `JournalQueue.java:95`, default
10 %, no property), a refusal counted under the event's source (`RuntimeJournal.java:337`), and a re-entrant offer being
queued (BootUI has no guard, :321-340). The journal no longer produces the `reentrant` dropped key; the log tail's own
guard still does.
