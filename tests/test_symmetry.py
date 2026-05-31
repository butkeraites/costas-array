"""Tests for the dihedral symmetry module, and a soundness regression for the
SAT encoding's hand-coded symmetry-breaking constraints.

Background (docs/dyadic_obstruction_findings.md): full canonical-form symmetry
breaking was investigated as a speedup lever, but measurement showed the
existing hand-coded scheme already reduces the search to within ~1.5x of the
theoretical optimum (the number of dihedral orbits). The valuable, durable
artifacts are therefore (a) the verified symmetry module and (b) a regression
guaranteeing the existing SAT symmetry clauses never become *unsound* (i.e.
never drop every member of an orbit, which would risk a false UNSAT).
"""
from __future__ import annotations

from itertools import permutations
from pathlib import Path
import sys
import unittest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import costas_symmetry as cs
import main


def is_costas(perm) -> bool:
    n = len(perm)
    return all(len({perm[i + h] - perm[i] for i in range(n - h)}) == (n - h) for h in range(1, n))


class DihedralGroup(unittest.TestCase):
    def test_generators_are_involutions(self):
        for n in (6, 9, 12):
            p = list(main.read_arrays_for_order(n, ROOT_DIR / "db")[0])
            self.assertEqual(cs.reverse(cs.reverse(p)), tuple(p))
            self.assertEqual(cs.complement(cs.complement(p)), tuple(p))
            self.assertEqual(cs.inverse(cs.inverse(p)), tuple(p))

    def test_orbit_divides_eight_and_preserves_costas(self):
        for n in range(5, 9):
            for p in permutations(range(1, n + 1)):
                if not is_costas(p):
                    continue
                orbit = cs.dihedral_orbit(p)
                self.assertEqual(8 % len(orbit), 0, msg=f"orbit {len(orbit)} for {p}")
                for image in orbit:
                    self.assertTrue(is_costas(image), msg=f"{image} not Costas")

    def test_canonical_idempotent_and_orbit_invariant(self):
        for n in range(5, 9):
            for p in permutations(range(1, n + 1)):
                if not is_costas(p):
                    continue
                can = cs.to_canonical(p)
                self.assertEqual(cs.to_canonical(can), can)
                for image in cs.dihedral_orbit(p):
                    self.assertEqual(cs.to_canonical(image), can)

    def test_grid_cell_maps_are_bijections(self):
        n = 8
        for name, cells in cs.grid_cell_maps(n).items():
            flat = [c * n + r for (c, r) in cells]
            self.assertEqual(sorted(flat), list(range(n * n)), msg=name)


def _kept_by_sat_symmetry(perm) -> bool:
    """Exact replica of the symmetry-breaking clauses in costas_sat.write_costas_cnf
    (1-indexed perm). Used only to assert soundness of that scheme."""
    n = len(perm)
    fr = perm[0] - 1   # 0-based row of the column-1 dot
    lr = perm[-1] - 1  # 0-based row of the column-N dot
    if fr in range(n // 2, n):                      # upper-half (complement)
        return False
    if lr in range(fr + 1) or lr in range(n - fr, n):  # first/last band (reversal)
        return False
    c1 = perm.index(1)   # 0-based column holding value 1 (top row)
    cn = perm.index(n)   # 0-based column holding value N (bottom row)
    forbidden = set(range(fr)) | set(range(n - fr, n))  # transpose row constraints
    if c1 in forbidden or cn in forbidden:
        return False
    return True


class ExistingSatSymmetrySchemeIsSound(unittest.TestCase):
    """The hand-coded SAT symmetry clauses must keep at least one representative
    of every dihedral orbit; otherwise a satisfiable instance could be reported
    UNSAT."""

    def test_keeps_at_least_one_per_orbit(self):
        for n in range(5, 10):
            costas = [p for p in permutations(range(1, n + 1)) if is_costas(p)]
            all_orbits = {cs.to_canonical(p) for p in costas}
            kept_orbits = {cs.to_canonical(p) for p in costas if _kept_by_sat_symmetry(p)}
            self.assertEqual(kept_orbits, all_orbits, msg=f"N={n}: an orbit was fully dropped")


if __name__ == "__main__":
    unittest.main()
