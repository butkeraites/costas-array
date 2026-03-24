from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from itertools import combinations
from math import comb
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


@dataclass(frozen=True)
class SearchAttempt:
    backend: str
    status: str
    detail: str
    example: list[int] | None = None


@dataclass(frozen=True)
class SearchResult:
    order: int
    status: str
    time_limit_seconds: float
    backend: str
    attempts: list[SearchAttempt] = field(default_factory=list)
    example: list[int] | None = None


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive number")
    return parsed


def parse_assignment_specs(raw_assignments: Sequence[str], *, order: int) -> list[tuple[int, int]]:
    assignments_by_column: dict[int, int] = {}
    columns_by_row: dict[int, int] = {}

    for raw_assignment in raw_assignments:
        match = re.fullmatch(r"(\d+)=(\d+)", raw_assignment.strip())
        if match is None:
            raise ValueError(
                f"invalid assignment '{raw_assignment}'; expected COLUMN=ROW using 1-based coordinates"
            )

        column = int(match.group(1))
        row = int(match.group(2))
        if not 1 <= column <= order:
            raise ValueError(f"column {column} is outside 1..{order}")
        if not 1 <= row <= order:
            raise ValueError(f"row {row} is outside 1..{order}")

        previous_row = assignments_by_column.get(column)
        if previous_row is not None and previous_row != row:
            raise ValueError(
                f"column {column} was assigned both row {previous_row} and row {row}"
            )
        previous_column = columns_by_row.get(row)
        if previous_column is not None and previous_column != column:
            raise ValueError(
                f"row {row} was assigned to both column {previous_column} and column {column}"
            )

        assignments_by_column[column] = row
        columns_by_row[row] = column

    return sorted(assignments_by_column.items())


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


def matches_assignments(array: Sequence[int], assignments: Sequence[tuple[int, int]]) -> bool:
    return all(array[column - 1] == row for column, row in assignments)


def augment_array_by_one(array: Sequence[int], insert_column: int, insert_row: int) -> list[int]:
    augmented = []
    for index, value in enumerate(array):
        if index == insert_column:
            augmented.append(insert_row)
        augmented.append(value + (1 if value >= insert_row else 0))

    if insert_column == len(array):
        augmented.append(insert_row)

    return augmented


def delete_positions(array: Sequence[int], positions: Sequence[int]) -> list[int]:
    removed = set(positions)
    remaining = [value for index, value in enumerate(array) if index not in removed]
    removed_values = sorted(array[index] for index in removed)

    compressed = []
    for value in remaining:
        shift = sum(1 for removed_value in removed_values if removed_value < value)
        compressed.append(value - shift)

    return compressed


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


def search_via_database(
    order: int,
    db_dir: Path,
    *,
    assignments: Sequence[tuple[int, int]] = (),
) -> SearchAttempt | None:
    path = db_dir / f"Costas_essense_N={order}.txt"
    if not path.is_file():
        return None

    arrays = read_arrays_for_order(order, db_dir)
    if not arrays:
        return None

    if assignments:
        for array in arrays:
            if matches_assignments(array, assignments):
                return SearchAttempt(
                    backend="database",
                    status="found",
                    detail=(
                        f"repository already stores an example for order {order} "
                        "that matches the fixed assignments"
                    ),
                    example=array,
                )
        return SearchAttempt(
            backend="database",
            status="unknown",
            detail=(
                f"repository stores {len(arrays)} example(s) for order {order}, "
                "but none satisfy the fixed assignments"
            ),
        )

    return SearchAttempt(
        backend="database",
        status="found",
        detail=f"repository already stores {len(arrays)} example(s) for order {order}",
        example=arrays[0],
    )


