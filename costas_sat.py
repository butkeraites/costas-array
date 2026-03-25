from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path
import shutil
import subprocess
import tempfile

from local_window4 import (
    allowed_rows_by_column,
    endpoint_window_starts,
    iter_consecutive_window4_forbidden_tuples,
)


@dataclass(frozen=True)
class CnfStats:
    order: int
    variable_count: int
    clause_count: int
    path: Path


@dataclass(frozen=True)
class SatResult:
    status: str
    solver: str
    detail: str
    example: list[int] | None = None
    cnf_stats: CnfStats | None = None


def _grid_var(order: int, column: int, row: int) -> int:
    return column * order + row + 1


def _amo_aux_count(size: int) -> int:
    return max(0, size - 1)


def _amo_clause_count(size: int) -> int:
    if size <= 1:
        return 0
    return 2 if size == 2 else (3 * size) - 4


def _count_edge_variables(order: int) -> int:
    total = 0
    for dx in range(1, order):
        for dy in range(-(order - 1), order):
            total += (order - dx) * (order - abs(dy))
    return total


def _count_displacement_aux(order: int) -> int:
    total = 0
    for dx in range(1, order):
        for dy in range(-(order - 1), order):
            placements = (order - dx) * (order - abs(dy))
            total += _amo_aux_count(placements)
    return total


def _count_displacement_clauses(order: int) -> int:
    total = 0
    for dx in range(1, order):
        for dy in range(-(order - 1), order):
            placements = (order - dx) * (order - abs(dy))
            total += (3 * placements) + _amo_clause_count(placements)
    return total


def compute_cnf_stats(order: int, path: Path, *, extra_clause_count: int = 0) -> CnfStats:
    grid_variables = order * order
    row_column_aux = 2 * order * _amo_aux_count(order)
    edge_variables = _count_edge_variables(order)
    displacement_aux = _count_displacement_aux(order)

    row_column_clauses = 2 * order * (1 + _amo_clause_count(order))
    displacement_clauses = _count_displacement_clauses(order)

    upper_half_clauses = order // 2
    first_last_lower_clauses = order * (order + 1) // 2
    first_last_upper_clauses = order * (order - 1) // 2
    transpose_row_one_lower = order * (order - 1) // 2
    transpose_row_one_upper = order * (order - 1) // 2
    transpose_row_n_lower = order * (order - 1) // 2
    transpose_row_n_upper = order * (order - 1) // 2

    return CnfStats(
        order=order,
        variable_count=grid_variables + row_column_aux + edge_variables + displacement_aux,
        clause_count=(
            row_column_clauses
            + displacement_clauses
            + upper_half_clauses
            + first_last_lower_clauses
            + first_last_upper_clauses
            + transpose_row_one_lower
            + transpose_row_one_upper
            + transpose_row_n_lower
            + transpose_row_n_upper
            + extra_clause_count
        ),
        path=path,
    )


def _write_clause(handle, literals: list[int]) -> None:
    handle.write(" ".join(str(literal) for literal in literals))
    handle.write(" 0\n")


def _write_at_most_one(handle, literals: list[int], next_aux: int) -> int:
    size = len(literals)
    if size <= 1:
        return next_aux

    aux_vars = list(range(next_aux, next_aux + size - 1))
    next_aux += size - 1

    _write_clause(handle, [-literals[0], aux_vars[0]])
    for index in range(1, size - 1):
        _write_clause(handle, [-literals[index], aux_vars[index]])
        _write_clause(handle, [-aux_vars[index - 1], aux_vars[index]])
        _write_clause(handle, [-literals[index], -aux_vars[index - 1]])
    _write_clause(handle, [-literals[-1], -aux_vars[-1]])

    return next_aux


def _write_exactly_one(handle, literals: list[int], next_aux: int) -> int:
    _write_clause(handle, literals)
    return _write_at_most_one(handle, literals, next_aux)


