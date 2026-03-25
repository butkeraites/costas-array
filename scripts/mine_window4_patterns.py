from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main
from local_window4 import allowed_rows_by_column, iter_consecutive_window4_feasible_tuples


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mine 4-column patterns that are globally non-extendable for specific shards."
    )
    parser.add_argument("order", type=int, help="Order N to search.")
    parser.add_argument(
        "--assign",
        action="append",
        default=[],
        metavar="COLUMN=ROW",
        help="Fix one or more 1-based endpoint or shard coordinates.",
    )
    parser.add_argument(
        "--backend",
        choices=("sat", "native"),
        default="sat",
        help="Search backend to use for checking extendability (default: sat).",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=5.0,
        help="Time limit per pattern check in seconds.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 1,
        help="Maximum concurrent checks.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Output JSON file for the mined forbidden patterns.",
    )
    return parser


def check_pattern(
    order: int,
    base_assignments: Sequence[tuple[int, int]],
    start_col: int,
    rows: tuple[int, int, int, int],
    backend: str,
    time_limit_seconds: float,
) -> dict[str, Any]:
    # Combine base assignments with pattern
    combined = list(base_assignments)
    combined.extend([
        (start_col, rows[0]),
        (start_col + 1, rows[1]),
        (start_col + 2, rows[2]),
        (start_col + 3, rows[3]),
    ])

    result = main.search_costas_array(
        order,
        db_dir=Path(),  # Not actually using neighbors for this check
        time_limit_seconds=time_limit_seconds,
        backend=backend,
        candidate_budget=0,
        assignments=combined,
        sat_solver="cadical" if backend == "sat" else "kissat",
    )

    return {
        "start": start_col,
        "rows": rows,
        "status": result.status
    }


def main_entry(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.order < 4:
        raise SystemExit("order must be >= 4")
    
    assignments = main.parse_assignment_specs(args.assign, order=args.order)

    domain_result = allowed_rows_by_column(args.order, assignments)
    if domain_result.status == "infeasible":
        print("Base assignments are infeasible.")
        return 2

    # Count total patterns without storing them
    total_patterns = 0
    for start in range(1, args.order - 2):
        for rows in iter_consecutive_window4_feasible_tuples(domain_result.allowed_rows, start):
            total_patterns += 1
            
    print(f"Total locally feasible 4-column patterns: {total_patterns}")

    if total_patterns == 0:
        print("No feasible patterns to check.")
        return 0

    if not args.output_file:
        args.output_file = ROOT_DIR / f"forbidden_patterns_n{args.order}.json"

    forbidden_patterns: dict[str, list[tuple[int, int, int, int]]] = {}
    completed = 0
    found_forbidden = 0
    
    def task_generator():
        for start in range(1, args.order - 2):
            for rows in iter_consecutive_window4_feasible_tuples(domain_result.allowed_rows, start):
                yield (start, rows)
                
    tasks_iter = task_generator()
    future_to_task = {}
    max_queued = args.workers * 4
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Initial queue fill
        for _ in range(max_queued):
            try:
                start_col, rows = next(tasks_iter)
                future = executor.submit(
                    check_pattern,
                    order=args.order,
                    base_assignments=assignments,
                    start_col=start_col,
                    rows=rows,
                    backend=args.backend,
                    time_limit_seconds=args.time_limit,
                )
                future_to_task[future] = (start_col, rows)
            except StopIteration:
                break
            
        while future_to_task:
            done, _ = wait(future_to_task, return_when=FIRST_COMPLETED)
            for future in done:
                start_col, rows = future_to_task.pop(future)
                try:
                    res = future.result()
                    if res["status"] == "unsat":
                        key = str(start_col)
                        if key not in forbidden_patterns:
                            forbidden_patterns[key] = []
                        forbidden_patterns[key].append(rows)
                        found_forbidden += 1
                except Exception as e:
                    print(f"Error checking pattern {rows} at col {start_col}: {e}")
                    
                completed += 1
                if completed % 1000 == 0 or completed == total_patterns:
                    print(f"Checked {completed}/{total_patterns} patterns, found {found_forbidden} globally non-extendable.")
                    # Periodically flush to file natively to save progress across long runs
                    with args.output_file.open("w", encoding="utf-8") as f:
                        json.dump(forbidden_patterns, f, indent=2)

                # Replenish queue
                try:
                    next_start, next_rows = next(tasks_iter)
                    new_future = executor.submit(
                        check_pattern,
                        order=args.order,
                        base_assignments=assignments,
                        start_col=next_start,
                        rows=next_rows,
                        backend=args.backend,
                        time_limit_seconds=args.time_limit,
                    )
                    future_to_task[new_future] = (next_start, next_rows)
                except StopIteration:
                    pass

    # Save to file
    with args.output_file.open("w", encoding="utf-8") as f:
        json.dump(forbidden_patterns, f, indent=2)
        
    print(f"Saved {found_forbidden} non-extendable patterns to {args.output_file}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
