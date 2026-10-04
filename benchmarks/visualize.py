#!/usr/bin/env python3
"""Benchmark visualization and reporting generator for QmlPromise.

Reads results.csv, results-before.csv, and components.csv using Python's standard
library only and generates:
1. An interactive, standalone HTML dashboard with responsive charts (Chart.js via CDN)
2. A GitHub-Flavored Markdown summary suitable for $GITHUB_STEP_SUMMARY
"""

import argparse
import csv
from collections import defaultdict
import html
import json
from pathlib import Path
from statistics import mean, median
import sys


def parse_results(filepath: Path):
    if not filepath.exists():
        return {}
    groups = defaultdict(list)
    with filepath.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["workload"], int(row["batch"]), row["method"])
            groups[key].append({
                "repeat": int(row["repeat"]),
                "operations": int(row["operations"]),
                "setup_us_per_op": float(row["setup_us_per_op"]),
                "total_us_per_op": float(row["total_us_per_op"]),
                "ops_per_second": float(row["ops_per_second"]) if "ops_per_second" in row and row["ops_per_second"] else 1e6 / float(row["total_us_per_op"]),
            })
    return groups


def parse_components(filepath: Path):
    if not filepath.exists():
        return {}
    groups = defaultdict(list)
    with filepath.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            groups[row["component"]].append({
                "repeat": int(row["repeat"]),
                "operations": int(row["operations"]),
                "loop_us_per_op": float(row["loop_us_per_op"]),
                "total_us_per_op": float(row["total_us_per_op"]),
            })
    return groups


def aggregate_results(groups):
    stats = {}
    for (workload, batch, method), rows in groups.items():
        setups = [r["setup_us_per_op"] for r in rows]
        totals = [r["total_us_per_op"] for r in rows]
        ops = [r["ops_per_second"] for r in rows]
        stats[(workload, batch, method)] = {
            "workload": workload,
            "batch": batch,
            "method": method,
            "samples": len(rows),
            "setup_median": median(setups),
            "total_median": median(totals),
            "total_min": min(totals),
            "total_max": max(totals),
            "ops_sec_median": median(ops),
        }
    return stats


def generate_markdown_summary(current_stats, before_stats=None, components_stats=None):
    md = []
    md.append("## 🚀 QmlPromise Benchmark & Performance Summary\n")

    # Speedup section if before data is available
    if before_stats:
        md.append("### ⚡ Optimization Speedup (Before vs After)\n")
        md.append("| Workload | Batch | Baseline (v1.0) | Optimized (v1.1 Cached) | Speedup | Latency Reduction |")
        md.append("|:---|---:|---:|---:|---:|---:|")
        for (w, b, m), curr in sorted(current_stats.items()):
            if m == "qmlpromise" and (w, b, m) in before_stats:
                prev = before_stats[(w, b, m)]
                speedup = prev["total_median"] / curr["total_median"]
                reduction = (1.0 - curr["total_median"] / prev["total_median"]) * 100.0
                md.append(f"| `{w}` | {b} | {prev['total_median']:.2f} µs | **{curr['total_median']:.2f} µs** | **{speedup:.1f}×** | -{reduction:.1f}% |")
        md.append("")

    # Full End-to-End comparison across methods
    md.append("### 📊 End-to-End Delivery Comparison (Current)\n")
    md.append("| Workload | Batch | Method | Setup (µs/op) | Total (µs/op) median [min–max] | Throughput (Ops/sec) |")
    md.append("|:---|---:|:---|---:|---:|---:|")
    for (w, b, m), s in sorted(current_stats.items()):
        md.append(f"| `{w}` | {b} | `{m}` | {s['setup_median']:.2f} | **{s['total_median']:.2f}** [{s['total_min']:.2f}–{s['total_max']:.2f}] | {s['ops_sec_median']:,.0f} |")
    md.append("")

    # Component microbenchmarks if available
    if components_stats:
        md.append("### 🔬 Isolated Component Costs\n")
        md.append("| Component | Loop (µs/op) | Total w/ Final GC (µs/op) |")
        md.append("|:---|---:|---:|")
        for comp, rows in sorted(components_stats.items()):
            loop = median([r["loop_us_per_op"] for r in rows])
            total = median([r["total_us_per_op"] for r in rows])
            md.append(f"| `{comp}` | {loop:.2f} | {total:.2f} |")
        md.append("")

    return "\n".join(md)


