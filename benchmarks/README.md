# C++ to QML asynchronous result benchmark

This standalone benchmark measures the existing QmlPromise header without modifying it.
It uses actual QML code in a QQmlEngine and runs without a display server.

## Reproduce

From the repository root:

```sh
cmake -S benchmarks -B /tmp/qmlpromise-benchmark -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/qmlpromise-benchmark
/tmp/qmlpromise-benchmark/bench_qml_promise > benchmarks/results.csv
/tmp/qmlpromise-benchmark/bench_qml_promise --micro > benchmarks/components.csv
python3 benchmarks/summarize.py
```

`results.csv` and `components.csv` contain the latest measurements with explicit polyfill
installation. `*-cached-auto.csv` preserves the intermediate cached implementation that
still checked for the polyfill during conversion. The corresponding
`*-before.csv` files preserve the original measurements from the preceding run with the
header at commit `9054f526d7d3de2cff136e0bc75ca917f3b2b74a`.
These files contain recorded measurements, not performance thresholds. Benchmark workloads
and timing methodology are unchanged; installer calls were renamed with the public API.

## Methods

All methods start with QML calling a C++ invokable and end in the same QML result handler:

- `queued_signal`: queue an invocation to the backend's thread, emit a signal connected
  to the QML handler. No future observer or JavaScript promise. In the worker workload,
  a QtConcurrent job queues this delivery.
- `watcher_signal`: create a QFutureWatcher per request and emit the result signal on completion.
- `watcher_callback`: create a QFutureWatcher per request and call a QJSValue callback on completion.
- `continuation_signal`: use QFuture::then(context, ...) to emit the result signal.
- `qmlpromise`: use QmlPromise::fromFuture and attach the QML handler with .then().

Three workloads isolate different costs:

- `ready`: a completed integer future. The queued-signal baseline simply queues its integer.
- `pending`: a QPromise completed on the next event-loop turn. The baseline is the same
  queued signal as in `ready`, so it avoids promise/future allocation and watcher events.
- `worker`: a QtConcurrent job on a dedicated four-thread pool returns an integer.
  This includes scheduling but intentionally performs no expensive computation or sleep.

Batch 1 measures one request at a time. Batch 64 measures throughput by submitting up to
64 requests before draining the event loop. A ready continuation may execute synchronously;
it is not forced to match native Promise asynchronous semantics. These approaches also
have different cancellation, error, composition, and lifetime semantics. The alternatives
implement only successful result delivery, not all QmlPromise behavior.

Each scenario has a warm-up sample and seven recorded samples. Each recorded sample
contains 256 operations for batch 1 or 2,048 for batch 64. Method order is shuffled with
a fixed seed. QML validates the count, sum, and absence of duplicate values for every batch.

`setup_us_per_op` measures the QML submission call: invocations, future creation/scheduling,
observer or promise setup, and handler attachment. Synchronously executed continuations
also deliver their result during this interval.

`total_us_per_op` measures elapsed time divided by operations, including submission,
event-loop pumping, QML handling/validation, deferred deletion, waiting for workers to
return, and a final garbage collection. Natural automatic GC is also included. An initial
GC occurs outside the timed sample. Batch 64 totals are **amortized elapsed time**, not
individual request latency. Batch 1 includes harness/event-loop overhead; neither metric
is an isolated CPU-cycle measurement of the library. No GUI rendering is involved.

`--micro` separately compares an explicit idempotent installer call, the current resolver
factory (which no longer checks the polyfill), and a small equivalent resolver factory evaluated
once and called repeatedly. It drains events every 64 operations and reports loop time
and time including final GC. This cached function is a diagnostic experiment, not a
replacement library implementation. These standalone C++ calls have a different execution
context from QML-initiated requests; their costs must not be added to or subtracted from
the end-to-end benchmark. First-use engine startup and cold polyfill installation are excluded.

## Recorded environment and results

Measured on 2026-10-04: AMD Ryzen 7 3800X, Linux x86-64, Qt 6.11.2,
GCC 16.2.1, CMake Release build. CPU frequency and affinity were not locked.
Results describe this machine and Qt version, not a guarantee for other platforms.

### Explicit `.finally()` installation (current API)

Call `QmlPromise::installFinallyPolyfill(&engine)` during engine setup if `.finally()`
support is needed and not provided natively. Conversions never check or install it.
`.then()`, `.catch()`, and `Promise.all()` require no registration. The installer remains
idempotent and leaves an existing native implementation untouched.

The same benchmark rerun measured these median elapsed costs:

| QmlPromise scenario | Cached with automatic check (µs/op) | Explicit setup (µs/op) |
|---|---:|---:|
| Ready, batch 64 | 10.78 | 9.81 |
| Pending, batch 64 | 11.46 | 10.96 |
| Worker, batch 64 | 13.95 | 13.96 |
| Worker, batch 1 | 20.21 | 18.87 |

The smaller change is consistent with removing a sub-microsecond check. Worker scheduling
noise obscures it in the batched worker result; this is not evidence of an improvement
in every scenario. Pending submission measured 6.06 µs/op, about 0.39 ms for 64 requests.
The isolated resolver factory measured 1.40 µs/op, down from 1.74 µs/op with the check.

All 24 tests passed, including successful conversion/composition/error handling while
`.finally()` is absent and explicit repair after deleting it. The renamed demo built
and started offscreen. The benchmark validated another 241,920 recorded deliveries.
The sanitizer results below belong to the preceding cached implementation.

### Factory caching with automatic checks (previous measurements)

