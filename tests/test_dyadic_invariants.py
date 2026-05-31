"""Regression tests for the dyadic-invariant findings (see
docs/dyadic_obstruction_findings.md).

These lock in two things:
  1. The three provable necessary laws hold for every stored Costas array.
  2. The rigorous negative result: no single-layer residue lemma can prune an
     N=32 endpoint shard (every residue class is reachable, all moduli tested).
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main
from scripts.mine_dyadic_invariants import (
    dyadic_shifts,
    law_half_shift_parity,
    law_shift1_parity,
    law_telescoping,
    reachable_residues_mod,
)


class ProvableLawsHoldOnDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = ROOT_DIR / "db"
        orders = [s.order for s in main.summarize_dataset(db)]
        cls.arrays = [(o, a) for o in orders for a in main.read_arrays_for_order(o, db)]
        assert cls.arrays, "expected stored arrays"

    def test_telescoping(self):
        for order, a in self.arrays:
            for h in dyadic_shifts(order):
                self.assertTrue(law_telescoping(a, h), msg=f"N={order} h={h}")

    def test_shift1_parity(self):
        for order, a in self.arrays:
            self.assertTrue(law_shift1_parity(a), msg=f"N={order} {a}")

    def test_half_shift_parity(self):
        for order, a in self.arrays:
            self.assertTrue(law_half_shift_parity(a), msg=f"N={order} {a}")


class SingleLayerResidueLemmaCannotPruneN32(unittest.TestCase):
    def test_all_residues_reachable(self):
        for m in (2, 4, 8, 16, 32):
            for h in dyadic_shifts(32):
                reach = reachable_residues_mod(32, h, m)
                self.assertEqual(
                    reach,
                    set(range(m)),
                    msg=f"mod {m} shift {h}: only {sorted(reach)} reachable",
                )


# Witness refuting Target A (the Dyadic Injectivity Obstruction): a permutation
# of [32] whose dyadic layers {1,2,4,8,16} are all collision-free but which is
# NOT a full Costas array. See docs/dyadic_obstruction_findings.md.
DYADIC_WITNESS_N32 = [
    17, 4, 28, 6, 15, 30, 24, 16, 20, 11, 19, 29, 2, 5, 25, 13,
    18, 32, 12, 10, 22, 1, 3, 31, 8, 21, 14, 9, 27, 23, 7, 26,
]


def _layer_distinct(perm, h):
    diffs = [perm[i + h] - perm[i] for i in range(len(perm) - h)]
    return len(set(diffs)) == len(diffs)


class DyadicInjectivityObstructionIsFalse(unittest.TestCase):
    def test_witness_is_permutation(self):
        self.assertEqual(sorted(DYADIC_WITNESS_N32), list(range(1, 33)))

    def test_witness_dyadic_feasible_but_not_costas(self):
        for h in dyadic_shifts(32):
            self.assertTrue(_layer_distinct(DYADIC_WITNESS_N32, h), msg=f"shift {h}")
        self.assertFalse(main.is_costas_array(DYADIC_WITNESS_N32))


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