def generate_html_report(current_stats, before_stats=None, components_stats=None, title="QmlPromise Performance Report"):
    workloads = ["ready", "pending", "worker"]
    batches = [1, 64]
    methods = ["queued_signal", "continuation_signal", "watcher_signal", "watcher_callback", "qmlpromise"]

    # Speedups for summary cards
    speedup_ready_64 = 0.0
    speedup_pending_64 = 0.0
    speedup_worker_64 = 0.0
    if before_stats:
        if ("ready", 64, "qmlpromise") in before_stats and ("ready", 64, "qmlpromise") in current_stats:
            speedup_ready_64 = before_stats[("ready", 64, "qmlpromise")]["total_median"] / current_stats[("ready", 64, "qmlpromise")]["total_median"]
        if ("pending", 64, "qmlpromise") in before_stats and ("pending", 64, "qmlpromise") in current_stats:
            speedup_pending_64 = before_stats[("pending", 64, "qmlpromise")]["total_median"] / current_stats[("pending", 64, "qmlpromise")]["total_median"]
        if ("worker", 64, "qmlpromise") in before_stats and ("worker", 64, "qmlpromise") in current_stats:
            speedup_worker_64 = before_stats[("worker", 64, "qmlpromise")]["total_median"] / current_stats[("worker", 64, "qmlpromise")]["total_median"]

    best_throughput = max([s["ops_sec_median"] for s in current_stats.values() if s["method"] == "qmlpromise"], default=0)

    # JSON chart payload
    chart_data = {
        "workloads": workloads,
        "batches": batches,
        "methods": methods,
        "current": {},
        "before": {},
        "components": {}
    }
    for k, v in current_stats.items():
        chart_data["current"][f"{k[0]}:{k[1]}:{k[2]}"] = v
    if before_stats:
        for k, v in before_stats.items():
            chart_data["before"][f"{k[0]}:{k[1]}:{k[2]}"] = v
    if components_stats:
        for comp, rows in components_stats.items():
            chart_data["components"][comp] = {
                "loop": median([r["loop_us_per_op"] for r in rows]),
                "total": median([r["total_us_per_op"] for r in rows])
            }

    chart_json = json.dumps(chart_data)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --border-color: #30363d;
    --text-primary: #f0f6fc;
    --text-secondary: #8b949e;
    --accent-blue: #58a6ff;
    --accent-green: #3fb950;
    --accent-purple: #bc8cff;
    --accent-orange: #f0883e;
    --accent-red: #f85149;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background-color: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-sans);
    line-height: 1.5;
    padding: 24px;
  }}

  .container {{ max-width: 1280px; margin: 0 auto; }}

  header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 20px;
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 16px;
  }}

  .title-group h1 {{
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 10px;
  }}

  .title-group p {{
    color: var(--text-secondary);
    font-size: 0.95rem;
    margin-top: 4px;
  }}

  .badge {{
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.85rem;
    color: var(--accent-blue);
    font-weight: 500;
  }}

  /* KPI cards */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }}

  .kpi-card {{
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 16px 20px;
    position: relative;
    overflow: hidden;
  }}

  .kpi-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    background: var(--card-accent, var(--accent-blue));
  }}

  .kpi-card.green {{ --card-accent: var(--accent-green); }}
  .kpi-card.purple {{ --card-accent: var(--accent-purple); }}
  .kpi-card.orange {{ --card-accent: var(--accent-orange); }}

  .kpi-label {{
    color: var(--text-secondary);
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
  }}

  .kpi-value {{
    font-size: 2rem;
    font-weight: 700;
    margin: 8px 0 4px 0;
    color: var(--text-primary);
  }}

  .kpi-subtext {{
    color: var(--text-secondary);
    font-size: 0.8rem;
  }}

  /* Chart sections */
  .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 24px;
  }}

  @media (max-width: 900px) {{
    .grid-2 {{ grid-template-columns: 1fr; }}
  }}

  .card {{
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 24px;
  }}

  .card-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border-color);
  }}

  .card-header h2 {{
    font-size: 1.15rem;
    font-weight: 600;
  }}

  .chart-container {{
    position: relative;
    height: 320px;
    width: 100%;
  }}

  /* Data tables */
  .table-wrapper {{
    overflow-x: auto;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
    text-align: left;
  }}

  th {{
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    padding: 10px 14px;
    font-weight: 600;
    border-bottom: 1px solid var(--border-color);
  }}

  td {{
    padding: 10px 14px;
    border-bottom: 1px solid var(--border-color);
  }}

  tr:hover td {{
    background: rgba(255, 255, 255, 0.02);
  }}

  .text-right {{ text-align: right; }}
  .font-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .highlight-speedup {{
    color: var(--accent-green);
    font-weight: 700;
  }}

  footer {{
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.85rem;
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid var(--border-color);
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="title-group">
      <h1>⚡ QmlPromise Performance & Benchmark</h1>
      <p>Continuous Benchmark Report & End-to-End Latency/Throughput Analysis</p>
    </div>
    <div>
      <span class="badge">Qt 6 &bull; C++20 &bull; Header-Only</span>
    </div>
  </header>

  <!-- KPI summary cards -->
  <div class="kpi-grid">
    <div class="kpi-card green">
      <div class="kpi-label">Ready Batch 64 Speedup</div>
      <div class="kpi-value">{speedup_ready_64:.1f}×</div>
      <div class="kpi-subtext">Compared to un-cached resolver evaluation</div>
    </div>
    <div class="kpi-card green">
      <div class="kpi-label">Pending Batch 64 Speedup</div>
      <div class="kpi-value">{speedup_pending_64:.1f}×</div>
      <div class="kpi-subtext">Asynchronous QPromise resolution</div>
    </div>
    <div class="kpi-card purple">
      <div class="kpi-label">Worker Batch 64 Speedup</div>
      <div class="kpi-value">{speedup_worker_64:.1f}×</div>
      <div class="kpi-subtext">QtConcurrent threadpool workload</div>
    </div>
    <div class="kpi-card orange">
      <div class="kpi-label">Peak QmlPromise Throughput</div>
      <div class="kpi-value">{best_throughput:,.0f}</div>
      <div class="kpi-subtext">Operations per second (Ready Batch 64)</div>
    </div>
  </div>

  <!-- Row 1: Speedup Comparison & Throughput -->
  <div class="grid-2">
    <div class="card">
      <div class="card-header">
        <h2>⚡ Before vs After Latency (µs/op)</h2>
        <span class="badge">Lower is better</span>
      </div>
      <div class="chart-container">
        <canvas id="speedupChart"></canvas>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2>🚀 Throughput Comparison (Ops/sec, Batch 64)</h2>
        <span class="badge">Higher is better</span>
      </div>
      <div class="chart-container">
        <canvas id="throughputChart"></canvas>
      </div>
    </div>
  </div>

  <!-- Row 2: Method Comparison Across Workloads (Batch 64 & Batch 1) -->
  <div class="grid-2">
    <div class="card">
      <div class="card-header">
        <h2>📊 Batch 64 Latency Across Delivery Methods</h2>
        <span class="badge">Amortized µs/op</span>
      </div>
      <div class="chart-container">
        <canvas id="batch64Chart"></canvas>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2>⏱️ Batch 1 Latency Across Delivery Methods</h2>
        <span class="badge">Single Request µs/op</span>
      </div>
      <div class="chart-container">
        <canvas id="batch1Chart"></canvas>
      </div>
    </div>
  </div>

  <!-- Row 3: Isolated microbenchmark costs -->
  <div class="card">
    <div class="card-header">
      <h2>🔬 Isolated Component Microbenchmarks</h2>
      <span class="badge">Microsecond overhead</span>
    </div>
    <div class="chart-container" style="height: 240px;">
      <canvas id="componentChart"></canvas>
    </div>
  </div>

  <!-- Data Tables -->
  <div class="card">
    <div class="card-header">
      <h2>📋 Detailed Measurement Records</h2>
    </div>
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Workload</th>
            <th class="text-right">Batch</th>
            <th>Method</th>
            <th class="text-right">Setup µs/op</th>
            <th class="text-right">Total µs/op (Median)</th>
            <th class="text-right">Range [Min – Max]</th>
            <th class="text-right">Throughput (Ops/sec)</th>
          </tr>
        </thead>
        <tbody>
"""

    for (w, b, m), s in sorted(current_stats.items()):
        is_promise = (m == "qmlpromise")
        row_style = ' style="font-weight: 600; color: var(--accent-blue);"' if is_promise else ""
        html_content += f"""          <tr{row_style}>
            <td class="font-mono">{w}</td>
            <td class="text-right font-mono">{b}</td>
            <td class="font-mono">{m}</td>
            <td class="text-right font-mono">{s['setup_median']:.2f}</td>
            <td class="text-right font-mono">{s['total_median']:.2f}</td>
            <td class="text-right font-mono" style="color: var(--text-secondary);">[{s['total_min']:.2f} – {s['total_max']:.2f}]</td>
            <td class="text-right font-mono">{s['ops_sec_median']:,.0f}</td>
          </tr>
"""

    html_content += f"""        </tbody>
      </table>
    </div>
  </div>

  <footer>
    Generated by QmlPromise Benchmark Visualization &bull; Standard Library &amp; Chart.js
  </footer>
</div>

<script>
const data = {chart_json};
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = '#30363d';
Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

// 1. Speedup Chart: Before vs After for qmlpromise
const speedupLabels = [
  'Ready B1', 'Ready B64',
  'Pending B1', 'Pending B64',
  'Worker B1', 'Worker B64'
];

const beforeValues = [
  data.before['ready:1:qmlpromise']?.total_median || 0,
  data.before['ready:64:qmlpromise']?.total_median || 0,
  data.before['pending:1:qmlpromise']?.total_median || 0,
  data.before['pending:64:qmlpromise']?.total_median || 0,
  data.before['worker:1:qmlpromise']?.total_median || 0,
  data.before['worker:64:qmlpromise']?.total_median || 0
];

const afterValues = [
  data.current['ready:1:qmlpromise']?.total_median || 0,
  data.current['ready:64:qmlpromise']?.total_median || 0,
  data.current['pending:1:qmlpromise']?.total_median || 0,
  data.current['pending:64:qmlpromise']?.total_median || 0,
  data.current['worker:1:qmlpromise']?.total_median || 0,
  data.current['worker:64:qmlpromise']?.total_median || 0
];

new Chart(document.getElementById('speedupChart'), {{
  type: 'bar',
  data: {{
    labels: speedupLabels,
    datasets: [
      {{
        label: 'Before (v1.0 Uncached)',
        data: beforeValues,
        backgroundColor: '#f8514988',
        borderColor: '#f85149',
        borderWidth: 1
      }},
      {{
        label: 'After (v1.1 Cached + Explicit Polyfill)',
        data: afterValues,
        backgroundColor: '#3fb950aa',
        borderColor: '#3fb950',
        borderWidth: 1
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'top' }},
      tooltip: {{
        callbacks: {{
          afterBody: function(items) {{
            const idx = items[0].dataIndex;
            const b = beforeValues[idx];
            const a = afterValues[idx];
            if (b > 0 && a > 0) {{
              return 'Speedup: ' + (b / a).toFixed(1) + 'x (' + ((1 - a / b) * 100).toFixed(1) + '% faster)';
            }}
          }}
        }}
      }}
    }},
    scales: {{
      y: {{
        title: {{ display: true, text: 'Median µs/op (Lower is better)' }},
        beginAtZero: true
      }}
    }}
  }}
}});

// 2. Throughput Chart (Batch 64)
const methodList = ['queued_signal', 'continuation_signal', 'watcher_signal', 'watcher_callback', 'qmlpromise'];
const methodColors = {{
  'queued_signal': '#8b949e',
  'continuation_signal': '#58a6ff',
  'watcher_signal': '#d29922',
  'watcher_callback': '#f0883e',
  'qmlpromise': '#3fb950'
}};

const throughputData = methodList.map(m => data.current['ready:64:' + m]?.ops_sec_median || 0);

new Chart(document.getElementById('throughputChart'), {{
  type: 'bar',
  data: {{
    labels: ['Queued Signal (No Observer)', 'Continuation Signal', 'Watcher Signal', 'Watcher Callback', 'QmlPromise (.then)'],
    datasets: [{{
      label: 'Ready Batch 64 Ops/sec',
      data: throughputData,
      backgroundColor: methodList.map(m => methodColors[m] + 'bb'),
      borderColor: methodList.map(m => methodColors[m]),
      borderWidth: 1
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      y: {{
        title: {{ display: true, text: 'Operations / sec (Higher is better)' }},
        beginAtZero: true
      }}
    }}
  }}
}});

// 3. Batch 64 Across Methods
new Chart(document.getElementById('batch64Chart'), {{
  type: 'bar',
  data: {{
    labels: ['Ready', 'Pending', 'Worker'],
    datasets: methodList.map(m => ({{
      label: m,
      data: ['ready', 'pending', 'worker'].map(w => data.current[w + ':64:' + m]?.total_median || 0),
      backgroundColor: methodColors[m] + 'aa',
      borderColor: methodColors[m],
      borderWidth: 1
    }}))
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      y: {{
        title: {{ display: true, text: 'Median Total µs/op' }},
        beginAtZero: true
      }}
    }}
  }}
}});

