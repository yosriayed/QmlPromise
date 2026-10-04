#!/usr/bin/env python3
"""Print median and range of benchmark samples; only Python's standard library is needed."""
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

def bridge_medians(filename):
    samples = defaultdict(list)
    with (directory / filename).open() as source:
        for row in csv.DictReader(source):
            if row["method"] == "qmlpromise":
                samples[(row["workload"], int(row["batch"]))].append(float(row["total_us_per_op"]))
    return {key: median(values) for key, values in samples.items()}

before = bridge_medians("results-before.csv")
after = bridge_medians("results.csv")
print("\n| QmlPromise workload | Batch | Before µs/op | After µs/op | Speedup |")
print("|---|---:|---:|---:|---:|")
for (workload, batch), value in sorted(after.items()):
    original = before[(workload, batch)]
    print(f"| {workload} | {batch} | {original:.2f} | {value:.2f} | {original/value:.1f}× |")