def _build_extra_clauses(
    order: int,
    *,
    assignments: tuple[tuple[int, int], ...],
    window4_radius: int,
    forbidden_patterns_path: Path | None = None,
    clique_cuts_path: Path | None = None,
) -> list[list[int]]:
    domain_result = allowed_rows_by_column(order, assignments)
    if domain_result.status == "infeasible":
        raise ValueError("the fixed assignments already violate the symmetry domain")

    allowed = domain_result.allowed_rows
    assignment_clauses = [
        [_grid_var(order, column - 1, row - 1)] for column, row in assignments
    ]
    domain_clauses = []
    for column in range(1, order + 1):
        allowed_rows = set(allowed[column - 1])
        for row in range(1, order + 1):
            if row not in allowed_rows:
                domain_clauses.append([-_grid_var(order, column - 1, row - 1)])

    window_clauses = []
    if window4_radius > 0:
        for start in endpoint_window_starts(order, window4_radius):
            for row1, row2, row3, row4 in iter_consecutive_window4_forbidden_tuples(
                allowed, start
            ):
                window_clauses.append(
                    [
                        -_grid_var(order, start - 1, row1 - 1),
                        -_grid_var(order, start, row2 - 1),
                        -_grid_var(order, start + 1, row3 - 1),
                        -_grid_var(order, start + 2, row4 - 1),
                    ]
                )

    forbidden_clauses = []
    if forbidden_patterns_path is not None and forbidden_patterns_path.is_file():
        import json
        with forbidden_patterns_path.open(encoding="utf-8") as handle:
            forbidden_data = json.load(handle)
        for start_str, tuples in forbidden_data.items():
            start = int(start_str)
            for rows in tuples:
                forbidden_clauses.append(
                    [
                        -_grid_var(order, start - 1, rows[0] - 1),
                        -_grid_var(order, start, rows[1] - 1),
                        -_grid_var(order, start + 1, rows[2] - 1),
                        -_grid_var(order, start + 2, rows[3] - 1),
                    ]
                )

    clique_clauses = []
    if clique_cuts_path is not None and clique_cuts_path.is_file():
        import json
        with clique_cuts_path.open(encoding="utf-8") as handle:
            clique_data = json.load(handle)
        for clique in clique_data:
            for i in range(len(clique)):
                pA = clique[i]
                for j in range(i + 1, len(clique)):
                    pB = clique[j]
                    literals = set()
                    for c_off, ri in enumerate(pA[1:]):
                        literals.add(-_grid_var(order, pA[0] - 1 + c_off, ri - 1))
                    for c_off, ri in enumerate(pB[1:]):
                        literals.add(-_grid_var(order, pB[0] - 1 + c_off, ri - 1))
                    clique_clauses.append(sorted(literals))

    return assignment_clauses + domain_clauses + window_clauses + forbidden_clauses + clique_clauses


