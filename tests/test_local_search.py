"""Tests for the stochastic witness-search engine (costas_local_search).

Covers the energy invariants that must hold for the search to be correct, and
confirms it solves a small order. It deliberately does NOT assert solving large
orders: local search is empirically unable to reach high orders for Costas
arrays (see docs/dyadic_obstruction_findings.md).
"""
from __future__ import annotations

from pathlib import Path
import random
import sys
import unittest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import costas_local_search as ls
import main


class EnergyInvariants(unittest.TestCase):
    def test_zero_energy_iff_costas(self):
        for n in (8, 12, 16):
            arr = main.read_arrays_for_order(n, ROOT_DIR / "db")[0]
            self.assertEqual(ls.CostasEnergy(arr).energy, 0)
            self.assertTrue(main.is_costas_array(arr))

    def test_swap_delta_matches_apply(self):
        rng = random.Random(0)
        for n in (12, 24):
            state = ls.CostasEnergy(list(range(1, n + 1)))
            for _ in range(300):
                p, q = rng.randrange(n), rng.randrange(n)
                predicted = state.swap_delta(p, q)
                before = state.energy
                after = state.apply_swap(p, q)
                state.apply_swap(p, q)  # revert
                self.assertEqual(after - before, predicted)
                state.apply_swap(rng.randrange(n), rng.randrange(n))

    def test_apply_swap_is_self_inverse(self):
        rng = random.Random(1)
        n = 16
        state = ls.CostasEnergy(list(range(1, n + 1)))
        baseline = state.energy
        for _ in range(100):
            p, q = rng.randrange(n), rng.randrange(n)
            state.apply_swap(p, q)
            state.apply_swap(p, q)
        self.assertEqual(state.energy, baseline)
        self.assertEqual(state.perm, list(range(1, n + 1)))


class SolvesSmallOrder(unittest.TestCase):
    def test_finds_costas_array_for_small_n(self):
        # N=9 is comfortably within the reach of local search.
        perm, energy, _ = ls.search(9, seed=0, steps_per_restart=3000, max_restarts=300)
        self.assertEqual(energy, 0)
        self.assertTrue(main.is_costas_array(perm))


if __name__ == "__main__":
    unittest.main()