def search_via_neighbors(
    order: int,
    db_dir: Path,
    *,
    candidate_budget: int,
    assignments: Sequence[tuple[int, int]] = (),
) -> SearchAttempt:
    checked = 0
    details = []

    previous_path = db_dir / f"Costas_essense_N={order - 1}.txt"
    if previous_path.is_file():
        previous_arrays = read_arrays_for_order(order - 1, db_dir)
        if not previous_arrays:
            details.append(f"stored order {order - 1} has no recorded arrays to augment")
        else:
            total_candidates = len(previous_arrays) * order * order
            if total_candidates <= candidate_budget:
                for array in previous_arrays:
                    for insert_column in range(order):
                        for insert_row in range(1, order + 1):
                            checked += 1
                            candidate = augment_array_by_one(array, insert_column, insert_row)
                            if is_costas_array(candidate) and matches_assignments(
                                candidate, assignments
                            ):
                                return SearchAttempt(
                                    backend="neighbors",
                                    status="found",
                                    detail=(
                                        f"found a witness after checking {checked} one-point augmentations "
                                        f"from stored order {order - 1}"
                                    ),
                                    example=candidate,
                                )
                details.append(
                    f"checked {total_candidates} one-point augmentations from stored order {order - 1}"
                )
            else:
                details.append(
                    f"skipped {total_candidates} one-point augmentations from order {order - 1} "
                    f"(budget {candidate_budget})"
                )

    for gap in (1, 2):
        higher_order = order + gap
        higher_path = db_dir / f"Costas_essense_N={higher_order}.txt"
        if not higher_path.is_file():
            continue

        higher_arrays = read_arrays_for_order(higher_order, db_dir)
        if not higher_arrays:
            continue

        delete_choices = comb(higher_order, gap)
        total_candidates = len(higher_arrays) * delete_choices
        if total_candidates > candidate_budget:
            details.append(
                f"skipped {total_candidates} deletion candidates from stored order {higher_order} "
                f"(budget {candidate_budget})"
            )
            continue

        for array in higher_arrays:
            for positions in combinations(range(higher_order), gap):
                checked += 1
                candidate = delete_positions(array, positions)
                if is_costas_array(candidate) and matches_assignments(candidate, assignments):
                    return SearchAttempt(
                        backend="neighbors",
                        status="found",
                        detail=(
                            f"found a witness after checking {checked} deletions from "
                            f"stored order {higher_order}"
                        ),
                        example=candidate,
                    )

        details.append(
            f"checked {total_candidates} deletion candidates from stored order {higher_order}"
        )

    if not details:
        details.append("no usable neighboring stored orders were available")

    return SearchAttempt(
        backend="neighbors",
        status="unknown",
        detail="; ".join(details),
    )


