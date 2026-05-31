"""Stochastic local search for Costas arrays (witness finding).

Energy = number of colliding difference pairs, summed over every width:
``E(f) = sum_h sum_d C(m_{h,d}, 2)`` where ``m_{h,d}`` counts how many times the
value ``d`` occurs as a width-``h`` difference. ``E = 0`` iff ``f`` is a Costas
array. ``CostasEnergy`` maintains the per-width difference-value counts so a swap
of two columns updates the energy in ``O(n)`` (only edges touching the swapped
columns change), which makes millions of moves per second feasible.

The search is simulated annealing with conflict-focused moves (bias swaps toward
columns that participate in a collision, min-conflicts style) and geometric
cooling with reheating; callers add random restarts on top.
"""
from __future__ import annotations

import random
from typing import Sequence


class CostasEnergy:
    def __init__(self, perm: Sequence[int]) -> None:
        self.n = len(perm)
        self.perm = list(perm)
        # count[h] maps a difference value -> multiplicity in the width-h layer.
        self.count: list[dict[int, int]] = [dict() for _ in range(self.n)]
        self.energy = 0
        for h in range(1, self.n):
            ch = self.count[h]
            for i in range(self.n - h):
                d = self.perm[i + h] - self.perm[i]
                m = ch.get(d, 0)
                self.energy += m  # C(m+1,2) - C(m,2) = m
                ch[d] = m + 1

    def _edges_touching(self, p: int) -> set[tuple[int, int]]:
        """All edges (i, j) with i < j and j - i a width, touching column p."""
        edges = set()
        n = self.n
        for h in range(1, n):
            if p + h < n:
                edges.add((p, p + h))
            if p - h >= 0:
                edges.add((p - h, p))
        return edges

    def apply_swap(self, p: int, q: int) -> int:
        """Swap columns p and q, update energy incrementally, return new energy."""
        if p == q:
            return self.energy
        edges = self._edges_touching(p) | self._edges_touching(q)
        perm = self.perm
        # remove old contributions
        for i, j in edges:
            h = j - i
            ch = self.count[h]
            d = perm[j] - perm[i]
            m = ch[d]
            self.energy -= (m - 1)  # C(m,2) - C(m-1,2) = m-1
            if m == 1:
                del ch[d]
            else:
                ch[d] = m - 1
        # apply swap
        perm[p], perm[q] = perm[q], perm[p]
        # add new contributions
        for i, j in edges:
            h = j - i
            ch = self.count[h]
            d = perm[j] - perm[i]
            m = ch.get(d, 0)
            self.energy += m
            ch[d] = m + 1
        return self.energy

    def swap_delta(self, p: int, q: int) -> int:
        """Energy change if columns p, q were swapped, WITHOUT mutating state."""
        if p == q:
            return 0
        edges = self._edges_touching(p) | self._edges_touching(q)
        perm = self.perm
        overlay: dict[tuple[int, int], int] = {}

        def cur(h: int, d: int) -> int:
            key = (h, d)
            if key in overlay:
                return overlay[key]
            return self.count[h].get(d, 0)

        delta = 0
        for i, j in edges:  # remove old contributions
            h = j - i
            d = perm[j] - perm[i]
            c = cur(h, d)
            delta -= (c - 1)
            overlay[(h, d)] = c - 1
        vp, vq = perm[p], perm[q]
        for i, j in edges:  # add contributions with swapped values
            h = j - i
            vi = vq if i == p else (vp if i == q else perm[i])
            vj = vq if j == p else (vp if j == q else perm[j])
            d = vj - vi
            c = cur(h, d)
            delta += c
            overlay[(h, d)] = c + 1
        return delta

    def conflicted_columns(self) -> list[int]:
        """Columns that participate in at least one colliding difference."""
        n = self.n
        flagged = [False] * n
        for h in range(1, n):
            ch = self.count[h]
            # which difference values collide (multiplicity >= 2)
            bad = {d for d, m in ch.items() if m >= 2}
            if not bad:
                continue
            for i in range(n - h):
                if (self.perm[i + h] - self.perm[i]) in bad:
                    flagged[i] = True
                    flagged[i + h] = True
        return [c for c in range(n) if flagged[c]]


def optimize(
    energy: CostasEnergy,
    rng: random.Random,
    *,
    max_steps: int,
    target: int = 0,
    patience: int = 30,
    kick_strength: int = 3,
) -> int:
    """Min-conflicts iterated local search, in place. Returns best energy seen.

    Each step picks a conflicted column and moves it to the swap that most
    reduces energy (steepest descent on that column, random tie-break). When no
    improvement occurs for ``patience`` steps it applies a random ``kick`` of a
    few swaps to escape the local minimum (iterated local search). This is far
    more effective at closing the last handful of collisions than random-walk
    annealing.
    """
    n = energy.n
    best = energy.energy
    if best <= target:
        return best
    since_improve = 0
    tenure = max(4, n // 2)            # tabu tenure: how long a swapped pair stays banned
    tabu: dict[tuple[int, int], int] = {}
    for step in range(max_steps):
        conflicted = energy.conflicted_columns()
        if not conflicted:
            break  # energy is 0
        p = conflicted[rng.randrange(len(conflicted))]
        # Min-conflicts with tabu: move p to the swap minimising energy, ignoring
        # pairs swapped in the last `tenure` steps (prevents 2-cycles), but always
        # allow a move that beats the best-so-far (aspiration). Escape deeper
        # minima via the periodic kick.
        best_d = None
        best_qs: list[int] = []
        for q in range(n):
            if q == p:
                continue
            key = (p, q) if p < q else (q, p)
            d = energy.swap_delta(p, q)
            tabued = tabu.get(key, 0) > step and (energy.energy + d) >= best
            if tabued:
                continue
            if best_d is None or d < best_d:
                best_d = d
                best_qs = [q]
            elif d == best_d:
                best_qs.append(q)
        if not best_qs:  # everything tabu: take a random partner
            best_qs = [rng.randrange(n)]
            while best_qs[0] == p:
                best_qs[0] = rng.randrange(n)
        q = best_qs[rng.randrange(len(best_qs))]
        tabu[(p, q) if p < q else (q, p)] = step + tenure
        energy.apply_swap(p, q)

        if energy.energy < best:
            best = energy.energy
            since_improve = 0
            if best <= target:
                return best
        else:
            since_improve += 1

        if since_improve >= patience:
            for _ in range(kick_strength):
                energy.apply_swap(rng.randrange(n), rng.randrange(n))
            since_improve = 0
            tabu.clear()
    return best


def search(
    n: int,
    seed: int,
    *,
    target: int = 0,
    steps_per_restart: int = 4_000,
    max_restarts: int | None = None,
    on_restart=None,
):
    """Random-restart min-conflicts ILS. Returns (best_perm, best_energy,
    restarts). ``on_restart(restart_idx, best_energy_so_far)`` is called after
    each restart (used for progress reporting)."""
    rng = random.Random(seed)
    base = list(range(1, n + 1))
    best_perm: list[int] | None = None
    best_energy: int | None = None
    restart = 0
    while max_restarts is None or restart < max_restarts:
        start = base[:]
        rng.shuffle(start)
        state = CostasEnergy(start)
        e = optimize(state, rng, max_steps=steps_per_restart, target=target)
        if best_energy is None or e < best_energy:
            best_energy = e
            best_perm = state.perm[:]
        restart += 1
        if on_restart is not None:
            on_restart(restart, best_energy)
        if best_energy <= target:
            break
    return best_perm, best_energy, restart
