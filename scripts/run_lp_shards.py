from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (ROOT_DIR, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import lp_shard_relaxation
from run_native_shards import generate_endpoint_shards


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run shard-aware LP relaxations in parallel."
    )
    parser.add_argument("order", type=int, help="Order N to study.")
    parser.add_argument(
        "--widths",
        default="all",
        help="Comma-separated widths, or one of: short4, dyadic, all.",
    )
    parser.add_argument(
        "--solver",
        choices=("PDLP", "GLOP"),
        default="PDLP",
        help="LP backend to use.",
    )
    parser.add_argument(
        "--triangles",
        choices=("none", "consecutive", "window4"),
        default="consecutive",
        help="Optional triangle-marginal layer to tighten local width interactions.",
    )
    parser.add_argument(
        "--quads",
        choices=("none", "endpoints"),
        default="none",
        help="Optional 4-column endpoint-window layer.",
    )
    parser.add_argument(
        "--quad-radius",
        type=int,
        default=2,
        help="Number of consecutive 4-column windows to add from each endpoint.",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=60.0,
        help="Per-shard time limit in seconds.",
    )
    parser.add_argument(
        "--forbidden-patterns",
        type=Path,
        help="Optional JSON file mapping start_column to a list of globally forbidden 4-column tuples.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 1,
        help="Maximum number of concurrent shard workers.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "artifacts" / "lp-shards",
        help="Directory for shard logs and summary output.",
    )
    parser.add_argument(
        "--shard-stride",
        type=int,
        default=1,
        help="Keep only shard indexes congruent to --shard-offset modulo this value.",
    )
    parser.add_argument(
        "--shard-offset",
        type=int,
        default=0,
        help="Shard index residue to keep when --shard-stride is greater than 1.",
    )
    return parser


def run_one_shard(
    *,
    order: int,
    widths: list[int],
    solver_name: str,
    triangle_mode: str,
    quad_mode: str,
    quad_radius: int,
    time_limit: float,
    shard: dict[str, Any],
    output_dir: Path,
    forbidden_patterns_path: Path | None,
) -> dict[str, Any]:
    shard_dir = output_dir / shard["id"]
    shard_dir.mkdir(parents=True, exist_ok=True)

    result = lp_shard_relaxation.solve_relaxation(
        order,
        widths=widths,
        assignments=shard["assignments"],
        solver_name=solver_name,
        time_limit_seconds=time_limit,
        triangle_mode=triangle_mode,
        quad_mode=quad_mode,
        quad_radius=quad_radius,
        forbidden_patterns_path=forbidden_patterns_path,
    )

    shard_result = {
        "index": shard["index"],
        "id": shard["id"],
        "assignments": shard["assignments"],
        "status": result.status,
        "solver_status": result.solver_status,
        "variables": result.variable_count,
        "constraints": result.constraint_count,
        "wall_time_seconds": result.wall_time_seconds,
    }
    (shard_dir / "result.json").write_text(
        json.dumps(shard_result, indent=2),
        encoding="utf-8",
    )
    return shard_result


def load_existing_result(shard_dir: Path) -> dict[str, Any] | None:
    path = shard_dir / "result.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main_entry(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.order < 1:
        raise SystemExit("order must be positive")
    if args.workers < 1:
        raise SystemExit("workers must be positive")
    if args.shard_stride < 1:
        raise SystemExit("shard stride must be positive")
    if not 0 <= args.shard_offset < args.shard_stride:
        raise SystemExit("shard offset must satisfy 0 <= offset < stride")

    widths = lp_shard_relaxation.parse_width_spec(args.widths, args.order)
    all_shards = generate_endpoint_shards(args.order)
    selected_shards = [
        shard
        for shard in all_shards
        if shard["index"] % args.shard_stride == args.shard_offset
    ]

    output_dir = args.output_dir.resolve() / f"n{args.order}"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "order": args.order,
        "widths": widths,
        "solver": args.solver,
        "triangles": args.triangles,
        "quads": args.quads,
        "quad_radius": args.quad_radius,
        "time_limit": args.time_limit,
        "workers": args.workers,
        "output_dir": str(output_dir),
        "total_shards": len(all_shards),
        "selected_shards": len(selected_shards),
        "shard_stride": args.shard_stride,
        "shard_offset": args.shard_offset,
        "counts": {"feasible": 0, "infeasible": 0, "unknown": 0},
        "results": [],
    }
    summary_path = output_dir / f"summary_stride{args.shard_stride}_offset{args.shard_offset}.json"
    progress_path = output_dir / f"progress_stride{args.shard_stride}_offset{args.shard_offset}.jsonl"
    progress_path.write_text("", encoding="utf-8")

    pending_shards: list[dict[str, Any]] = []
    for shard in selected_shards:
        existing = load_existing_result(output_dir / shard["id"])
        if existing is None:
            pending_shards.append(shard)
            continue
        summary["results"].append(existing)
        summary["counts"][existing["status"]] += 1
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(existing) + "\n")

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    future_to_shard: dict[Future[dict[str, Any]], dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for shard in pending_shards:
            future = executor.submit(
                run_one_shard,
                order=args.order,
                widths=widths,
                solver_name=args.solver,
                triangle_mode=args.triangles,
                quad_mode=args.quads,
                quad_radius=args.quad_radius,
                time_limit=args.time_limit,
                shard=shard,
                output_dir=output_dir,
                forbidden_patterns_path=args.forbidden_patterns,
            )
            future_to_shard[future] = shard

        while future_to_shard:
            done, _pending = wait(future_to_shard, return_when=FIRST_COMPLETED)
            for future in done:
                shard_result = future.result()
                summary["results"].append(shard_result)
                summary["counts"][shard_result["status"]] += 1
                del future_to_shard[future]
                with progress_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(shard_result) + "\n")
                summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    summary["results"].sort(key=lambda item: item["index"])
    if summary["counts"]["infeasible"] > 0:
        summary["overall_status"] = "some_infeasible"
    elif summary["counts"]["unknown"] > 0:
        summary["overall_status"] = "unknown"
    else:
        summary["overall_status"] = "all_feasible"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Order N={args.order}")
    print(f"Selected shards: {len(selected_shards)} of {len(all_shards)}")
    print(f"Reused existing shard results: {len(selected_shards) - len(pending_shards)}")
    print(
        "Status counts: "
        f"feasible={summary['counts']['feasible']} "
        f"infeasible={summary['counts']['infeasible']} "
        f"unknown={summary['counts']['unknown']}"
    )
    print(f"Overall status: {summary['overall_status']}")
    print(f"Summary: {summary_path}")
    print(f"Progress log: {progress_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
