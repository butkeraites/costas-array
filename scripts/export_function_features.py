from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
from typing import Iterable, Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export normalized function/secant features for stored Costas arrays."
    )
    parser.add_argument(
        "--db-dir",
        type=Path,
        default=ROOT_DIR / "db",
        help="Directory containing Costas_essense_N=<n>.txt files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional CSV output path. Prints to stdout if omitted.",
    )
    parser.add_argument(
        "orders",
        nargs="*",
        type=int,
        help="Optional orders to inspect. Defaults to all non-empty stored orders.",
    )
    return parser


def dyadic_shifts(order: int) -> list[int]:
    shifts = []
    shift = 1
    while shift < order:
        shifts.append(shift)
        shift *= 2
    return shifts


def mirror_pair_count(array: Sequence[int], width: int) -> int:
    differences = [array[index + width] - array[index] for index in range(len(array) - width)]
    values = set(differences)
    count = 0
    for difference in values:
        if difference > 0 and -difference in values:
            count += 1
    return count


def second_differences(array: Sequence[int]) -> list[int]:
    return [
        array[index + 2] - 2 * array[index + 1] + array[index]
        for index in range(len(array) - 2)
    ]


def sign_change_count(values: Iterable[int]) -> int:
    signs = [1 if value > 0 else -1 if value < 0 else 0 for value in values]
    signs = [sign for sign in signs if sign != 0]
    if len(signs) < 2:
        return 0
    return sum(1 for left, right in zip(signs, signs[1:]) if left != right)


def secant_features(order: int, array: Sequence[int]) -> dict[str, float | int]:
    row: dict[str, float | int] = {
        "order": order,
        "first_row": array[0],
        "last_row": array[-1],
        "first_row_norm": array[0] / order,
        "last_row_norm": array[-1] / order,
        "mirror_width_1": mirror_pair_count(array, 1) if order >= 2 else 0,
        "mirror_width_2": mirror_pair_count(array, 2) if order >= 3 else 0,
        "curvature_sign_changes": sign_change_count(second_differences(array)),
    }

    for shift in dyadic_shifts(order):
        differences = [array[index + shift] - array[index] for index in range(order - shift)]
        positive_count = sum(value > 0 for value in differences)
        odd_count = sum(value & 1 for value in differences)
        row[f"shift_{shift}_mean"] = sum(differences) / len(differences)
        row[f"shift_{shift}_min"] = min(differences)
        row[f"shift_{shift}_max"] = max(differences)
        row[f"shift_{shift}_positive"] = positive_count
        row[f"shift_{shift}_negative"] = len(differences) - positive_count
        row[f"shift_{shift}_odd"] = odd_count
        row[f"shift_{shift}_sign_changes"] = sign_change_count(differences)

    return row


def iter_feature_rows(db_dir: Path, orders: Sequence[int] | None = None) -> list[dict[str, float | int]]:
    rows = []
    if orders is None:
        summaries = [summary for summary in main.summarize_dataset(db_dir) if summary.array_count > 0]
        orders = [summary.order for summary in summaries]

    for order in orders:
        for array in main.read_arrays_for_order(order, db_dir):
            rows.append(secant_features(order, array))

    return rows


def main_entry(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_dir = args.db_dir.resolve()
    rows = iter_feature_rows(db_dir, orders=args.orders or None)
    if not rows:
        print("No rows exported.", file=sys.stderr)
        return 1

    fieldnames = sorted(
        {key for row in rows for key in row.keys()},
        key=lambda name: (name.count("_"), name),
    )

    if args.output:
        output_path = args.output.resolve()
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} feature rows to {output_path}")
        return 0

    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
