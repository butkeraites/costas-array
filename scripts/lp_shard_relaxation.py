from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from time import time
from typing import Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main
from local_window4 import (
    allowed_rows_by_column,
    endpoint_window_starts,
    iter_consecutive_window4_feasible_tuples,
)


try:
    from ortools.linear_solver import pywraplp
except ImportError as exc:  # pragma: no cover - exercised in integration environments
    raise SystemExit(
        "lp relaxation requires ortools; install dependencies with 'python3 -m pip install -r requirements.txt'"
    ) from exc


@dataclass
class RelaxationResult:
    status: str
    solver_status: str
    variable_count: int
    constraint_count: int
    wall_time_seconds: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Solve a shard-aware LP relaxation for Costas arrays."
    )
    parser.add_argument("order", type=int, help="Order N to study.")
    parser.add_argument(
        "--assign",
        action="append",
        default=[],
        metavar="COLUMN=ROW",
        help="Fix one or more 1-based endpoint or shard coordinates.",
    )
    parser.add_argument(
        "--widths",
        default="1,2,3,4",
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
        help="Optional 4-column window layer; 'endpoints' only adds windows near the two ends.",
    )
    parser.add_argument(
        "--quad-radius",
        type=main.positive_int,
        default=2,
        help="Number of consecutive 4-column windows to add from each endpoint.",
    )
    parser.add_argument(
        "--time-limit",
        type=main.positive_float,
        default=60.0,
        help="Wall-clock time limit in seconds.",
    )
    parser.add_argument(
        "--forbidden-patterns",
        type=Path,
        help="Optional JSON file mapping start_column to a list of globally forbidden 4-column tuples.",
    )
    parser.add_argument(
        "--clique-cuts",
        type=Path,
        help="Optional JSON file containing lists of maximal conflict cliques to bind with hyper-cuts.",
    )
    return parser


def parse_width_spec(raw: str, order: int) -> list[int]:
    spec = raw.strip().lower()
    if spec == "short4":
        return [width for width in (1, 2, 3, 4) if width < order]
    if spec == "dyadic":
        widths = []
        width = 1
        while width < order:
            widths.append(width)
            width *= 2
        return widths
    if spec == "all":
        return list(range(1, order))

    widths = []
    seen = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            raise ValueError("width list contains an empty token")
        width = int(token)
        if not 1 <= width < order:
            raise ValueError(f"width {width} is outside 1..{order - 1}")
        if width not in seen:
            seen.add(width)
            widths.append(width)
    return widths


def solver_status_name(status: int) -> str:
    names = {
        pywraplp.Solver.OPTIMAL: "OPTIMAL",
        pywraplp.Solver.FEASIBLE: "FEASIBLE",
        pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
        pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
        pywraplp.Solver.ABNORMAL: "ABNORMAL",
        pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    }
    return names.get(status, f"UNKNOWN_{status}")


