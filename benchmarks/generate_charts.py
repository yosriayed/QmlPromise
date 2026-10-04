#!/usr/bin/env python3
"""Generate crisp, high-resolution SVG benchmark charts for QmlPromise.

Reads results.csv using Python's standard library and generates self-contained
SVG charts designed for direct embedding in GitHub README markdown.
"""

import csv
from collections import defaultdict
from pathlib import Path
from statistics import median
import sys


METHOD_CONFIG = [
    ("queued_signal", "Raw Signal", "#8b949e", "Minimal baseline (queued signal)"),
    ("continuation_signal", "Continuation Signal", "#58a6ff", "QFuture::then continuation"),
    ("watcher_signal", "Watcher Signal", "#d29922", "QFutureWatcher signal"),
    ("watcher_callback", "Watcher Callback", "#f0883e", "QFutureWatcher JS callback"),
    ("qmlpromise", "QmlPromise", "#3fb950", "Native ES6 Promise (.then)"),
]


def load_stats(filepath: Path):
    if not filepath.exists():
        return {}
    groups = defaultdict(list)
    with filepath.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["workload"], int(row["batch"]), row["method"])
            groups[key].append(float(row["total_us_per_op"]))
    return {k: median(v) for k, v in groups.items()}


def generate_latency_chart(stats: dict, output_path: Path):
    """Generates a grouped bar chart comparing latency across methods for Batch 64."""
    width = 850
    height = 420
    pad_left = 60
    pad_right = 30
    pad_top = 80
    pad_bottom = 60

    plot_width = width - pad_left - pad_right
    plot_height = height - pad_top - pad_bottom

    workloads = [
        ("ready", "Ready Future (Immediate)"),
        ("pending", "Pending Promise (Next Turn)"),
        ("worker", "Worker Threadpool (QtConcurrent)"),
    ]

    max_y = 16.0  # µs/op
    y_ticks = [0, 4, 8, 12, 16]

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">')
    svg.append('<style>')
    svg.append('  .bg { fill: #0d1117; stroke: #30363d; stroke-width: 1.5; rx: 10px; }')
    svg.append('  .grid { stroke: #21262d; stroke-width: 1; stroke-dasharray: 4,4; }')
    svg.append('  .axis { stroke: #30363d; stroke-width: 1.5; }')
    svg.append('  .title { fill: #f0f6fc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 16px; font-weight: 700; }')
    svg.append('  .subtitle { fill: #8b949e; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 12px; }')
    svg.append('  .label { fill: #8b949e; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 11px; }')
    svg.append('  .tick-text { fill: #8b949e; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; text-anchor: end; }')
    svg.append('  .group-title { fill: #f0f6fc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 12px; font-weight: 600; text-anchor: middle; }')
    svg.append('  .bar-val { fill: #f0f6fc; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 10px; font-weight: 600; text-anchor: middle; }')
    svg.append('  .bar-val-green { fill: #3fb950; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 10px; font-weight: 700; text-anchor: middle; }')
    svg.append('  .legend-text { fill: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 11px; }')
    svg.append('</style>')

    # Background card
    svg.append(f'<rect width="{width}" height="{height}" class="bg"/>')

    # Header
    svg.append(f'<text x="{pad_left}" y="32" class="title">C++ ➔ QML Asynchronous Delivery Latency (Batch 64)</text>')
    svg.append(f'<text x="{pad_left}" y="52" class="subtitle">Amortized microseconds per operation (Lower is better) &bull; Tested on Qt 6.8 / C++20</text>')

    # Legend at top right
    leg_x = width - pad_right - 480
    leg_y = 26
    for i, (m_key, m_label, m_color, _) in enumerate(METHOD_CONFIG):
        lx = leg_x + i * 98
        svg.append(f'<rect x="{lx}" y="{leg_y}" width="10" height="10" rx="2" fill="{m_color}"/>')
        svg.append(f'<text x="{lx + 14}" y="{leg_y + 9}" class="legend-text">{m_label}</text>')

    # Gridlines and Y-ticks
    for tick in y_ticks:
        y_pos = pad_top + plot_height - (tick / max_y) * plot_height
        svg.append(f'<line x1="{pad_left}" y1="{y_pos}" x2="{width - pad_right}" y2="{y_pos}" class="grid"/>')
        svg.append(f'<text x="{pad_left - 8}" y="{y_pos + 4}" class="tick-text">{tick} µs</text>')

    # X-Axis line
    y_zero = pad_top + plot_height
    svg.append(f'<line x1="{pad_left}" y1="{y_zero}" x2="{width - pad_right}" y2="{y_zero}" class="axis"/>')

    # Groups & Bars
    num_workloads = len(workloads)
    group_width = plot_width / num_workloads
    num_methods = len(METHOD_CONFIG)
    bar_width = 32
    group_bar_span = num_methods * bar_width + (num_methods - 1) * 4

    for g_idx, (w_key, w_name) in enumerate(workloads):
        group_center = pad_left + g_idx * group_width + group_width / 2
        start_x = group_center - group_bar_span / 2

        # Group label
        svg.append(f'<text x="{group_center}" y="{y_zero + 24}" class="group-title">{w_name}</text>')

        for m_idx, (m_key, m_label, m_color, _) in enumerate(METHOD_CONFIG):
            val = stats.get((w_key, 64, m_key), 0.0)
            bar_height = (val / max_y) * plot_height
            bar_x = start_x + m_idx * (bar_width + 4)
            bar_y = y_zero - bar_height

            is_qp = (m_key == "qmlpromise")
            stroke_attr = ' stroke="#2ea043" stroke-width="1.5"' if is_qp else ""
            rx = 3

            svg.append(f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_width}" height="{bar_height:.1f}" rx="{rx}" fill="{m_color}"{stroke_attr}/>')

            val_cls = "bar-val-green" if is_qp else "bar-val"
            svg.append(f'<text x="{bar_x + bar_width / 2:.1f}" y="{bar_y - 6:.1f}" class="{val_cls}">{val:.2f}</text>')

    svg.append('</svg>')
    output_path.write_text("\n".join(svg), encoding="utf-8")