// 4. Batch 1 Across Methods
new Chart(document.getElementById('batch1Chart'), {{
  type: 'bar',
  data: {{
    labels: ['Ready', 'Pending', 'Worker'],
    datasets: methodList.map(m => ({{
      label: m,
      data: ['ready', 'pending', 'worker'].map(w => data.current[w + ':1:' + m]?.total_median || 0),
      backgroundColor: methodColors[m] + 'aa',
      borderColor: methodColors[m],
      borderWidth: 1
    }}))
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      y: {{
        title: {{ display: true, text: 'Median Total µs/op' }},
        beginAtZero: true
      }}
    }}
  }}
}});

// 5. Component Microbenchmark
const compKeys = Object.keys(data.components);
if (compKeys.length > 0) {{
  new Chart(document.getElementById('componentChart'), {{
    type: 'bar',
    data: {{
      labels: compKeys,
      datasets: [
        {{
          label: 'Loop µs/op',
          data: compKeys.map(k => data.components[k].loop),
          backgroundColor: '#58a6ffaa',
          borderColor: '#58a6ff',
          borderWidth: 1
        }},
        {{
          label: 'Total w/ Final GC µs/op',
          data: compKeys.map(k => data.components[k].total),
          backgroundColor: '#bc8cffaa',
          borderColor: '#bc8cff',
          borderWidth: 1
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      scales: {{
        y: {{
          title: {{ display: true, text: 'µs / op' }},
          beginAtZero: true
        }}
      }}
    }}
  }});
}}
</script>
</body>
</html>
"""
    return html_content


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark visualizations and summaries for QmlPromise")
    parser.add_argument("--results", type=Path, default=Path("benchmarks/results.csv"), help="Path to results.csv")
    parser.add_argument("--before", type=Path, default=Path("benchmarks/results-before.csv"), help="Path to results-before.csv")
    parser.add_argument("--components", type=Path, default=Path("benchmarks/components.csv"), help="Path to components.csv")
    parser.add_argument("--html", type=Path, default=None, help="Output path for standalone HTML report")
    parser.add_argument("--summary", action="store_true", help="Print Markdown summary to stdout")
    parser.add_argument("--github-summary", action="store_true", help="Append Markdown summary to $GITHUB_STEP_SUMMARY if available")

    args = parser.parse_args()

    results_data = parse_results(args.results)
    if not results_data:
        print(f"Warning: No benchmark results found at {args.results}", file=sys.stderr)
        return 1

    current_stats = aggregate_results(results_data)
    before_stats = aggregate_results(parse_results(args.before)) if args.before.exists() else None
    components_stats = parse_components(args.components) if args.components.exists() else None

    # Markdown summary
    summary_md = generate_markdown_summary(current_stats, before_stats, components_stats)

    if args.summary or (not args.html and not args.github_summary):
        print(summary_md)

    # HTML output
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        html_code = generate_html_report(current_stats, before_stats, components_stats)
        args.html.write_text(html_code, encoding="utf-8")
        print(f"Visualization report generated at: {args.html}")

    # GitHub Step Summary
    if args.github_summary:
        import os
        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(summary_md + "\n")
            print(f"Summary appended to $GITHUB_STEP_SUMMARY")
        else:
            print("Notice: GITHUB_STEP_SUMMARY environment variable not set, skipping step summary output.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
