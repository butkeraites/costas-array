from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Sequence


@dataclass
class DomainResult:
    status: str
    allowed_rows: list[list[int]]


def allowed_rows_by_column(order: int, assignments: Sequence[tuple[int, int]]) -> DomainResult:
    fixed_by_column = {column: row for column, row in assignments}
    fixed_rows = {row for _column, row in assignments}
    allowed = []
    for column in range(1, order + 1):
        if column in fixed_by_column:
            allowed.append([fixed_by_column[column]])
        else:
            allowed.append([row for row in range(1, order + 1) if row not in fixed_rows])

    first_row = fixed_by_column.get(1)
    last_row = fixed_by_column.get(order)
    if first_row is not None:
        if first_row > (order + 1) // 2:
            return DomainResult(status="infeasible", allowed_rows=allowed)
        if last_row is not None and not (first_row <= last_row <= order + 1 - first_row):
            return DomainResult(status="infeasible", allowed_rows=allowed)

        min_column = first_row
        max_column = order + 1 - first_row
        for column in range(1, order + 1):
            if min_column <= column <= max_column:
                continue
            restricted = [row for row in allowed[column - 1] if row not in (1, order)]
            if not restricted:
                return DomainResult(status="infeasible", allowed_rows=allowed)
            allowed[column - 1] = restricted

    for rows in allowed:
        if not rows:
            return DomainResult(status="infeasible", allowed_rows=allowed)
    return DomainResult(status="ok", allowed_rows=allowed)


def endpoint_window_starts(order: int, radius: int) -> list[int]:
    if order < 4 or radius <= 0:
        return []

    last_start = order - 3
    starts = set()
    for start in range(1, min(radius, last_start) + 1):
        starts.add(start)
    for start in range(max(1, last_start - radius + 1), last_start + 1):
        starts.add(start)
    return sorted(starts)


def is_consecutive_window4_costas(rows: Sequence[int]) -> bool:
    if len(rows) != 4:
        raise ValueError("window4 check expects exactly four rows")
    if len(set(rows)) != 4:
        return False

    d1 = rows[1] - rows[0]
    d2 = rows[2] - rows[1]
    d3 = rows[3] - rows[2]
    if len({d1, d2, d3}) != 3:
        return False

    e1 = rows[2] - rows[0]
    e2 = rows[3] - rows[1]
    return e1 != e2


def iter_consecutive_window4_feasible_tuples(
    allowed_rows: Sequence[Sequence[int]], start: int
) -> Iterator[tuple[int, int, int, int]]:
    left_rows = allowed_rows[start - 1]
    middle_left_rows = allowed_rows[start]
    middle_right_rows = allowed_rows[start + 1]
    right_rows = allowed_rows[start + 2]

    for row1 in left_rows:
        for row2 in middle_left_rows:
            if row2 == row1:
                continue
            d1 = row2 - row1
            for row3 in middle_right_rows:
                if row3 in (row1, row2):
                    continue
                d2 = row3 - row2
                if d2 == d1:
                    continue
                e1 = row3 - row1
                for row4 in right_rows:
                    if row4 in (row1, row2, row3):
                        continue
                    d3 = row4 - row3
                    if d3 in (d1, d2):
                        continue
                    e2 = row4 - row2
                    if e2 == e1:
                        continue
                    yield (row1, row2, row3, row4)


def iter_consecutive_window4_forbidden_tuples(
    allowed_rows: Sequence[Sequence[int]], start: int
) -> Iterator[tuple[int, int, int, int]]:
    left_rows = allowed_rows[start - 1]
    middle_left_rows = allowed_rows[start]
    middle_right_rows = allowed_rows[start + 1]
    right_rows = allowed_rows[start + 2]

    for row1 in left_rows:
        for row2 in middle_left_rows:
            if row2 == row1:
                continue
            for row3 in middle_right_rows:
                if row3 in (row1, row2):
                    continue
                for row4 in right_rows:
                    if row4 in (row1, row2, row3):
                        continue
                    rows = (row1, row2, row3, row4)
                    if not is_consecutive_window4_costas(rows):
                        yield rows