def generate_overhead_chart(stats: dict, output_path: Path):
    """Generates an overhead comparison chart showing marginal overhead vs watcher callback."""
    width = 850
    height = 360
    pad_left = 60
    pad_right = 40
    pad_top = 80
    pad_bottom = 70

    plot_width = width - pad_left - pad_right
    plot_height = height - pad_top - pad_bottom

    scenarios = [
        ("ready", 64, "Ready (Batch 64)", "Completed future, amortized throughput"),
        ("pending", 64, "Pending (Batch 64)", "Next event loop turn, amortized throughput"),
        ("worker", 64, "Worker (Batch 64)", "QtConcurrent thread pool, amortized"),
        ("worker", 1, "Worker (Single B1)", "Individual request roundtrip in real threads"),
    ]

    max_y = 8.0  # µs delta
    y_ticks = [0, 2, 4, 6, 8]

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">')
    svg.append('<style>')
    svg.append('  .bg { fill: #0d1117; stroke: #30363d; stroke-width: 1.5; rx: 10px; }')
    svg.append('  .grid { stroke: #21262d; stroke-width: 1; stroke-dasharray: 4,4; }')
    svg.append('  .axis { stroke: #30363d; stroke-width: 1.5; }')
    svg.append('  .title { fill: #f0f6fc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 16px; font-weight: 700; }')
    svg.append('  .subtitle { fill: #8b949e; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 12px; }')
    svg.append('  .tick-text { fill: #8b949e; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; text-anchor: end; }')
    svg.append('  .col-title { fill: #f0f6fc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 13px; font-weight: 600; text-anchor: middle; }')
    svg.append('  .col-desc { fill: #8b949e; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 10px; text-anchor: middle; }')
    svg.append('  .delta-text { fill: #3fb950; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px; font-weight: 700; text-anchor: middle; }')
    svg.append('  .sub-note { fill: #8b949e; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 10px; text-anchor: middle; }')
    svg.append('</style>')

    # Background card
    svg.append(f'<rect width="{width}" height="{height}" class="bg"/>')

    # Header
    svg.append(f'<text x="{pad_left}" y="32" class="title">Marginal Overhead: QmlPromise vs QFutureWatcher Callback</text>')
    svg.append(f'<text x="{pad_left}" y="52" class="subtitle">Extra microseconds added by ES6 Promise abstraction compared to ad-hoc JS callback (Lower is better)</text>')

    # Y-axis ticks and gridlines
    for tick in y_ticks:
        y_pos = pad_top + plot_height - (tick / max_y) * plot_height
        svg.append(f'<line x1="{pad_left}" y1="{y_pos}" x2="{width - pad_right}" y2="{y_pos}" class="grid"/>')
        svg.append(f'<text x="{pad_left - 8}" y="{y_pos + 4}" class="tick-text">+{tick} µs</text>')

    y_zero = pad_top + plot_height
    svg.append(f'<line x1="{pad_left}" y1="{y_zero}" x2="{width - pad_right}" y2="{y_zero}" class="axis"/>')

    # Columns
    col_width = plot_width / len(scenarios)
    bar_width = 64

    for idx, (w_key, b_size, s_name, s_desc) in enumerate(scenarios):
        col_center = pad_left + idx * col_width + col_width / 2

        qp = stats.get((w_key, b_size, "qmlpromise"), 0.0)
        cb = stats.get((w_key, b_size, "watcher_callback"), 0.0)
        delta = max(0.0, qp - cb)

        bar_h = (delta / max_y) * plot_height
        bar_x = col_center - bar_width / 2
        bar_y = y_zero - bar_h

        # Bar
        svg.append(f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_width}" height="{bar_h:.1f}" rx="4" fill="#3fb950" stroke="#2ea043" stroke-width="1.5"/>')

        # Delta label
        svg.append(f'<text x="{col_center:.1f}" y="{bar_y - 10:.1f}" class="delta-text">+{delta:.2f} µs</text>')
        ratio = (qp / cb) if cb > 0 else 1.0
        svg.append(f'<text x="{col_center:.1f}" y="{bar_y - 26:.1f}" class="sub-note">({ratio:.1f}× callback time)</text>')

        # Labels below x axis
        svg.append(f'<text x="{col_center:.1f}" y="{y_zero + 22}" class="col-title">{s_name}</text>')
        svg.append(f'<text x="{col_center:.1f}" y="{y_zero + 38}" class="col-desc">{s_desc}</text>')

    svg.append('</svg>')
    output_path.write_text("\n".join(svg), encoding="utf-8")