def write_costas_cnf(
    order: int,
    output_path: Path,
    *,
    assignments: tuple[tuple[int, int], ...] = (),
    window4_radius: int = 0,
    forbidden_patterns_path: Path | None = None,
    clique_cuts_path: Path | None = None,
) -> CnfStats:
    extra_clauses = _build_extra_clauses(
        order,
        assignments=assignments,
        window4_radius=window4_radius,
        forbidden_patterns_path=forbidden_patterns_path,
        clique_cuts_path=clique_cuts_path,
    )
    stats = compute_cnf_stats(order, output_path, extra_clause_count=len(extra_clauses))

    grid_variables = order * order
    row_column_aux_start = grid_variables + 1
    edge_var_start = row_column_aux_start + (2 * order * _amo_aux_count(order))
    displacement_aux_start = edge_var_start + _count_edge_variables(order)

    next_row_column_aux = row_column_aux_start
    next_edge_var = edge_var_start
    next_displacement_aux = displacement_aux_start

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(f"p cnf {stats.variable_count} {stats.clause_count}\n")

        for column in range(order):
            literals = [_grid_var(order, column, row) for row in range(order)]
            next_row_column_aux = _write_exactly_one(handle, literals, next_row_column_aux)

        for row in range(order):
            literals = [_grid_var(order, column, row) for column in range(order)]
            next_row_column_aux = _write_exactly_one(handle, literals, next_row_column_aux)

        for row in range(order // 2, order):
            _write_clause(handle, [-_grid_var(order, 0, row)])

        for first_row in range(order):
            for last_row in range(first_row + 1):
                _write_clause(
                    handle,
                    [
                        -_grid_var(order, 0, first_row),
                        -_grid_var(order, order - 1, last_row),
                    ],
                )
            for last_row in range(order - first_row, order):
                _write_clause(
                    handle,
                    [
                        -_grid_var(order, 0, first_row),
                        -_grid_var(order, order - 1, last_row),
                    ],
                )

        for first_row in range(order):
            for first_row_column in range(first_row):
                _write_clause(
                    handle,
                    [
                        -_grid_var(order, 0, first_row),
                        -_grid_var(order, first_row_column, 0),
                    ],
                )
            for first_row_column in range(order - first_row, order):
                _write_clause(
                    handle,
                    [
                        -_grid_var(order, 0, first_row),
                        -_grid_var(order, first_row_column, 0),
                    ],
                )
            for last_row_column in range(first_row):
                _write_clause(
                    handle,
                    [
                        -_grid_var(order, 0, first_row),
                        -_grid_var(order, last_row_column, order - 1),
                    ],
                )
            for last_row_column in range(order - first_row, order):
                _write_clause(
                    handle,
                    [
                        -_grid_var(order, 0, first_row),
                        -_grid_var(order, last_row_column, order - 1),
                    ],
                )

        for dx in range(1, order):
            for dy in range(-(order - 1), order):
                edge_literals = []
                row_start = max(0, -dy)
                row_stop = min(order, order - dy)
                for column in range(order - dx):
                    for row in range(row_start, row_stop):
                        start_var = _grid_var(order, column, row)
                        end_var = _grid_var(order, column + dx, row + dy)
                        edge_var = next_edge_var
                        next_edge_var += 1
                        edge_literals.append(edge_var)

                        _write_clause(handle, [-edge_var, start_var])
                        _write_clause(handle, [-edge_var, end_var])
                        _write_clause(handle, [-start_var, -end_var, edge_var])

                next_displacement_aux = _write_at_most_one(
                    handle, edge_literals, next_displacement_aux
                )

        for clause in extra_clauses:
            _write_clause(handle, clause)

    return stats


def solve_costas_with_kissat(
    order: int,
    *,
    time_limit_seconds: float,
    cnf_path: Path | None = None,
    keep_cnf: bool = False,
    assignments: tuple[tuple[int, int], ...] = (),
    window4_radius: int = 0,
    forbidden_patterns_path: Path | None = None,
    clique_cuts_path: Path | None = None,
) -> SatResult:
    solver_path = shutil.which("kissat")
    if solver_path is None:
        raise RuntimeError("kissat is not installed; install it with 'brew install kissat'")

    managed_temp = False
    if cnf_path is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="costas-cnf-"))
        cnf_path = temp_dir / f"costas_{order}.cnf"
        managed_temp = True

    domain_result = allowed_rows_by_column(order, assignments)
    if domain_result.status == "infeasible":
        return SatResult(
            status="unsat",
            solver="kissat",
            detail="kissat skipped because the fixed assignments already violate the symmetry domain",
        )

    stats = write_costas_cnf(
        order,
        cnf_path,
        assignments=assignments,
        window4_radius=window4_radius,
        forbidden_patterns_path=forbidden_patterns_path,
        clique_cuts_path=clique_cuts_path,
    )

    try:
        result = subprocess.run(
            [
                solver_path,
                "-q",
                f"--time={max(1, ceil(time_limit_seconds))}",
                str(cnf_path),
            ],
            cwd=cnf_path.parent,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        if managed_temp and not keep_cnf:
            try:
                cnf_path.unlink(missing_ok=True)
                cnf_path.parent.rmdir()
            except OSError:
                pass

    if result.returncode == 10:
        positives = set()
        for line in result.stdout.splitlines():
            if not line.startswith("v "):
                continue
            for token in line.split()[1:]:
                literal = int(token)
                if literal > 0:
                    positives.add(literal)

        example = []
        for column in range(order):
            for row in range(order):
                if _grid_var(order, column, row) in positives:
                    example.append(row + 1)
                    break

        return SatResult(
            status="found",
            solver="kissat",
            detail=(
                f"kissat found a witness from {stats.variable_count} variables "
                f"and {stats.clause_count} clauses"
            ),
            example=example,
            cnf_stats=stats,
        )

    if result.returncode == 20:
        return SatResult(
            status="unsat",
            solver="kissat",
            detail=(
                f"kissat proved infeasibility for a CNF with {stats.variable_count} variables "
                f"and {stats.clause_count} clauses"
            ),
            cnf_stats=stats,
        )

    return SatResult(
        status="unknown",
        solver="kissat",
        detail=(
            f"kissat returned unknown on a CNF with {stats.variable_count} variables "
            f"and {stats.clause_count} clauses"
        ),
        cnf_stats=stats,
    )


def solve_costas_with_cadical(
    order: int,
    *,
    time_limit_seconds: float,
    cnf_path: Path | None = None,
    keep_cnf: bool = False,
    assignments: tuple[tuple[int, int], ...] = (),
    window4_radius: int = 0,
    forbidden_patterns_path: Path | None = None,
    clique_cuts_path: Path | None = None,
) -> SatResult:
    solver_path = shutil.which("cadical")
    if solver_path is None:
        raise RuntimeError("cadical is not installed; install it with 'brew install cadical'")

    managed_temp = False
    if cnf_path is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="costas-cnf-"))
        cnf_path = temp_dir / f"costas_{order}.cnf"
        managed_temp = True

    domain_result = allowed_rows_by_column(order, assignments)
    if domain_result.status == "infeasible":
        return SatResult(
            status="unsat",
            solver="cadical",
            detail="cadical skipped because the fixed assignments already violate the symmetry domain",
        )

    stats = write_costas_cnf(
        order,
        cnf_path,
        assignments=assignments,
        window4_radius=window4_radius,
        forbidden_patterns_path=forbidden_patterns_path,
        clique_cuts_path=clique_cuts_path,
    )

    try:
        result = subprocess.run(
            [
                solver_path,
                "-q",
                "-t",
                str(max(1, ceil(time_limit_seconds))),
                str(cnf_path),
            ],
            cwd=cnf_path.parent,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        if managed_temp and not keep_cnf:
            try:
                cnf_path.unlink(missing_ok=True)
                cnf_path.parent.rmdir()
            except OSError:
                pass

    if "s SATISFIABLE" in result.stdout:
        positives = set()
        for line in result.stdout.splitlines():
            if not line.startswith("v "):
                continue
            for token in line.split()[1:]:
                literal = int(token)
                if literal > 0:
                    positives.add(literal)

        example = []
        for column in range(order):
            for row in range(order):
                if _grid_var(order, column, row) in positives:
                    example.append(row + 1)
                    break

        return SatResult(
            status="found",
            solver="cadical",
            detail=(
                f"cadical found a witness from {stats.variable_count} variables "
                f"and {stats.clause_count} clauses"
            ),
            example=example,
            cnf_stats=stats,
        )

    if "s UNSATISFIABLE" in result.stdout:
        return SatResult(
            status="unsat",
            solver="cadical",
            detail=(
                f"cadical proved infeasibility for a CNF with {stats.variable_count} variables "
                f"and {stats.clause_count} clauses"
            ),
            cnf_stats=stats,
        )

    return SatResult(
        status="unknown",
        solver="cadical",
        detail=(
            f"cadical returned unknown on a CNF with {stats.variable_count} variables "
            f"and {stats.clause_count} clauses"
        ),
        cnf_stats=stats,
    )
