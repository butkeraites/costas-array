"""Every array shipped in db/ must actually be a Costas array.

This is the test that matters most in this repository. The database is
third-party data (see db/SOURCE.md); re-deriving the defining property on
every CI run is what lets the repo make claims about it.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from costas_generate import canonical, essential_set, is_costas  # noqa: E402

DB_DIR = ROOT_DIR / "db"

# Orders for which no Costas array is known. The smallest two, 32 and 33, are
# a long-standing open problem.
ORDERS_WITH_NONE_KNOWN = {
    32, 33, 43, 48, 49, 54, 63, 73, 74, 83, 84, 85, 89, 90, 91, 92, 93, 97,
}


def _order_of(path: Path) -> int:
    return int(re.search(r"N=(\d+)", path.name).group(1))


def _load(path: Path) -> list[tuple[int, ...]] | None:
    """Arrays in a db file, or None when the file records 'no Costas arrays'."""
    rows = [r for r in path.read_text().splitlines() if r.strip()]
    if any(c.isalpha() for r in rows for c in r):
        return None
    return [tuple(int(v) for v in r.split()) for r in rows]


def _db_files() -> list[Path]:
    return sorted(DB_DIR.glob("Costas_essen*_N=*.txt"), key=_order_of)


class DatabaseIntegrityTests(unittest.TestCase):
    def test_database_is_present(self) -> None:
        self.assertGreater(len(_db_files()), 50, "db/ looks empty or unreadable")

    def test_every_array_is_costas(self) -> None:
        checked = 0
        for path in _db_files():
            order = _order_of(path)
            arrays = _load(path)
            if arrays is None:
                continue
            for index, arr in enumerate(arrays, start=1):
                with self.subTest(order=order, row=index):
                    self.assertEqual(
                        len(arr), order,
                        f"{path.name} row {index}: length {len(arr)} != N={order}")
                    self.assertEqual(
                        sorted(arr), list(range(1, order + 1)),
                        f"{path.name} row {index}: not a permutation of 1..{order}")
                    self.assertTrue(
                        is_costas(arr),
                        f"{path.name} row {index}: repeated displacement vector")
                checked += 1
        self.assertGreater(checked, 9000, f"only {checked} arrays checked")

    def test_no_duplicate_orbits_within_an_order(self) -> None:
        """The 'essential set' claim: one representative per D4 orbit."""
        for path in _db_files():
            arrays = _load(path)
            if arrays is None:
                continue
            canonicals = [canonical(a) for a in arrays]
            with self.subTest(order=_order_of(path)):
                self.assertEqual(
                    len(canonicals), len(set(canonicals)),
                    f"{path.name} lists two arrays from the same D4 orbit")

    def test_orders_with_none_known_are_recorded_as_empty(self) -> None:
        for path in _db_files():
            order = _order_of(path)
            is_empty = _load(path) is None
            with self.subTest(order=order):
                self.assertEqual(
                    is_empty, order in ORDERS_WITH_NONE_KNOWN,
                    f"{path.name}: emptiness disagrees with the known-orders table")


class GeneratorAgreesWithDatabaseTests(unittest.TestCase):
    """The generator is independent code; where it claims coverage, it must
    agree exactly. See db/SOURCE.md for where coverage currently stops."""

    EXHAUSTIVE_LIMIT = 7

    def test_reproduces_database_exactly_up_to_exhaustive_limit(self) -> None:
        for order in range(2, self.EXHAUSTIVE_LIMIT + 1):
            path = DB_DIR / f"Costas_essense_N={order}.txt"
            if not path.exists():
                continue
            shipped = {canonical(a) for a in (_load(path) or [])}
            generated = {canonical(a) for a in essential_set(order, self.EXHAUSTIVE_LIMIT)}
            with self.subTest(order=order):
                self.assertEqual(
                    generated, shipped,
                    f"order {order}: generator and database disagree")

    def test_generator_output_is_always_valid(self) -> None:
        for order in range(2, 13):
            for arr in essential_set(order, self.EXHAUSTIVE_LIMIT):
                with self.subTest(order=order):
                    self.assertTrue(is_costas(arr))


if __name__ == "__main__":
    unittest.main()