def solve_relaxation(
    order: int,
    *,
    widths: Sequence[int],
    assignments: Sequence[tuple[int, int]],
    solver_name: str,
    time_limit_seconds: float,
    triangle_mode: str = "consecutive",
    quad_mode: str = "none",
    quad_radius: int = 2,
    forbidden_patterns_path: Path | None = None,
    clique_cuts_path: Path | None = None,
) -> RelaxationResult:
    domain_result = allowed_rows_by_column(order, assignments)
    if domain_result.status == "infeasible":
        return RelaxationResult(
            status="infeasible",
            solver_status="DOMAIN_INFEASIBLE",
            variable_count=0,
            constraint_count=0,
            wall_time_seconds=0.0,
        )

    solver = pywraplp.Solver.CreateSolver(solver_name)
    if solver is None:
        raise RuntimeError(f"unable to create OR-Tools solver {solver_name}")
    solver.SetTimeLimit(int(time_limit_seconds * 1000.0))
    solver.SetNumThreads(1)

    started = time()
    allowed = domain_result.allowed_rows

    x: dict[tuple[int, int], pywraplp.Variable] = {}
    for column in range(1, order + 1):
        for row in allowed[column - 1]:
            x[(column, row)] = solver.NumVar(0.0, 1.0, f"x_c{column}_r{row}")

    constraint_count = 0

    for column in range(1, order + 1):
        constraint = solver.Constraint(1.0, 1.0, f"column_{column}")
        for row in allowed[column - 1]:
            constraint.SetCoefficient(x[(column, row)], 1.0)
        constraint_count += 1

    for row in range(1, order + 1):
        constraint = solver.Constraint(1.0, 1.0, f"row_{row}")
        for column in range(1, order + 1):
            variable = x.get((column, row))
            if variable is not None:
                constraint.SetCoefficient(variable, 1.0)
        constraint_count += 1

    y_by_pair: dict[tuple[int, int], list[tuple[int, int, pywraplp.Variable]]] = {}
    y_vars: dict[tuple[int, int, int, int], pywraplp.Variable] = {}
    y_by_delta: dict[tuple[int, int], list[pywraplp.Variable]] = {}

    for width in widths:
        for left in range(1, order - width + 1):
            right = left + width
            pair_entries = []
            for left_row in allowed[left - 1]:
                for right_row in allowed[right - 1]:
                    if left_row == right_row:
                        continue
                    variable = solver.NumVar(
                        0.0,
                        1.0,
                        f"y_w{width}_c{left}_r{left_row}_c{right}_r{right_row}",
                    )
                    y_vars[(left, width, left_row, right_row)] = variable
                    pair_entries.append((left_row, right_row, variable))
                    delta = right_row - left_row
                    y_by_delta.setdefault((width, delta), []).append(variable)
            y_by_pair[(left, width)] = pair_entries

            for left_row in allowed[left - 1]:
                constraint = solver.Constraint(0.0, 0.0, f"left_marginal_c{left}_w{width}_r{left_row}")
                for candidate_left, _candidate_right, variable in pair_entries:
                    if candidate_left == left_row:
                        constraint.SetCoefficient(variable, 1.0)
                constraint.SetCoefficient(x[(left, left_row)], -1.0)
                constraint_count += 1

            for right_row in allowed[right - 1]:
                constraint = solver.Constraint(0.0, 0.0, f"right_marginal_c{right}_w{width}_r{right_row}")
                for _candidate_left, candidate_right, variable in pair_entries:
                    if candidate_right == right_row:
                        constraint.SetCoefficient(variable, 1.0)
                constraint.SetCoefficient(x[(right, right_row)], -1.0)
                constraint_count += 1

    for width in widths:
        for delta in range(-(order - 1), order):
            if delta == 0:
                continue
            variables = y_by_delta.get((width, delta))
            if not variables:
                continue
            constraint = solver.Constraint(-solver.infinity(), 1.0, f"unique_w{width}_d{delta}")
            for variable in variables:
                constraint.SetCoefficient(variable, 1.0)
            constraint_count += 1

    if (order & 1) == 0 and order > 6:
        half = order // 2
        quadrants = [
            ("left_top", range(1, half + 1), range(1, half + 1)),
            ("left_bottom", range(1, half + 1), range(half + 1, order + 1)),
            ("right_top", range(half + 1, order + 1), range(1, half + 1)),
            ("right_bottom", range(half + 1, order + 1), range(half + 1, order + 1)),
        ]
        for name, columns, rows in quadrants:
            constraint = solver.Constraint(1.0, solver.infinity(), f"quadrant_{name}")
            for column in columns:
                for row in rows:
                    variable = x.get((column, row))
                    if variable is not None:
                        constraint.SetCoefficient(variable, 1.0)
            constraint_count += 1

    if order >= 6:
        mirror_vars = []
        for width in (1, 2):
            if width not in widths:
                continue
            for delta in range(1, order):
                positive = y_by_delta.get((width, delta))
                negative = y_by_delta.get((width, -delta))
                if not positive or not negative:
                    continue
                mirror = solver.NumVar(0.0, 1.0, f"mirror_w{width}_d{delta}")
                left_constraint = solver.Constraint(-solver.infinity(), 0.0, f"mirror_pos_w{width}_d{delta}")
                left_constraint.SetCoefficient(mirror, 1.0)
                for variable in positive:
                    left_constraint.SetCoefficient(variable, -1.0)
                constraint_count += 1

                right_constraint = solver.Constraint(-solver.infinity(), 0.0, f"mirror_neg_w{width}_d{delta}")
                right_constraint.SetCoefficient(mirror, 1.0)
                for variable in negative:
                    right_constraint.SetCoefficient(variable, -1.0)
                constraint_count += 1

                mirror_vars.append(mirror)

        if mirror_vars:
            constraint = solver.Constraint(1.0, solver.infinity(), "mirror_pair_exists")
            for variable in mirror_vars:
                constraint.SetCoefficient(variable, 1.0)
            constraint_count += 1

    triangle_patterns: list[tuple[int, int]] = []
    if triangle_mode == "consecutive":
        triangle_patterns = [(1, 2)]
    elif triangle_mode == "window4":
        triangle_patterns = [(1, 2), (1, 3), (2, 3)]

    for offset_middle, offset_right in triangle_patterns:
        if offset_middle not in widths or offset_right not in widths or (offset_right - offset_middle) not in widths:
            raise ValueError(
                f"triangle mode {triangle_mode} requires widths "
                f"{offset_middle}, {offset_right - offset_middle}, and {offset_right}"
            )

        for left in range(1, order - offset_right + 1):
            middle = left + offset_middle
            right = left + offset_right
            z_by_01: dict[tuple[int, int], list[pywraplp.Variable]] = {}
            z_by_12: dict[tuple[int, int], list[pywraplp.Variable]] = {}
            z_by_02: dict[tuple[int, int], list[pywraplp.Variable]] = {}

            for left_row in allowed[left - 1]:
                for middle_row in allowed[middle - 1]:
                    if left_row == middle_row:
                        continue
                    for right_row in allowed[right - 1]:
                        if right_row in (left_row, middle_row):
                            continue
                        variable = solver.NumVar(
                            0.0,
                            1.0,
                            f"z_c{left}_r{left_row}_c{middle}_r{middle_row}_c{right}_r{right_row}",
                        )
                        z_by_01.setdefault((left_row, middle_row), []).append(variable)
                        z_by_12.setdefault((middle_row, right_row), []).append(variable)
                        z_by_02.setdefault((left_row, right_row), []).append(variable)

            for left_row in allowed[left - 1]:
                for middle_row in allowed[middle - 1]:
                    if left_row == middle_row:
                        continue
                    variable = y_vars[(left, offset_middle, left_row, middle_row)]
                    constraint = solver.Constraint(
                        0.0,
                        0.0,
                        f"tri01_c{left}_o{offset_middle}_{left_row}_{middle_row}",
                    )
                    for z_variable in z_by_01.get((left_row, middle_row), []):
                        constraint.SetCoefficient(z_variable, 1.0)
                    constraint.SetCoefficient(variable, -1.0)
                    constraint_count += 1

            for middle_row in allowed[middle - 1]:
                for right_row in allowed[right - 1]:
                    if middle_row == right_row:
                        continue
                    variable = y_vars[(middle, offset_right - offset_middle, middle_row, right_row)]
                    constraint = solver.Constraint(
                        0.0,
                        0.0,
                        f"tri12_c{middle}_o{offset_right - offset_middle}_{middle_row}_{right_row}",
                    )
                    for z_variable in z_by_12.get((middle_row, right_row), []):
                        constraint.SetCoefficient(z_variable, 1.0)
                    constraint.SetCoefficient(variable, -1.0)
                    constraint_count += 1

            for left_row in allowed[left - 1]:
                for right_row in allowed[right - 1]:
                    if left_row == right_row:
                        continue
                    variable = y_vars[(left, offset_right, left_row, right_row)]
                    constraint = solver.Constraint(
                        0.0,
                        0.0,
                        f"tri02_c{left}_o{offset_right}_{left_row}_{right_row}",
                    )
                    for z_variable in z_by_02.get((left_row, right_row), []):
                        constraint.SetCoefficient(z_variable, 1.0)
                    constraint.SetCoefficient(variable, -1.0)
                    constraint_count += 1

    if quad_mode == "endpoints":
        if not {1, 2, 3}.issubset(widths):
            raise ValueError("quad mode endpoints requires widths 1, 2, and 3")

        for start in endpoint_window_starts(order, quad_radius):
            q_by_col_row: list[dict[int, list[pywraplp.Variable]]] = [{}, {}, {}, {}]
            q_by_pair01: dict[tuple[int, int], list[pywraplp.Variable]] = {}
            q_by_pair12: dict[tuple[int, int], list[pywraplp.Variable]] = {}
            q_by_pair23: dict[tuple[int, int], list[pywraplp.Variable]] = {}
            q_by_pair02: dict[tuple[int, int], list[pywraplp.Variable]] = {}
            q_by_pair13: dict[tuple[int, int], list[pywraplp.Variable]] = {}
            q_by_pair03: dict[tuple[int, int], list[pywraplp.Variable]] = {}

            for row1, row2, row3, row4 in iter_consecutive_window4_feasible_tuples(allowed, start):
                variable = solver.NumVar(0.0, 1.0, f"q_c{start}_r{row1}_{row2}_{row3}_{row4}")
                q_by_col_row[0].setdefault(row1, []).append(variable)
                q_by_col_row[1].setdefault(row2, []).append(variable)
                q_by_col_row[2].setdefault(row3, []).append(variable)
                q_by_col_row[3].setdefault(row4, []).append(variable)
                q_by_pair01.setdefault((row1, row2), []).append(variable)
                q_by_pair12.setdefault((row2, row3), []).append(variable)
                q_by_pair23.setdefault((row3, row4), []).append(variable)
                q_by_pair02.setdefault((row1, row3), []).append(variable)
                q_by_pair13.setdefault((row2, row4), []).append(variable)
                q_by_pair03.setdefault((row1, row4), []).append(variable)

            column_rows = [
                allowed[start - 1],
                allowed[start],
                allowed[start + 1],
                allowed[start + 2],
            ]
            for offset, rows in enumerate(column_rows):
                column = start + offset
                for row in rows:
                    constraint = solver.Constraint(0.0, 0.0, f"quad_col_c{column}_r{row}")
                    for variable in q_by_col_row[offset].get(row, []):
                        constraint.SetCoefficient(variable, 1.0)
                    constraint.SetCoefficient(x[(column, row)], -1.0)
                    constraint_count += 1

            pair_specs = [
                (q_by_pair01, start, 1),
                (q_by_pair12, start + 1, 1),
                (q_by_pair23, start + 2, 1),
                (q_by_pair02, start, 2),
                (q_by_pair13, start + 1, 2),
                (q_by_pair03, start, 3),
            ]
            for pair_map, left, width in pair_specs:
                right = left + width
                for left_row in allowed[left - 1]:
                    for right_row in allowed[right - 1]:
                        if left_row == right_row:
                            continue
                        constraint = solver.Constraint(
                            0.0,
                            0.0,
                            f"quad_pair_c{left}_w{width}_{left_row}_{right_row}",
                        )
                        for variable in pair_map.get((left_row, right_row), []):
                            constraint.SetCoefficient(variable, 1.0)
                        constraint.SetCoefficient(
                            y_vars[(left, width, left_row, right_row)],
                            -1.0,
                        )
                        constraint_count += 1

    if forbidden_patterns_path is not None and forbidden_patterns_path.is_file():
        import json
        with forbidden_patterns_path.open(encoding="utf-8") as handle:
            forbidden_data = json.load(handle)
        for start_str, tuples in forbidden_data.items():
            start = int(start_str)
            for rows in tuples:
                constraint = solver.Constraint(-solver.infinity(), 3.0, f"forbid_c{start}_{rows[0]}_{rows[1]}_{rows[2]}_{rows[3]}")
                for i, row in enumerate(rows):
                    var = x.get((start + i, row))
                    if var is not None:
                        constraint.SetCoefficient(var, 1.0)
                constraint_count += 1

    objective = solver.Objective()
    objective.SetMinimization()

    if clique_cuts_path is not None and clique_cuts_path.is_file():
        with clique_cuts_path.open(encoding="utf-8") as handle:
            clique_data = json.load(handle)
        for i, clique in enumerate(clique_data):
            clique_sum_ct = solver.Constraint(-solver.infinity(), 1.0, f"clique_{i}_sum")
            for j, pA in enumerate(clique):
                y_var = solver.NumVar(0.0, 1.0, f"clique_{i}_p_{j}")
                clique_sum_ct.SetCoefficient(y_var, 1.0)
                
                force_ct = solver.Constraint(-3.0, solver.infinity(), f"clique_{i}_p_{j}_force")
                force_ct.SetCoefficient(y_var, 1.0)
                for c_off, ri in enumerate(pA[1:]):
                    try:
                        v = x[(pA[0] - 1 + c_off + 1, ri)]
                        force_ct.SetCoefficient(v, -1.0)
                    except KeyError:
                        pass
                        
    status_code = solver.Solve()
    solver_status = solver_status_name(status_code)
    if status_code in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        status = "feasible"
    elif status_code == pywraplp.Solver.INFEASIBLE:
        status = "infeasible"
    else:
        status = "unknown"

    return RelaxationResult(
        status=status,
        solver_status=solver_status,
        variable_count=solver.NumVariables(),
        constraint_count=constraint_count,
        wall_time_seconds=round(time() - started, 3),
    )


def main_entry(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assignments = main.parse_assignment_specs(args.assign, order=args.order)
    widths = parse_width_spec(args.widths, args.order)
    result = solve_relaxation(
        args.order,
        widths=widths,
        assignments=assignments,
        solver_name=args.solver,
        time_limit_seconds=args.time_limit,
        triangle_mode=args.triangles,
        quad_mode=args.quads,
        quad_radius=args.quad_radius,
        forbidden_patterns_path=args.forbidden_patterns,
        clique_cuts_path=args.clique_cuts,
    )

    print(f"status={result.status}")
    print(f"solver_status={result.solver_status}")
    print(f"order={args.order}")
    print(f"widths={','.join(str(width) for width in widths)}")
    print(f"triangles={args.triangles}")
    print(f"quads={args.quads}")
    if assignments:
        print("assignments=" + " ".join(f"{column}={row}" for column, row in assignments))
    print(f"variables={result.variable_count}")
    print(f"constraints={result.constraint_count}")
    print(f"wall_time_seconds={result.wall_time_seconds}")

    if result.status == "feasible":
        return 0
    if result.status == "infeasible":
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main_entry())
