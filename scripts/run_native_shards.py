from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run native Costas search shards in parallel."
    )
    parser.add_argument("order", type=int, help="Order N to search.")
    parser.add_argument(
        "--time-limit",
        type=float,
        default=300.0,
        help="Per-shard time limit in seconds.",
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
        default=ROOT_DIR / "artifacts" / "native-shards",
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
    parser.add_argument(
        "--focus-widths",
        help="Optional comma-separated width priorities to guide native branching.",
    )
    return parser


def generate_endpoint_shards(order: int) -> list[dict[str, Any]]:
    shards = []
    for first_row in range(1, (order + 1) // 2 + 1):
        for last_row in range(first_row, order + 2 - first_row):
            if last_row == first_row:
                continue
            shard_index = len(shards)
            shards.append(
                {
                    "index": shard_index,
                    "id": f"c1r{first_row}_c{order}r{last_row}",
                    "assignments": [(1, first_row), (order, last_row)],
                }
            )
    return shards


def parse_native_output(stdout: str) -> dict[str, Any]:
    parsed: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()

    example = None
    if parsed.get("example"):
        example = [int(value) for value in parsed["example"].split()]

    return {
        "status": parsed.get("status", "unknown"),
        "nodes": int(parsed.get("nodes", "0")),
        "example": example,
    }


def run_one_shard(
    *,
    binary: Path,
    order: int,
    time_limit: float,
    shard: dict[str, Any],
    output_dir: Path,
    focus_widths: str | None,
) -> dict[str, Any]:
    shard_dir = output_dir / shard["id"]
    shard_dir.mkdir(parents=True, exist_ok=True)

    command = [str(binary), str(order), str(time_limit)]
    if focus_widths:
        command.append(f"--focus-widths={focus_widths}")
    command.extend(f"{column}={row}" for column, row in shard["assignments"])
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    log_path = shard_dir / "native.log"
    log_path.write_text(
        result.stdout + ("\nSTDERR:\n" + result.stderr if result.stderr else ""),
        encoding="utf-8",
    )

    parsed = parse_native_output(result.stdout)
    shard_result = {
        "index": shard["index"],
        "id": shard["id"],
        "assignments": shard["assignments"],
        "command": command,
        "exit_code": result.returncode,
        "log": str(log_path),
        **parsed,
    }
    (shard_dir / "result.json").write_text(
        json.dumps(shard_result, indent=2),
        encoding="utf-8",
    )
    return shard_result


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

    binary = main.build_native_solver()
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
        "time_limit": args.time_limit,
        "workers": args.workers,
        "output_dir": str(output_dir),
        "total_shards": len(all_shards),
        "selected_shards": len(selected_shards),
        "shard_stride": args.shard_stride,
        "shard_offset": args.shard_offset,
        "focus_widths": args.focus_widths,
        "counts": {"found": 0, "unsat": 0, "unknown": 0},
        "results": [],
    }
    summary_path = output_dir / f"summary_stride{args.shard_stride}_offset{args.shard_offset}.json"
    progress_path = output_dir / f"progress_stride{args.shard_stride}_offset{args.shard_offset}.jsonl"
    progress_path.write_text("", encoding="utf-8")

    future_to_shard: dict[Future[dict[str, Any]], dict[str, Any]] = {}
    found_result: dict[str, Any] | None = None
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for shard in selected_shards:
            future = executor.submit(
                run_one_shard,
                binary=binary,
                order=args.order,
                time_limit=args.time_limit,
                shard=shard,
                output_dir=output_dir,
                focus_widths=args.focus_widths,
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

                if shard_result["status"] == "found":
                    found_result = shard_result
                    for pending in future_to_shard:
                        pending.cancel()
                    future_to_shard.clear()
                    break

    summary["results"].sort(key=lambda item: item["index"])
    if found_result is not None:
        summary["overall_status"] = "found"
        summary["found_shard"] = found_result["id"]
    elif summary["counts"]["unknown"] == 0:
        summary["overall_status"] = "unsat"
    else:
        summary["overall_status"] = "unknown"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Order N={args.order}")
    print(f"Selected shards: {len(selected_shards)} of {len(all_shards)}")
    print(
        "Status counts: "
        f"found={summary['counts']['found']} "
        f"unsat={summary['counts']['unsat']} "
        f"unknown={summary['counts']['unknown']}"
    )
    print(f"Overall status: {summary['overall_status']}")
    print(f"Summary: {summary_path}")
    print(f"Progress log: {progress_path}")
    if found_result is not None:
        print("Witness:")
        print("  " + " ".join(str(value) for value in found_result["example"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