The implementation now caches a callable resolver factory in a QJSValue held by an
engine-owned QObject dynamic property. It checks for an existing `.finally()` directly
through QJSValue properties, evaluating the polyfill only when needed. This preserves
explicit and automatic repair if application code deletes `.finally()`. The factory
still creates a fresh promise and separate resolvers on every call. No process-wide
cache, JavaScript global cache property, moc requirement, or new dependency was added.

Median elapsed microseconds per operation, including cleanup:

| QmlPromise scenario | Before | After | Speedup |
|---|---:|---:|---:|
| Ready, batch 64 | 271.20 | 10.78 | 25.2× |
| Pending, batch 64 | 266.02 | 11.46 | 23.2× |
| Worker, batch 64 | 282.12 | 13.95 | 20.2× |
| Worker, batch 1 | 274.30 | 20.21 | 13.6× |

The concurrently remeasured alternatives remained much closer to their original timings:

| Method | Ready, batch 64 | Pending, batch 64 | Worker, batch 64 | Worker, batch 1 |
|---|---:|---:|---:|---:|
| Queued signal | 1.91 | 1.92 | 4.95 | 12.07 |
| Future continuation → signal | 2.75 | 3.89 | 7.35 | 15.45 |
| Future watcher → signal | 5.89 | 6.85 | 9.06 | 18.16 |
| Future watcher → JS callback | 6.35 | 7.29 | 9.28 | 18.91 |
| QmlPromise → .then() | 10.78 | 11.46 | 13.95 | 20.21 |

Compared with watcher-to-signal delivery, the optimized bridge adds about 4.6–4.9 µs/op
in the batched pending/worker tests, roughly 1.5–1.7 times the total time. Pending-result
throughput increased from about 3,759 to 87,243 operations/second in this harness.
Submission cost fell from 258.71 to 6.58 µs/op, so submitting 64 pending requests now takes
about 0.42 ms rather than 16.6 ms. These are warm-cache results; each engine's first use
still evaluates the factory and may install the polyfill.

The standalone polyfill check fell from 158.00 to 0.41 µs/op, and actual resolver factory
creation from 249.09 to 1.74 µs/op (including final GC). The complete bridge costs more
because it also observes the future, attaches and delivers the JavaScript handler, and
performs cleanup and benchmark validation.

All 23 Qt Test cases passed, including new coverage for garbage collection between
conversions, independent engines and engine recreation, and polyfill repair with a warm
factory cache. Existing teardown, cancellation, exception, and promise-composition tests
also passed. The new benchmark run validated 241,920 recorded result deliveries.
The suite also passed with AddressSanitizer and UndefinedBehaviorSanitizer enabled.
LeakSanitizer could not run in this environment (it reported a ptrace incompatibility),
so the sanitizer rerun disabled leak detection; no leak-check result is claimed.

### Original baseline

Median elapsed microseconds per operation, including cleanup:

| Method | Ready, batch 64 | Pending, batch 64 | Worker, batch 64 | Worker, batch 1 |
|---|---:|---:|---:|---:|
| Queued signal | 2.02 | 1.99 | 4.38 | 12.16 |
| Future continuation → signal | 2.86 | 3.92 | 7.29 | 15.88 |
| Future watcher → signal | 6.01 | 6.96 | 9.01 | 17.31 |
| Future watcher → JS callback | 6.28 | 7.06 | 9.48 | 18.50 |
| QmlPromise → .then() | 271.20 | 266.02 | 282.12 | 274.30 |

For pending results, QmlPromise took about 38 times the elapsed time of watcher-to-signal
delivery, an additional 259 µs per operation. For worker jobs in batches, the difference
was about 31 times, or 273 µs per operation. These ratios compare small transport costs,
not application speed or total duration of a real background task.

The pending QmlPromise submission alone took 259 µs/op: almost all of the measured time
occurs while creating the bridge and attaching .then(), on the engine thread. Submitting
64 such requests in one QML call took roughly 16.6 ms before returning to the event loop.
This can matter for animation even though the eventual background work is asynchronous.

An extra 0.26 ms is approximately 0.26% of a 100 ms operation, but 26% of a 1 ms operation.
Those percentages are arithmetic illustrations, not measured application workloads.
For occasional network/file operations this overhead may be acceptable; for frequent
short tasks or large bursts, prefer the lighter alternatives or optimize setup first.

The obvious optimization target is repeated JavaScript evaluation: install/check the
polyfill once per engine and cache a callable resolver factory per engine. The standalone
component experiment measured the following medians, including final GC:

| Standalone component | µs/op |
|---|---:|
| Existing-polyfill check via evaluate | 158.00 |
| Current resolver factory, including that check | 249.09 |
| Cached resolver factory call | 1.02 |

This demonstrates that a cached factory can be much cheaper, but does
not establish the performance of a complete optimized bridge. Any implementation must
preserve engine ownership/thread affinity and be tested for teardown and multiple engines.

No memory allocation counts, peak memory, error/cancellation paths, large payloads,
Q_PROPERTY bindings, or UI frame times were measured. Runtime-loaded benchmark QML also
does not model every application built with ahead-of-time QML compilation.

## Qt documentation consulted through Qt Docs MCP

- [QFuture::then(QObject *, ...)](https://doc.qt.io/qt-6/qfuture.html#then-1)
  documents context-thread dispatch and immediate handling of ready futures.
- [QFutureWatcher::setFuture](https://doc.qt.io/qt-6/qfuturewatcher.html#setFuture)
  documents delivery of existing future state and connecting before observation.
- [QJSEngine::evaluate](https://doc.qt.io/qt-6/qjsengine.html#evaluate)
  documents evaluation of source strings in the engine.
- [QML signal handling](https://doc.qt.io/qt-6/qtqml-syntax-signals.html)
  documents connecting signals to JavaScript handlers.
