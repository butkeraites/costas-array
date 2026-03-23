from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Iterator, Sequence


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_DB_DIR = ROOT_DIR / "db"
ORDER_FILE_RE = re.compile(r"^Costas_essense_N=(\d+)\.txt$")
NO_ARRAYS_MARKER = "No Costas arrays."


@dataclass(frozen=True)
class OrderFile:
    order: int
    path: Path


@dataclass(frozen=True)
class OrderSummary:
    order: int
    path: Path
    array_count: int


@dataclass
class ValidationResult:
    order: int
    checked_arrays: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def is_permutation(array: Sequence[int]) -> bool:
    n = len(array)
    return set(array) == set(range(1, n + 1))


def is_costas_array(array: Sequence[int]) -> bool:
    """Return True when ``array`` is a 1-based Costas permutation."""
    if not is_permutation(array):
        return False

    vectors = set()
    for left in range(len(array) - 1):
        for right in range(left + 1, len(array)):
            vector = (right - left, array[right] - array[left])
            if vector in vectors:
                return False
            vectors.add(vector)

    return True


def parse_array_line(raw_line: str, *, path: Path, line_number: int) -> list[int] | None:
    stripped = raw_line.strip()
    if not stripped or stripped == NO_ARRAYS_MARKER:
        return None

    try:
        return [int(value) for value in stripped.split()]
    except ValueError as exc:
        raise ValueError(f"{path.name}:{line_number} contains a non-integer value") from exc


def discover_order_files(db_dir: Path) -> list[OrderFile]:
    if not db_dir.is_dir():
        raise FileNotFoundError(f"database directory not found: {db_dir}")

    order_files = []
    for path in db_dir.iterdir():
        match = ORDER_FILE_RE.fullmatch(path.name)
        if match:
            order_files.append(OrderFile(order=int(match.group(1)), path=path))

    if not order_files:
        raise FileNotFoundError(f"no Costas order files found in: {db_dir}")

    return sorted(order_files, key=lambda item: item.order)


def order_file_path(order: int, db_dir: Path) -> Path:
    path = db_dir / f"Costas_essense_N={order}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"order {order} is not available in {db_dir}")
    return path


