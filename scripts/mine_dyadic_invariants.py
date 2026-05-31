"""Mine and verify dyadic difference-layer invariants for Costas arrays.

Two goals, both aimed at the open order N=32:

1. VERIFY provable necessary conditions (laws) across every stored array, so a
   regression catches any mis-statement, and report — for a target order — which
   of them are *boundary-checkable* (decidable from a fixed prefix/suffix of
   columns) and therefore usable to prune shards.

2. DISCOVER candidate invariants: scan a battery of per-shift functionals across
   all stored arrays and flag those that are exactly determined by N (theorem
   candidates) versus merely clustered (conjectures / heuristics).

A "law" here is a statement provable from the permutation + Costas structure. A
"candidate" is an empirical regularity in the (curated, non-exhaustive) dataset
and must be treated as a conjecture until proved.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main


def dyadic_shifts(order: int) -> list[int]:
    shifts = []
    shift = 1
    while shift < order:
        shifts.append(shift)
        shift *= 2
    return shifts


def layer(array, h):
    return [array[i + h] - array[i] for i in range(len(array) - h)]


# ---------------------------------------------------------------------------
# Provable laws: each returns True iff the array satisfies it. A law that ever
# returns False on a real Costas array is mis-stated.
# ---------------------------------------------------------------------------

def law_telescoping(array, h) -> bool:
    """Sum of the width-h layer equals (sum of last h values) - (sum of first h)."""
    return sum(layer(array, h)) == sum(array[-h:]) - sum(array[:h])


def law_shift1_parity(array) -> bool:
    """#odd consecutive differences has the parity of (f(1)+f(N))."""
    diffs = layer(array, 1)
    return (sum(d & 1 for d in diffs)) % 2 == (array[0] + array[-1]) % 2


def law_half_shift_parity(array) -> bool:
    """Even N, h=N/2: #odd diffs over the first N/2 pairs ≡ (N/2) mod 2."""
    n = len(array)
    if n % 2:
        return True
    h = n // 2
    diffs = [array[i + h] - array[i] for i in range(h)]
    return (sum(d & 1 for d in diffs)) % 2 == h % 2


def verify_laws(arrays_by_order) -> list[str]:
    out = ["== Provable-law verification (0 violations expected) =="]
    tele = s1 = hs = 0
    n_even = 0
    for order, arrays in arrays_by_order.items():
        for a in arrays:
            for h in dyadic_shifts(order):
                if not law_telescoping(a, h):
                    tele += 1
            if not law_shift1_parity(a):
                s1 += 1
            if order % 2 == 0:
                n_even += 1
                if not law_half_shift_parity(a):
                    hs += 1
    out.append(f"telescoping S_h identity: {tele} violations")
    out.append(f"shift-1 #odd ≡ endpoint parity: {s1} violations")
    out.append(f"half-shift parity (even N): {hs}/{n_even} violations")
    return out


# ---------------------------------------------------------------------------
# Boundary-sum reachability: can the width-h layer (N-h distinct nonzero diffs
# in [-(N-1), N-1]) sum to a required target with the right residue mod m?
# When the first h and last h columns are fixed, the target sum is determined,
# so this becomes a boundary-checkable necessary condition.
# ---------------------------------------------------------------------------

def reachable_residues_mod(order: int, h: int, m: int) -> set[int]:
    """Residues mod m attainable as the sum of (N-h) DISTINCT nonzero diffs in
    [-(N-1),N-1]. (No row-domain restriction — an upper bound on reachability.)"""
    k = order - h
    candidates = [d for d in range(-(order - 1), order) if d != 0]
    # DP over (count chosen) x (running residue mod m); reachability only.
    reach = [[False] * m for _ in range(k + 1)]
    reach[0][0] = True
    for d in candidates:
        r = d % m
        # iterate count downward so each diff is used at most once (0/1 knapsack)
        for c in range(k - 1, -1, -1):
            row = reach[c]
            nxt = reach[c + 1]
            for res in range(m):
                if row[res]:
                    nxt[(res + r) % m] = True
    return {res for res in range(m) if reach[k][res]}


def analyze_target_order_boundary(order: int, m: int = 4) -> list[str]:
    """For each dyadic shift, report which target residues are reachable. If all
    residues are reachable for every shift, boundary-sum lemmas prune nothing."""
    out = [f"== Boundary-sum reachability for N={order} (mod {m}) =="]
    for h in dyadic_shifts(order):
        res = reachable_residues_mod(order, h, m)
        full = set(range(m))
        verdict = "ALL residues reachable -> no pruning" if res == full else f"reachable={sorted(res)} -> CAN prune"
        out.append(f"shift {h}: {verdict}")
    return out


# ---------------------------------------------------------------------------
# Candidate-invariant scan: per-shift functionals, grouped by N. Report spread.
# ---------------------------------------------------------------------------

def scan_candidates(arrays_by_order) -> list[str]:
    out = ["== Candidate per-shift functional spread (by N; tight => conjecture) =="]
    # functional name -> order -> set of values
    funcs = {
        "n_odd": lambda L, n, h: sum(d & 1 for d in L),
        "n_pos": lambda L, n, h: sum(d > 0 for d in L),
        "sum_abs": lambda L, n, h: sum(abs(d) for d in L),
        "max_abs": lambda L, n, h: max(abs(d) for d in L),
        "n_res0_mod4": lambda L, n, h: sum(d % 4 == 0 for d in L),
    }
    for fname, f in funcs.items():
        tight = []
        for order in sorted(arrays_by_order):
            if order % 2:
                continue
            arrays = arrays_by_order[order]
            if len(arrays) < 5:
                continue  # need a few samples to claim tightness
            for h in dyadic_shifts(order):
                vals = {f(layer(a, h), order, h) for a in arrays}
                if len(vals) == 1:
                    tight.append(f"  {fname} shift {h} N={order}: CONSTANT = {next(iter(vals))} (n={len(arrays)})")
        if tight:
            out.append(f"[{fname}] exactly-constant cases:")
            out.extend(tight)
        else:
            out.append(f"[{fname}] no exactly-constant cases (varies within every N)")
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mine/verify dyadic invariants for Costas arrays.")
    p.add_argument("--db-dir", type=Path, default=ROOT_DIR / "db")
    p.add_argument("--target", type=int, default=32, help="Open order to test for boundary pruning.")
    p.add_argument("--mod", type=int, default=4, help="Modulus for boundary-sum reachability.")
    return p


def main_entry(argv=None) -> int:
    args = build_parser().parse_args(argv)
    db = args.db_dir.resolve()
    orders = [s.order for s in main.summarize_dataset(db)]
    arrays_by_order = {o: main.read_arrays_for_order(o, db) for o in orders}
    total = sum(len(v) for v in arrays_by_order.values())

    print(f"Stored arrays: {total} across {len([o for o in orders if arrays_by_order[o]])} non-empty orders\n")
    print("\n".join(verify_laws(arrays_by_order)))
    print()
    print("\n".join(analyze_target_order_boundary(args.target, args.mod)))
    print()
    print("\n".join(scan_candidates(arrays_by_order)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