def generate_throughput_chart(stats: dict, output_path: Path):
    """Generates a horizontal throughput chart in operations per second."""
    width = 850
    height = 300
    pad_left = 180
    pad_right = 80
    pad_top = 70
    pad_bottom = 40

    plot_width = width - pad_left - pad_right
    plot_height = height - pad_top - pad_bottom

    methods = [
        ("queued_signal", "Raw Queued Signal", "#8b949e"),
        ("continuation_signal", "Continuation Signal", "#58a6ff"),
        ("watcher_signal", "Watcher Signal", "#d29922"),
        ("watcher_callback", "Watcher Callback", "#f0883e"),
        ("qmlpromise", "QmlPromise", "#3fb950"),
    ]

    max_ops = 600000.0  # 600k ops/sec

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">')
    svg.append('<style>')
    svg.append('  .bg { fill: #0d1117; stroke: #30363d; stroke-width: 1.5; rx: 10px; }')
    svg.append('  .grid { stroke: #21262d; stroke-width: 1; stroke-dasharray: 4,4; }')
    svg.append('  .axis { stroke: #30363d; stroke-width: 1.5; }')
    svg.append('  .title { fill: #f0f6fc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 16px; font-weight: 700; }')
    svg.append('  .subtitle { fill: #8b949e; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 12px; }')
    svg.append('  .row-label { fill: #f0f6fc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 12px; font-weight: 600; text-anchor: end; }')
    svg.append('  .val-text { fill: #f0f6fc; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; font-weight: 600; }')
    svg.append('  .val-text-green { fill: #3fb950; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; font-weight: 700; }')
    svg.append('  .tick-text { fill: #8b949e; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; text-anchor: middle; }')
    svg.append('</style>')

    # Background card
    svg.append(f'<rect width="{width}" height="{height}" class="bg"/>')

    # Header
    svg.append(f'<text x="30" y="32" class="title">Peak Throughput Comparison (Ready Future, Batch 64)</text>')
    svg.append(f'<text x="30" y="52" class="subtitle">Operations delivered per second (Higher is better)</text>')

    # Vertical gridlines
    for tick in [0, 150000, 300000, 450000, 600000]:
        x_pos = pad_left + (tick / max_ops) * plot_width
        svg.append(f'<line x1="{x_pos}" y1="{pad_top}" x2="{x_pos}" y2="{pad_top + plot_height}" class="grid"/>')
        label = f"{int(tick/1000)}k" if tick > 0 else "0"
        svg.append(f'<text x="{x_pos}" y="{pad_top + plot_height + 20}" class="tick-text">{label}</text>')

    # Y-axis
    svg.append(f'<line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{pad_top + plot_height}" class="axis"/>')

    # Horizontal bars
    bar_height = 22
    row_pitch = plot_height / len(methods)

    for idx, (m_key, m_label, m_color) in enumerate(methods):
        val_us = stats.get(("ready", 64, m_key), 0.0)
        ops_sec = 1e6 / val_us if val_us > 0 else 0.0

        y_center = pad_top + idx * row_pitch + row_pitch / 2
        bar_y = y_center - bar_height / 2
        bar_w = (ops_sec / max_ops) * plot_width

        is_qp = (m_key == "qmlpromise")
        stroke_attr = ' stroke="#2ea043" stroke-width="1.5"' if is_qp else ""

        # Row label
        label_cls = "row-label"
        svg.append(f'<text x="{pad_left - 12}" y="{y_center + 4}" class="{label_cls}">{m_label}</text>')

        # Bar
        svg.append(f'<rect x="{pad_left}" y="{bar_y:.1f}" width="{bar_w:.1f}" height="{bar_height}" rx="3" fill="{m_color}"{stroke_attr}/>')

        # Value label
        val_cls = "val-text-green" if is_qp else "val-text"
        svg.append(f'<text x="{pad_left + bar_w + 10:.1f}" y="{y_center + 4}" class="{val_cls}">{ops_sec:,.0f} ops/s</text>')

    svg.append('</svg>')
    output_path.write_text("\n".join(svg), encoding="utf-8")


def main():
    root = Path(__file__).resolve().parent
    results_path = root / "results.csv"
    charts_dir = root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    stats = load_stats(results_path)
    if not stats:
        print(f"Error: Could not load results from {results_path}", file=sys.stderr)
        return 1

    latency_path = charts_dir / "latency-comparison.svg"
    overhead_path = charts_dir / "overhead-vs-callbacks.svg"
    throughput_path = charts_dir / "throughput-comparison.svg"

    generate_latency_chart(stats, latency_path)
    generate_overhead_chart(stats, overhead_path)
    generate_throughput_chart(stats, throughput_path)

    print(f"Generated {latency_path.name}")
    print(f"Generated {overhead_path.name}")
    print(f"Generated {throughput_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