def iter_arrays_from_file(path: Path) -> Iterator[tuple[int, list[int]]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            array = parse_array_line(raw_line, path=path, line_number=line_number)
            if array is not None:
                yield line_number, array


def read_arrays_for_order(order: int, db_dir: Path) -> list[list[int]]:
    path = order_file_path(order, db_dir)
    return [array for _, array in iter_arrays_from_file(path)]


def summarize_dataset(db_dir: Path) -> list[OrderSummary]:
    summaries = []
    for order_file in discover_order_files(db_dir):
        array_count = sum(1 for _line_number, _array in iter_arrays_from_file(order_file.path))
        summaries.append(
            OrderSummary(order=order_file.order, path=order_file.path, array_count=array_count)
        )
    return summaries


def validate_order(order: int, db_dir: Path) -> ValidationResult:
    path = order_file_path(order, db_dir)
    result = ValidationResult(order=order)
    seen = set()

    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            try:
                array = parse_array_line(raw_line, path=path, line_number=line_number)
            except ValueError as exc:
                result.issues.append(str(exc))
                continue

            if array is None:
                continue

            result.checked_arrays += 1

            if len(array) != order:
                result.issues.append(
                    f"{path.name}:{line_number} expected {order} values, found {len(array)}"
                )
                continue

            if not is_permutation(array):
                result.issues.append(
                    f"{path.name}:{line_number} is not a permutation of 1..{order}"
                )
                continue

            array_key = tuple(array)
            if array_key in seen:
                result.issues.append(f"{path.name}:{line_number} duplicates an earlier array")
                continue
            seen.add(array_key)

            if not is_costas_array(array):
                result.issues.append(f"{path.name}:{line_number} is not a valid Costas array")

    return result


def validate_dataset(db_dir: Path, order: int | None = None) -> list[ValidationResult]:
    if order is not None:
        return [validate_order(order, db_dir)]

    return [validate_order(order_file.order, db_dir) for order_file in discover_order_files(db_dir)]


def render_summary(summaries: Sequence[OrderSummary], *, show_all: bool) -> str:
    total_arrays = sum(summary.array_count for summary in summaries)
    empty_orders = [summary.order for summary in summaries if summary.array_count == 0]
    non_empty = [summary for summary in summaries if summary.array_count > 0]

    lines = [
        f"Dataset: {summaries[0].path.parent}",
        f"Orders scanned: {len(summaries)}",
        f"Non-empty orders: {len(non_empty)}",
        f"Empty orders: {len(empty_orders)}",
        f"Total arrays: {total_arrays}",
    ]

    if non_empty:
        lines.append("")
        lines.append("Most populated orders:")
        for summary in sorted(non_empty, key=lambda item: (-item.array_count, item.order))[:5]:
            lines.append(f"  N={summary.order}: {summary.array_count}")

    if empty_orders:
        lines.append("")
        lines.append("Orders with no stored arrays:")
        lines.append("  " + ", ".join(str(order) for order in empty_orders))

    if show_all:
        lines.append("")
        lines.append("Per-order counts:")
        for summary in summaries:
            marker = " (empty)" if summary.array_count == 0 else ""
            lines.append(f"  N={summary.order}: {summary.array_count}{marker}")

    return "\n".join(lines)


def render_order(order: int, arrays: Sequence[Sequence[int]], *, limit: int | None) -> str:
    lines = [f"Order N={order}", f"Stored arrays: {len(arrays)}"]

    if not arrays:
        lines.append("No Costas arrays are stored for this order.")
        return "\n".join(lines)

    displayed = arrays if limit is None else arrays[:limit]
    for index, array in enumerate(displayed, start=1):
        lines.append(f"{index:>4}: {' '.join(str(value) for value in array)}")

    if limit is not None and limit < len(arrays):
        lines.append(f"Displayed {len(displayed)} of {len(arrays)} arrays.")

    return "\n".join(lines)


def render_validation(results: Sequence[ValidationResult], *, db_dir: Path) -> tuple[int, str]:
    total_arrays = sum(result.checked_arrays for result in results)
    invalid = [result for result in results if not result.is_valid]

    if invalid:
        lines = [
            f"Validation failed for {len(invalid)} order(s) in {db_dir}.",
            f"Arrays checked before reporting: {total_arrays}",
        ]
        for result in invalid:
            lines.append("")
            lines.append(f"Order N={result.order}:")
            for issue in result.issues:
                lines.append(f"  - {issue}")
        return 1, "\n".join(lines)

    if len(results) == 1:
        result = results[0]
        return 0, (
            f"Validated order N={result.order}: "
            f"{result.checked_arrays} arrays checked, no problems found."
        )

    return 0, (
        f"Validated {len(results)} orders in {db_dir}: "
        f"{total_arrays} arrays checked, no problems found."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explore and validate the Costas array dataset."
    )
    parser.add_argument(
        "--db-dir",
        type=Path,
        default=DEFAULT_DB_DIR,
        help="Directory containing Costas_essense_N=<n>.txt files.",
    )

    subparsers = parser.add_subparsers(dest="command")

    summary_parser = subparsers.add_parser(
        "summary", help="Show dataset coverage and array counts."
    )
    summary_parser.add_argument(
        "--all",
        action="store_true",
        help="Include counts for every discovered order.",
    )

    show_parser = subparsers.add_parser(
        "show", help="Print stored arrays for a specific order."
    )
    show_parser.add_argument("order", type=positive_int, help="Order N to inspect.")
    show_parser.add_argument(
        "--limit",
        type=positive_int,
        help="Maximum number of arrays to print.",
    )

    validate_parser = subparsers.add_parser(
        "validate", help="Validate the whole dataset or a single order."
    )
    validate_parser.add_argument(
        "order",
        nargs="?",
        type=positive_int,
        help="Optional single order N to validate.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_dir = args.db_dir.resolve()

    try:
        if args.command in (None, "summary"):
            summaries = summarize_dataset(db_dir)
            print(render_summary(summaries, show_all=getattr(args, "all", False)))
            return 0

        if args.command == "show":
            arrays = read_arrays_for_order(args.order, db_dir)
            print(render_order(args.order, arrays, limit=args.limit))
            return 0

        if args.command == "validate":
            results = validate_dataset(db_dir, order=args.order)
            exit_code, message = render_validation(results, db_dir=db_dir)
            print(message)
            return exit_code
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
