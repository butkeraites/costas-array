#!/usr/bin/env python3
"""Generate the Costas array database from first principles.

Every array in db/ is produced here, from public-domain mathematics — no
external dataset is downloaded, vendored, or redistributed.

Two sources:

  * Exhaustive backtracking search for small orders, which gives the complete
    set of Costas arrays for those orders.
  * The classical algebraic constructions of Welch, Golomb and Lempel, which
    generate arrays for orders derived from primes and prime powers. These are
    the only known systematic constructions; every order they miss is an order
    where Costas arrays must be found by search, and 32 and 33 are the smallest
    orders where nobody has found any by either route.

Output is the "essential set": one representative per orbit of the dihedral
group D4 acting on the square, since the eight symmetries of a Costas array
are again Costas arrays and carry no new information.

References
----------
J. P. Costas, "A study of a class of detection waveforms having nearly ideal
range-doppler ambiguity properties", Proc. IEEE 72(8), 1984.

S. W. Golomb, "Algebraic constructions for Costas arrays", J. Combin. Theory
Ser. A 37(1), 1984.

S. W. Golomb and H. Taylor, "Constructions and properties of Costas arrays",
Proc. IEEE 72(9), 1984.
"""

from __future__ import annotations

import argparse
import os
from itertools import product

# --------------------------------------------------------------------------
# Costas property
# --------------------------------------------------------------------------


def is_costas(perm: tuple[int, ...]) -> bool:
    """A permutation is Costas when every displacement vector occurs once.

    Equivalently: for each shift h, the differences perm[i+h] - perm[i] are
    all distinct. This is the whole definition; everything else is machinery.
    """
    n = len(perm)
    for h in range(1, n):
        seen = set()
        for i in range(n - h):
            d = perm[i + h] - perm[i]
            if d in seen:
                return False
            seen.add(d)
    return True


# --------------------------------------------------------------------------
# D4 symmetry — the eight ways to look at the same array
# --------------------------------------------------------------------------


def _inverse(p: tuple[int, ...]) -> tuple[int, ...]:
    n = len(p)
    inv = [0] * n
    for i, v in enumerate(p):
        inv[v - 1] = i + 1
    return tuple(inv)


def d4_orbit(p: tuple[int, ...]) -> set[tuple[int, ...]]:
    """All eight images of p under the symmetries of the square."""
    n = len(p)
    horizontal = tuple(reversed(p))                 # flip left-right
    vertical = tuple(n + 1 - v for v in p)          # flip up-down
    rot180 = tuple(n + 1 - v for v in reversed(p))
    out = set()
    for q in (p, horizontal, vertical, rot180):
        out.add(q)
        out.add(_inverse(q))                        # transpose
    return out


def canonical(p: tuple[int, ...]) -> tuple[int, ...]:
    """The lexicographically smallest member of p's orbit."""
    return min(d4_orbit(p))


# --------------------------------------------------------------------------
# Finite field GF(q), q = prime^k
# --------------------------------------------------------------------------


def _factorize(n: int) -> dict[int, int]:
    factors: dict[int, int] = {}
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors[d] = factors.get(d, 0) + 1
            n //= d
        d += 1
    if n > 1:
        factors[n] = factors.get(n, 0) + 1
    return factors


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    d = 2
    while d * d <= n:
        if n % d == 0:
            return False
        d += 1
    return True


def prime_power(q: int) -> tuple[int, int] | None:
    """Return (p, k) when q = p^k, else None."""
    f = _factorize(q)
    if len(f) != 1:
        return None
    (p, k), = f.items()
    return p, k


