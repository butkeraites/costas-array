from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize dyadic difference-layer statistics for stored Costas arrays."
    )
    parser.add_argument(
        "--db-dir",
        type=Path,
        default=ROOT_DIR / "db",
        help="Directory containing Costas_essense_N=<n>.txt files.",
    )
    parser.add_argument(
        "orders",
        nargs="*",
        type=int,
        help="Optional orders to inspect. Defaults to all stored orders.",
    )
    return parser


def dyadic_shifts(order: int) -> list[int]:
    shifts = []
    shift = 1
    while shift < order:
        shifts.append(shift)
        shift *= 2
    return shifts


def analyze_order(order: int, arrays: Sequence[Sequence[int]]) -> str:
    lines = [f"Order N={order}", f"Stored arrays: {len(arrays)}"]
    if not arrays:
        lines.append("No stored arrays.")
        return "\n".join(lines)

    endpoints = Counter((array[0], array[-1]) for array in arrays)
    lines.append(f"Unique endpoint pairs: {len(endpoints)}")
    lines.append(
        "Most common endpoints: "
        + ", ".join(f"({left},{right}) x{count}" for (left, right), count in endpoints.most_common(5))
    )

    for shift in dyadic_shifts(order):
        odd_counts = Counter()
        sign_counts = Counter()
        max_abs_counts = Counter()

        for array in arrays:
            differences = [array[index + shift] - array[index] for index in range(order - shift)]
            odd_counts[sum(value & 1 for value in differences)] += 1
            sign_counts[(sum(value > 0 for value in differences), sum(value < 0 for value in differences))] += 1
            max_abs_counts[max(abs(value) for value in differences)] += 1

        lines.append(
            f"Shift {shift}: odd-counts {odd_counts.most_common(3)}; "
            f"sign-balance {sign_counts.most_common(3)}; "
            f"max-abs {max_abs_counts.most_common(3)}"
        )

        if order % 2 == 0 and shift == order // 2:
            parity = shift % 2
            violations = 0
            for array in arrays:
                differences = [array[index + shift] - array[index] for index in range(shift)]
                odd_count = sum(value & 1 for value in differences)
                if odd_count % 2 != parity:
                    violations += 1
            lines.append(
                f"  Half-shift parity check: expected odd-count parity {parity}; violations {violations}"
            )

    return "\n".join(lines)


def main_entry(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_dir = args.db_dir.resolve()

    if args.orders:
        orders = args.orders
    else:
        orders = [summary.order for summary in main.summarize_dataset(db_dir)]

    reports = []
    for order in orders:
        arrays = main.read_arrays_for_order(order, db_dir)
        reports.append(analyze_order(order, arrays))

    print("\n\n".join(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
