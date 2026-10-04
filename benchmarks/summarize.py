#!/usr/bin/env python3
"""Print median and range of benchmark samples comparing QmlPromise to baseline async methods."""
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

directory = Path(__file__).resolve().parent
groups = defaultdict(list)
with (directory / "results.csv").open() as source:
    for row in csv.DictReader(source):
        groups[(row["workload"], int(row["batch"]), row["method"])].append(row)

print("| Workload | Batch | Method | Setup µs/op | Total µs/op, median [min–max] | Ops/s |")
print("|---|---:|---|---:|---:|---:|")
for (workload, batch, method), rows in sorted(groups.items()):
    setup = median(float(row["setup_us_per_op"]) for row in rows)
    total = [float(row["total_us_per_op"]) for row in rows]
    value = median(total)
    print(f"| {workload} | {batch} | {method} | {setup:.2f} | "
          f"{value:.2f} [{min(total):.2f}–{max(total):.2f}] | {1e6/value:,.0f} |")

groups.clear()
with (directory / "components.csv").open() as source:
    for row in csv.DictReader(source):
        groups[row["component"]].append(row)
print("\n| Component | Loop µs/op | Including final GC µs/op |")
print("|---|---:|---:|")
for component, rows in sorted(groups.items()):
    loop = median(float(row["loop_us_per_op"]) for row in rows)
    total = median(float(row["total_us_per_op"]) for row in rows)
    print(f"| {component} | {loop:.2f} | {total:.2f} |")

# Baseline comparison: QmlPromise vs alternative async mechanisms
medians = {}
with (directory / "results.csv").open() as source:
    raw = defaultdict(list)
    for row in csv.DictReader(source):
        raw[(row["workload"], int(row["batch"]), row["method"])].append(float(row["total_us_per_op"]))
    for key, values in raw.items():
        medians[key] = median(values)

print("\n### QmlPromise Overhead vs Baseline Async Mechanisms")
print("| Workload | Batch | QmlPromise µs | Watcher Callback µs | Overhead vs Callback | Raw Signal µs | Overhead vs Signal |")
print("|---|---:|---:|---:|---:|---:|---:|")
for (workload, batch) in sorted(set((w, b) for (w, b, m) in medians.keys())):
    qp = medians.get((workload, batch, "qmlpromise"), 0.0)
    cb = medians.get((workload, batch, "watcher_callback"), 0.0)
    sig = medians.get((workload, batch, "queued_signal"), 0.0)
    delta_cb = qp - cb
    delta_sig = qp - sig
    print(f"| {workload} | {batch} | {qp:.2f} | {cb:.2f} | +{delta_cb:.2f} µs ({qp/cb:.1f}×) | {sig:.2f} | +{delta_sig:.2f} µs ({qp/sig:.1f}×) |")