class GF:
    """GF(p^k) as polynomials over GF(p) modulo an irreducible polynomial.

    Elements are tuples of k coefficients, low degree first. For k == 1 this
    degenerates to arithmetic mod p, which is the case the Welch construction
    needs, so both constructions can share one implementation.
    """

    def __init__(self, p: int, k: int):
        self.p, self.k, self.q = p, k, p ** k
        self.zero = tuple([0] * k)
        self.one = tuple([1] + [0] * (k - 1))
        self.elements = [tuple(e) for e in product(range(p), repeat=k)]
        # Must come last: the search for a modulus multiplies field elements,
        # so zero/one have to exist before it runs.
        self.modulus = self._find_irreducible() if k > 1 else None

    # -- polynomial arithmetic ------------------------------------------

    def add(self, a, b):
        return tuple((x + y) % self.p for x, y in zip(a, b))

    def mul(self, a, b):
        if self.k == 1:
            return ((a[0] * b[0]) % self.p,)
        prod = [0] * (2 * self.k - 1)
        for i, x in enumerate(a):
            if x:
                for j, y in enumerate(b):
                    prod[i + j] = (prod[i + j] + x * y) % self.p
        # reduce modulo the defining polynomial
        for deg in range(len(prod) - 1, self.k - 1, -1):
            c = prod[deg]
            if c:
                prod[deg] = 0
                for i, m in enumerate(self.modulus):
                    prod[deg - self.k + i] = (prod[deg - self.k + i] - c * m) % self.p
        return tuple(prod[: self.k])

    def power(self, a, e):
        result, base = self.one, a
        while e:
            if e & 1:
                result = self.mul(result, base)
            base = self.mul(base, base)
            e >>= 1
        return result

    def _find_irreducible(self):
        """Lowest monic polynomial of degree k with no roots that generates a
        field. Checked by verifying the multiplicative group has order q-1."""
        for tail in product(range(self.p), repeat=self.k):
            self.modulus = tail  # x^k == -sum(tail[i] x^i), stored as coefficients
            if self._is_field():
                return tail
        raise RuntimeError(f"no irreducible polynomial found for GF({self.p}^{self.k})")

    def _is_field(self) -> bool:
        # Every nonzero element must be invertible, which for a finite ring of
        # this shape is equivalent to a^(q-1) == 1 for all a != 0.
        for a in product(range(self.p), repeat=self.k):
            if all(c == 0 for c in a):
                continue
            if self.power(tuple(a), self.q - 1) != self.one:
                return False
        return True

    # -- group structure -------------------------------------------------

    def primitives(self) -> list[tuple[int, ...]]:
        """Generators of the multiplicative group."""
        order = self.q - 1
        primes = list(_factorize(order))
        out = []
        for a in self.elements:
            if a == self.zero:
                continue
            if all(self.power(a, order // r) != self.one for r in primes):
                out.append(a)
        return out

    def log_table(self, g) -> dict[tuple[int, ...], int]:
        """Discrete logarithm base g."""
        table, cur = {}, self.one
        for e in range(self.q - 1):
            table[cur] = e
            cur = self.mul(cur, g)
        return table


# --------------------------------------------------------------------------
# Welch construction — order p - 1, and its corner-trimmed variants
# --------------------------------------------------------------------------


def welch(p: int) -> set[tuple[int, ...]]:
    """W1(p, g, c): a[i] = g^(i+c) mod p, for every primitive root g and shift c.

    Order p-1. Trimming the corner dot where the array takes the value 1 gives
    W2 (order p-2), and trimming again gives W3 (order p-3).
    """
    if not is_prime(p):
        return set()
    out = set()
    field = GF(p, 1)
    for g in field.primitives():
        g = g[0]
        powers = [pow(g, i, p) for i in range(p - 1)]
        for c in range(p - 1):
            arr = tuple(powers[(i + c) % (p - 1)] for i in range(p - 1))
            out.add(arr)
            # W2 / W3: drop leading dots once they sit in the corner
            if arr[0] == 1:
                out.add(_renumber(arr[1:]))
                if len(arr) > 2 and arr[1] == 2:
                    out.add(_renumber(arr[2:]))
    return out


def _renumber(arr: tuple[int, ...]) -> tuple[int, ...]:
    """Compress values to 1..n preserving order, so a trimmed array is again a
    permutation of its own length."""
    ranks = {v: i + 1 for i, v in enumerate(sorted(arr))}
    return tuple(ranks[v] for v in arr)


# --------------------------------------------------------------------------
# Golomb and Lempel constructions — order q - 2
# --------------------------------------------------------------------------


def golomb(q: int) -> set[tuple[int, ...]]:
    """G2(q, a, b): dot at (i, j) whenever a^i + b^j = 1, for i,j in 1..q-2.

    Order q-2. Lempel's construction is the special case a == b, and is
    included here rather than separated, since it is the same equation.
    """
    pk = prime_power(q)
    if pk is None:
        return set()
    p, k = pk
    field = GF(p, k)
    prims = field.primitives()
    out = set()

    for a in prims:
        log_a = field.log_table(a)
        a_pow = {e: field.power(a, e) for e in range(1, q - 1)}
        for b in prims:
            log_b = field.log_table(b)
            perm = [0] * (q - 2)
            ok = True
            for i in range(1, q - 1):
                # solve a^i + b^j = 1  ->  b^j = 1 - a^i
                target = field.add(field.one, tuple((-c) % p for c in a_pow[i]))
                if target == field.zero:
                    ok = False
                    break
                j = log_b.get(target)
                if j is None or not (1 <= j <= q - 2):
                    ok = False
                    break
                perm[i - 1] = j
            if not ok:
                continue
            arr = tuple(perm)
            if sorted(arr) != list(range(1, q - 1)):
                continue
            if is_costas(arr):
                out.add(arr)
                # G3/G4/T4: trim corner dots when they are present
                if arr[0] == 1:
                    trimmed = _renumber(arr[1:])
                    if is_costas(trimmed):
                        out.add(trimmed)
                if arr[-1] == len(arr):
                    trimmed = _renumber(arr[:-1])
                    if is_costas(trimmed):
                        out.add(trimmed)
    return out


# --------------------------------------------------------------------------
# Exhaustive search — complete for small orders
# --------------------------------------------------------------------------


def exhaustive(n: int) -> set[tuple[int, ...]]:
    """Every Costas array of order n, by backtracking with incremental
    difference checking. Feasible to about n = 13 in pure Python."""
    result: set[tuple[int, ...]] = set()
    perm: list[int] = []
    used = [False] * (n + 1)
    # diffs[h] holds the differences already seen at shift h
    diffs: list[set[int]] = [set() for _ in range(n)]

    def place(depth: int) -> None:
        if depth == n:
            result.add(tuple(perm))
            return
        for v in range(1, n + 1):
            if used[v]:
                continue
            added = []
            ok = True
            for h in range(1, depth + 1):
                d = v - perm[depth - h]
                if d in diffs[h]:
                    ok = False
                    break
                diffs[h].add(d)
                added.append((h, d))
            if ok:
                used[v] = True
                perm.append(v)
                place(depth + 1)
                perm.pop()
                used[v] = False
            for h, d in added:
                diffs[h].discard(d)

    place(0)
    return result


# --------------------------------------------------------------------------
# Assembling the database
# --------------------------------------------------------------------------


def essential_set(n: int, exhaustive_limit: int) -> list[tuple[int, ...]]:
    """One representative per D4 orbit, for order n."""
    found: set[tuple[int, ...]] = set()

    if n <= exhaustive_limit:
        found |= exhaustive(n)
    else:
        # Welch gives orders p-1, p-2, p-3; Golomb/Lempel give q-2 and its
        # corner-trimmed variants q-3, q-4.
        for p in (n + 1, n + 2, n + 3):
            if is_prime(p):
                found |= {a for a in welch(p) if len(a) == n}
        for q in (n + 2, n + 3, n + 4):
            found |= {a for a in golomb(q) if len(a) == n}

    representatives: dict[tuple[int, ...], tuple[int, ...]] = {}
    for arr in found:
        if not is_costas(arr):
            continue
        representatives.setdefault(canonical(arr), arr)
    return sorted(representatives.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-order", type=int, default=100)
    ap.add_argument("--exhaustive-limit", type=int, default=12,
                    help="orders at or below this are enumerated completely")
    ap.add_argument("--out", default="db")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    for n in range(2, args.max_order + 1):
        arrays = essential_set(n, args.exhaustive_limit)
        path = os.path.join(args.out, f"Costas_essential_N={n}.txt")
        with open(path, "w") as fh:
            if arrays:
                width = len(str(n))
                for arr in arrays:
                    fh.write(" " + " ".join(str(v).rjust(width) for v in arr) + "\n")
            else:
                fh.write(" No Costas arrays.\n")
        print(f"N={n:<4} {len(arrays):>6} arrays" + ("   (none known)" if not arrays else ""))


if __name__ == "__main__":
    main()