def search_costas_array_z3(order: int, *, time_limit_seconds: float) -> SearchAttempt:
    try:
        from z3 import Distinct, Int, Solver, sat, unsat
    except ImportError as exc:
        raise RuntimeError(
            "search requires z3-solver; install dependencies with 'python3 -m pip install -r requirements.txt'"
        ) from exc

    timeout_ms = max(1, int(time_limit_seconds * 1000))
    variables = [Int(f"x_{index}") for index in range(order)]
    solver = Solver()
    solver.set("timeout", timeout_ms)

    for variable in variables:
        solver.add(variable >= 1, variable <= order)

    solver.add(Distinct(variables))

    for distance in range(1, order):
        differences = [variables[index + distance] - variables[index] for index in range(order - distance)]
        if len(differences) > 1:
            solver.add(Distinct(differences))

    # Break simple mirror symmetries to help the search.
    solver.add(variables[0] < variables[-1])
    solver.add(variables[0] <= (order + 1) // 2)

    result = solver.check()
    if result == sat:
        model = solver.model()
        example = [model.evaluate(variable).as_long() for variable in variables]
        return SearchAttempt(
            backend="z3",
            status="found",
            detail=f"Z3 found a witness within {time_limit_seconds:.1f}s",
            example=example,
        )

    if result == unsat:
        return SearchAttempt(
            backend="z3",
            status="unsat",
            detail=f"Z3 proved infeasibility within {time_limit_seconds:.1f}s",
        )

    return SearchAttempt(
        backend="z3",
        status="unknown",
        detail=f"Z3 returned unknown after {time_limit_seconds:.1f}s",
    )


def build_native_solver() -> Path:
    source = ROOT_DIR / "native" / "costas_native.cpp"
    binary = ROOT_DIR / "native" / "costas_native"
    stamp_path = ROOT_DIR / "native" / "costas_native.build.json"
    build_stamp = {
        "system": platform.system(),
        "machine": platform.machine(),
    }

    stamp_matches = False
    if stamp_path.exists():
        try:
            stamp_matches = json.loads(stamp_path.read_text(encoding="utf-8")) == build_stamp
        except json.JSONDecodeError:
            stamp_matches = False

    if binary.exists() and binary.stat().st_mtime >= source.stat().st_mtime and stamp_matches:
        return binary

    subprocess.run(
        [
            "g++",
            "-O3",
            "-std=c++17",
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
    )
    stamp_path.write_text(json.dumps(build_stamp, indent=2), encoding="utf-8")
    return binary


def search_costas_array_native(
    order: int,
    *,
    time_limit_seconds: float,
    assignments: Sequence[tuple[int, int]] = (),
) -> SearchAttempt:
    try:
        binary = build_native_solver()
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"failed to build native solver: {stderr}") from exc

    command = [str(binary), str(order), f"{time_limit_seconds}"]
    command.extend(f"{column}={row}" for column, row in assignments)

    try:
        result = subprocess.run(
            command,
            check=False,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"failed to run native solver: {exc}") from exc

    parsed = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()

    status = parsed.get("status", "unknown")
    nodes = parsed.get("nodes", "0")
    fixed_detail = ""
    if assignments:
        fixed_detail = f" with {len(assignments)} fixed assignment(s)"
    if status == "found":
        example = [int(value) for value in parsed.get("example", "").split()]
        return SearchAttempt(
            backend="native",
            status="found",
            detail=f"native C++ search found a witness after exploring {nodes} nodes{fixed_detail}",
            example=example,
        )

    if status == "unsat":
        return SearchAttempt(
            backend="native",
            status="unsat",
            detail=f"native C++ search proved infeasibility after exploring {nodes} nodes{fixed_detail}",
        )

    return SearchAttempt(
        backend="native",
        status="unknown",
        detail=f"native C++ search returned unknown after exploring {nodes} nodes{fixed_detail}",
    )


def search_costas_array_sat(
    order: int,
    *,
    time_limit_seconds: float,
    cnf_path: Path | None = None,
    keep_cnf: bool = False,
    sat_solver: str = "kissat",
    assignments: Sequence[tuple[int, int]] = (),
    window4_radius: int = 0,
    forbidden_patterns_path: Path | None = None,
    clique_cuts_path: Path | None = None,
) -> SearchAttempt:
    if sat_solver == "cadical":
        from costas_sat import solve_costas_with_cadical

        result = solve_costas_with_cadical(
            order,
            time_limit_seconds=time_limit_seconds,
            cnf_path=cnf_path,
            keep_cnf=keep_cnf,
            assignments=tuple(assignments),
            window4_radius=window4_radius,
            forbidden_patterns_path=forbidden_patterns_path,
            clique_cuts_path=clique_cuts_path,
        )
    else:
        from costas_sat import solve_costas_with_kissat

        result = solve_costas_with_kissat(
            order,
            time_limit_seconds=time_limit_seconds,
            cnf_path=cnf_path,
            keep_cnf=keep_cnf,
            assignments=tuple(assignments),
            window4_radius=window4_radius,
            forbidden_patterns_path=forbidden_patterns_path,
            clique_cuts_path=clique_cuts_path,
        )

    return SearchAttempt(
        backend="sat",
        status=result.status,
        detail=result.detail,
        example=result.example,
    )


def search_costas_array_ortools(order: int, *, time_limit_seconds: float) -> SearchAttempt:
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise RuntimeError(
            "search requires ortools; install dependencies with 'python3 -m pip install -r requirements.txt'"
        ) from exc

    model = cp_model.CpModel()
    variables = [model.new_int_var(0, order - 1, f"x_{index}") for index in range(order)]
    inverse = [model.new_int_var(0, order - 1, f"inv_{index}") for index in range(order)]

    model.add_all_different(variables)
    model.add_inverse(variables, inverse)

    for distance in range(1, order):
        differences = [
            model.new_int_var(-(order - 1), order - 1, f"d_{distance}_{index}")
            for index in range(order - distance)
        ]
        for index, difference in enumerate(differences):
            model.add(difference == variables[index + distance] - variables[index])
        if len(differences) > 1:
            model.add_all_different(differences)

    first = variables[0]
    model.add(first <= variables[-1])
    model.add(first <= (order - 1) - variables[0])
    model.add(first <= (order - 1) - variables[-1])
    model.add(first <= inverse[0])
    model.add(first <= inverse[-1])
    model.add(first <= (order - 1) - inverse[0])
    model.add(first <= (order - 1) - inverse[-1])

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8

    status = solver.solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        example = [solver.value(variable) + 1 for variable in variables]
        return SearchAttempt(
            backend="ortools",
            status="found",
            detail=f"OR-Tools found a witness within {time_limit_seconds:.1f}s",
            example=example,
        )

    if status == cp_model.INFEASIBLE:
        return SearchAttempt(
            backend="ortools",
            status="unsat",
            detail=f"OR-Tools proved infeasibility within {time_limit_seconds:.1f}s",
        )

    return SearchAttempt(
        backend="ortools",
        status="unknown",
        detail=f"OR-Tools returned unknown after {time_limit_seconds:.1f}s",
    )


def search_costas_array(
    order: int,
    db_dir: Path,
    *,
    time_limit_seconds: float,
    backend: str,
    candidate_budget: int,
    assignments: Sequence[tuple[int, int]] = (),
    cnf_path: Path | None = None,
    keep_cnf: bool = False,
    sat_solver: str = "kissat",
    sat_window4_radius: int = 0,
    sat_forbidden_patterns_path: Path | None = None,
    sat_clique_cuts_path: Path | None = None,
) -> SearchResult:
    attempts = []

    database_attempt = search_via_database(order, db_dir, assignments=assignments)
    if database_attempt is not None:
        attempts.append(database_attempt)
        if database_attempt.status == "found":
            return SearchResult(
                order=order,
                status="found",
                time_limit_seconds=time_limit_seconds,
                backend="database",
                attempts=attempts,
                example=database_attempt.example,
            )

    neighbor_attempt = search_via_neighbors(
        order,
        db_dir,
        candidate_budget=candidate_budget,
        assignments=assignments,
    )
    attempts.append(neighbor_attempt)
    if neighbor_attempt.status == "found":
        return SearchResult(
            order=order,
            status="found",
            time_limit_seconds=time_limit_seconds,
            backend="neighbors",
            attempts=attempts,
            example=neighbor_attempt.example,
        )

    solver_attempts = []
    if backend == "z3":
        solver_attempts = [("z3", time_limit_seconds)]
    elif backend == "ortools":
        solver_attempts = [("ortools", time_limit_seconds)]
    elif backend == "native":
        solver_attempts = [("native", time_limit_seconds)]
    elif backend == "sat":
        solver_attempts = [("sat", time_limit_seconds)]
    else:
        native_time = time_limit_seconds * 0.4
        sat_time = time_limit_seconds - native_time
        solver_attempts = [("native", native_time), ("sat", sat_time)]

    for solver_name, solver_time in solver_attempts:
        if solver_time <= 0:
            continue

        if solver_name == "ortools":
            attempt = search_costas_array_ortools(order, time_limit_seconds=solver_time)
        elif solver_name == "native":
            attempt = search_costas_array_native(
                order,
                time_limit_seconds=solver_time,
                assignments=assignments,
            )
        elif solver_name == "sat":
            attempt = search_costas_array_sat(
                order,
                time_limit_seconds=solver_time,
                cnf_path=cnf_path,
                keep_cnf=keep_cnf,
                sat_solver=sat_solver,
                assignments=assignments,
                window4_radius=sat_window4_radius,
                forbidden_patterns_path=sat_forbidden_patterns_path,
                clique_cuts_path=sat_clique_cuts_path,
            )
        else:
            attempt = search_costas_array_z3(order, time_limit_seconds=solver_time)

        attempts.append(attempt)
        if attempt.status == "found":
            return SearchResult(
                order=order,
                status="found",
                time_limit_seconds=time_limit_seconds,
                backend=solver_name,
                attempts=attempts,
                example=attempt.example,
            )
        if attempt.status == "unsat":
            return SearchResult(
                order=order,
                status="unsat",
                time_limit_seconds=time_limit_seconds,
                backend=solver_name,
                attempts=attempts,
            )

    return SearchResult(
        order=order,
        status="unknown",
        time_limit_seconds=time_limit_seconds,
        backend=backend,
        attempts=attempts,
    )


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


def render_search(result: SearchResult, *, stored_count: int | None) -> tuple[int, str]:
    lines = [
        f"Search result for N={result.order}",
        f"Time limit: {result.time_limit_seconds:.1f}s",
        f"Winning backend: {result.backend}",
    ]

    if stored_count is None:
        lines.append("Repository status: no local data file for this order")
    else:
        lines.append(f"Repository status: {stored_count} stored array(s)")

    if result.attempts:
        lines.append("Attempts:")
        for attempt in result.attempts:
            lines.append(f"  - {attempt.backend}: {attempt.status} ({attempt.detail})")

    if result.status == "found":
        lines.append("Status: example found")
        lines.append("Example:")
        lines.append("  " + " ".join(str(value) for value in result.example or []))
        return 0, "\n".join(lines)

    if result.status == "unsat":
        lines.append("Status: proved impossible")
        lines.append("The solver reported that no Costas array exists for this order.")
        return 0, "\n".join(lines)

    lines.append("Status: no conclusion")
    lines.append(
        "No example was found and infeasibility was not proved within the requested time limit."
    )
    lines.append(
        "An empty data file in this repository should be treated as 'no stored example', not as a proof."
    )
    return 2, "\n".join(lines)


def export_cnf(
    order: int,
    output_path: Path,
    *,
    assignments: Sequence[tuple[int, int]] = (),
    window4_radius: int = 0,
) -> str:
    from costas_sat import write_costas_cnf

    stats = write_costas_cnf(
        order,
        output_path.resolve(),
        assignments=tuple(assignments),
        window4_radius=window4_radius,
    )
    lines = [
        f"Wrote CNF for N={order} to {stats.path}\n"
        f"Variables: {stats.variable_count}\n"
        f"Clauses: {stats.clause_count}"
    ]
    if assignments:
        lines.append(
            "Assignments: " + " ".join(f"{column}={row}" for column, row in assignments)
        )
    if window4_radius > 0:
        lines.append(f"Window4 endpoint radius: {window4_radius}")
    return "\n".join(lines)


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

    search_parser = subparsers.add_parser(
        "search",
        help="Use Z3 to search for an example or prove infeasibility for one order.",
    )
    search_parser.add_argument("order", type=positive_int, help="Order N to search.")
    search_parser.add_argument(
        "--time-limit",
        type=positive_float,
        default=30.0,
        help="Solver time limit in seconds.",
    )
    search_parser.add_argument(
        "--backend",
        choices=("auto", "native", "ortools", "sat", "z3"),
        default="auto",
        help="Search backend to use after database and neighbor heuristics.",
    )
    search_parser.add_argument(
        "--candidate-budget",
        type=positive_int,
        default=200000,
        help="Maximum number of neighbor-generated candidates to inspect.",
    )
    search_parser.add_argument(
        "--cnf-path",
        type=Path,
        help="Optional path for the generated CNF when using the SAT backend.",
    )
    search_parser.add_argument(
        "--keep-cnf",
        action="store_true",
        help="Keep the generated CNF file when using the SAT backend.",
    )
    search_parser.add_argument(
        "--sat-solver",
        choices=("kissat", "cadical"),
        default="kissat",
        help="External solver to use with the SAT backend.",
    )
    search_parser.add_argument(
        "--assign",
        action="append",
        default=[],
        metavar="COLUMN=ROW",
        help="Fix a 1-based column to a 1-based row for native or SAT subproblems.",
    )
    search_parser.add_argument(
        "--sat-window4-radius",
        type=positive_int,
        default=0,
        help="Add redundant 4-column endpoint clauses to SAT for the first/last k windows.",
    )
    search_parser.add_argument(
        "--sat-forbidden-patterns",
        type=Path,
        help="Optional JSON file mapping start_column to a list of globally forbidden 4-column tuples.",
    )
    search_parser.add_argument(
        "--sat-clique-cuts",
        type=Path,
        help="Optional JSON file containing lists of maximal conflict cliques.",
    )

    export_parser = subparsers.add_parser(
        "export-cnf",
        help="Write a DIMACS CNF encoding for one order.",
    )
    export_parser.add_argument("order", type=positive_int, help="Order N to encode.")
    export_parser.add_argument("output", type=Path, help="Destination .cnf path.")
    export_parser.add_argument(
        "--assign",
        action="append",
        default=[],
        metavar="COLUMN=ROW",
        help="Optional fixed assignments to bake into the CNF.",
    )
    export_parser.add_argument(
        "--sat-window4-radius",
        type=positive_int,
        default=0,
        help="Add redundant 4-column endpoint clauses for the first/last k windows.",
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

        if args.command == "search":
            assignments = parse_assignment_specs(args.assign, order=args.order)
            if assignments and args.backend not in ("auto", "native", "sat"):
                raise ValueError("--assign can only be used with --backend auto, native, or sat")

            path = db_dir / f"Costas_essense_N={args.order}.txt"
            stored_count = None
            if path.is_file():
                stored_count = len(read_arrays_for_order(args.order, db_dir))

            result = search_costas_array(
                args.order,
                db_dir,
                time_limit_seconds=args.time_limit,
                backend=args.backend,
                candidate_budget=args.candidate_budget,
                assignments=assignments,
                cnf_path=args.cnf_path.resolve() if args.cnf_path else None,
                keep_cnf=args.keep_cnf,
                sat_solver=args.sat_solver,
                sat_window4_radius=args.sat_window4_radius,
                sat_forbidden_patterns_path=args.sat_forbidden_patterns,
                sat_clique_cuts_path=args.sat_clique_cuts,
            )
            exit_code, message = render_search(result, stored_count=stored_count)
            print(message)
            return exit_code

        if args.command == "export-cnf":
            assignments = parse_assignment_specs(args.assign, order=args.order)
            print(
                export_cnf(
                    args.order,
                    args.output,
                    assignments=assignments,
                    window4_radius=args.sat_window4_radius,
                )
            )
            return 0
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
