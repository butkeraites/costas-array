from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (ROOT_DIR, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_near_miss_cloud import collision_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mine recurring bad widths from a near-miss cloud."
    )
    parser.add_argument(
        "nodes_csv",
        type=Path,
        help="Path to near_miss_nodes.csv.",
    )
    parser.add_argument(
        "--max-energy",
        type=int,
        default=20,
        help="Ignore near-miss states above this energy.",
    )
    parser.add_argument(
        "--top-widths",
        type=int,
        default=8,
        help="Number of focus widths to select.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path.",
    )
    return parser


def mine_width_pressure(rows: Sequence[dict[str, str]], max_energy: int) -> dict[int, dict[str, int]]:
    pressure: dict[int, dict[str, int]] = {}
    for row in rows:
        energy = int(row["energy"])
        if energy > max_energy:
            continue
        weight = max(1, max_energy + 1 - energy)
        array = [int(value) for value in row["array"].split()]
        for width, collisions in enumerate(collision_profile(array), start=1):
            if collisions == 0:
                continue
            stats = pressure.setdefault(width, {"weighted_collisions": 0, "node_count": 0, "raw_collisions": 0})
            stats["weighted_collisions"] += collisions * weight
            stats["node_count"] += 1
            stats["raw_collisions"] += collisions
    return pressure


def main_entry(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with args.nodes_csv.resolve().open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    pressure = mine_width_pressure(rows, args.max_energy)
    ranked = sorted(
        (
            {
                "width": width,
                **stats,
            }
            for width, stats in pressure.items()
        ),
        key=lambda item: (-item["weighted_collisions"], -item["raw_collisions"], item["width"]),
    )
    selected = [item["width"] for item in ranked[: args.top_widths]]

    result = {
        "nodes_csv": str(args.nodes_csv.resolve()),
        "max_energy": args.max_energy,
        "top_widths": args.top_widths,
        "selected_widths": selected,
        "focus_widths_arg": ",".join(str(width) for width in selected),
        "ranked_widths": ranked,
    }

    if args.output:
        output_path = args.output.resolve()
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote width-pressure summary to {output_path}")

    print(f"Selected widths: {result['focus_widths_arg']}")
    for item in ranked[: min(12, len(ranked))]:
        print(
            f"width={item['width']} weighted_collisions={item['weighted_collisions']} "
            f"raw_collisions={item['raw_collisions']} nodes={item['node_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
