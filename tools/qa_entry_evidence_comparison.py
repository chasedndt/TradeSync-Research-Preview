"""Read-only live reading of the declared entry-evidence comparisons.

Runs inside the state-api container against this checkout's code, opens its own
connection and prints what the endpoint would serve: how much of each reading the
recorded history actually supports, the family's bar, every cell that could be
tested, and what the bounded reads cost.

It writes nothing. Every statement is a SELECT, with the two SET LOCAL settings
each bounded read runs under; no migration is applied and no table is created.

    python tools/run_in_state_api.py tools/qa_entry_evidence_comparison.py
"""

from __future__ import annotations

import asyncio
import json
import os

import asyncpg

from app.entry_evidence_comparison import compute_entry_evidence_comparison


def line(cell: dict) -> str:
    def number(value, digits=1):
        return "—" if value is None else f"{value * 100:.{digits}f}"

    return (
        f"  {cell['variable']:<28} {cell['polarity']:<9} {cell['horizon_minutes']:>4}m "
        f"ctx {cell['context_available']:>5}/{cell['eligible']:<5} "
        f"kept {cell['retained']:>5}/{cell['abstained']:<5} "
        f"kept {number(cell['retained_mean_net_pct']):>8} skipped {number(cell['abstained_mean_net_pct']):>8} "
        f"contrast {number(cell['contrast_pct']):>8} bps  "
        f"z {'—' if cell['z'] is None else format(cell['z'], '+.2f'):>6}  "
        f"{'tested' if cell['tested'] else cell['sample_state']}"
        f"{'  SELECTS' if cell['selects'] else ''}"
    )


async def main() -> int:
    pool = await asyncpg.create_pool(os.environ["PG_DSN"], min_size=1, max_size=2, statement_cache_size=0)
    try:
        report = await compute_entry_evidence_comparison(pool)
    finally:
        await pool.close()

    population = report.get("population", {})
    source = report.get("population_source", {})
    coverage = source.get("coverage", {})
    cells = report.get("cells", [])
    tested = [cell for cell in cells if cell["tested"]]

    print("=== population")
    print(f"  calls measured      {population.get('cases')}")
    print(f"  opportunities       {source.get('opportunities')}")
    print(f"  markets             {len(population.get('symbols') or [])}: {', '.join(population.get('symbols') or [])}")
    print(f"  horizons            {population.get('horizons')}")
    print(f"  window              {source.get('window_days')} days")
    print(f"  history begins      {json.dumps(source.get('recorded_history_begins'))}")
    print(f"  managed positions   {report.get('managed_paper', {}).get('positions')}")

    print("=== coverage (calls with no reading)")
    for key in ("no_recorded_book", "no_open_interest_pair", "no_liquidation_received", "no_timeframe_measurement"):
        print(f"  {key:<28} {coverage.get(key)}")
    print("  context coverage per variable: " + json.dumps(population.get("context_coverage")))

    print("=== family")
    print(f"  {report.get('family', {}).get('version')} {report.get('family', {}).get('sha256', '')[:16]}…")
    print(f"  cells {report.get('holm', {}).get('cells')} declared, {report.get('holm', {}).get('cells_tested')} testable, "
          f"first-rank bar {report.get('holm', {}).get('first_rank_bar')}")
    print(f"  costs {report.get('costs', {}).get('total_pct')}% round trip")

    print("=== cells (means and contrast in basis points, net of costs)")
    for cell in sorted(cells, key=lambda c: (not c["tested"], -(c["z"] or -99))):
        print(line(cell))

    print("=== verdicts")
    print(f"  tested        {len(tested)}")
    print(f"  select        {sum(1 for cell in cells if cell['selects'])}")
    print(f"  economic      {sum(1 for cell in cells if cell['economic'])}")
    print(f"  held out      {sum(1 for cell in cells if cell['held_out'])}")

    print("=== bounded reads")
    for name, reading in (report.get("reads", {}).get("reads") or {}).items():
        print(f"  {name:<30} {reading.get('last_duration_s')}s  rows {reading.get('rows')}  "
              f"runs {reading.get('runs')}  failures {reading.get('failures')}")

    print(f"=== authority {report.get('authority')} · promotion_allowed {report.get('promotion_allowed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
