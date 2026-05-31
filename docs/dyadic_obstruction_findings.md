# Obstruction Findings (N=32)

Working notes from the search for a *necessary condition* that every Costas
array satisfies but that fails at order `N=32` — strong enough to certify
endpoint shards infeasible. Tooling: `scripts/mine_dyadic_invariants.py`;
regression: `tests/test_dyadic_invariants.py`.

**Summary of what has been ruled out (all rigorous):**
1. Single-layer sum/residue lemmas cannot prune any endpoint shard (any modulus).
2. The dyadic joint obstruction (agenda Target A) is *false* — a witness exists.
3. Global second-moment / additive-energy bounds are insensitive to the Costas
   property and cannot obstruct.

## What was tested computationally

- The full curated dataset (`db/`, 9217 stored arrays across 81 non-empty
  orders). **Caveat:** this is a *curated, non-exhaustive* set of inequivalent
  ("essence") arrays, biased toward algebraic constructions at large `N`. Any
  empirical regularity here is a **conjecture**, not a proof.
- Single-layer dyadic sum/residue reachability for `N=32` (an exact DP).

## Verified provable laws (0 violations across all 9217 arrays)

1. **Telescoping sum.** For every shift `h`, `sum_i (f(i+h)-f(i)) = (sum of last
   h values) - (sum of first h values)`. (Identity; sanity check.)
2. **Shift-1 parity.** `#{i : f(i+1)-f(i) is odd} ≡ f(1)+f(N) (mod 2)`. Because
   a consecutive difference is odd iff the two values differ in parity, so the
   count of parity-changes along the sequence has the parity of `f(1) XOR f(N)`.
3. **Half-shift parity.** For even `N`, `h=N/2`: `#{i in [1,N/2] :
   f(i+N/2)-f(i) odd} ≡ N/2 (mod 2)`. For `N=32` this is `≡ 0 (mod 2)`.

**None of these prunes an endpoint shard.** Laws 2 is always satisfiable for any
endpoint pair; law 3 ranges over all 32 columns, so fixing only `f(1),f(32)`
leaves it undetermined.

## Key negative result (rigorous, not just empirical)

**No single-layer sum/residue lemma can prune any `N=32` endpoint shard, for any
modulus `m`.** For each dyadic shift `h in {1,2,4,8,16}`, the layer consists of
`N-h` distinct nonzero differences drawn from `[-(N-1), N-1]`. A DP over
(count × residue) shows that for `m in {2,4,8,16,32}` **every** residue class is
reachable as the layer sum. So the boundary-sum target (determined by the fixed
endpoints) can always be met modulo `m` — the lemma never fires.

This is exactly the lemma family the native C++ solver implements
(`HalfShiftParityFeasible`, `SubsetParityFeasible`, `SubsetResidueMod4Feasible`,
`ShiftDifferencePoolFeasible`). It explains the measured fact that **native
proves 0 of 256 shards UNSAT at 30s/shard** (`artifacts/native-shards-coarse/`):
its dyadic filters are mathematically incapable of pruning endpoint-only shards,
so all pruning would have to come from the raw distinct-difference search, which
does not terminate at practical time budgets.

Corollary: porting these lemmas into a CP-SAT/LP model (the earlier plan's
Tier 2) cannot certify endpoint shards either — confirmed by spike: adding
half-shift parity to a CP-SAT model changed conflicts by ~12% and still timed
out.

## Non-result: `n_pos shift 1 = N/2`

The mining scan flags `#{ascents at shift 1} = N/2` as *constant* across many
large orders (46, 66, 70, 72, 78, 82, 88, 96, 100). This is a **construction
artifact**, not a Costas law: those files are populated by a single algebraic
family with a fixed canonical orientation, and `n_pos` is not
reflection-invariant (reflection sends `n_pos -> N-1-n_pos`). Small,
densely-sampled orders (16, 28, 30, 36, 40) show it taking both `N/2` and
`N/2-1`. Discard as an obstruction.

## Target A (the Dyadic Injectivity Obstruction) is FALSE — refuted

The agenda's central theorem target (Target A) conjectured that *no* permutation
of `[32]` can make all dyadic difference layers `{1,2,4,8,16}` simultaneously
injective. **This is false.** A constructive randomized backtracking search over
just the five dyadic-shift distinctness constraints found a witness in ~0.5M
nodes:

```
17 4 28 6 15 30 24 16 20 11 19 29 2 5 25 13 18 32 12 10 22 1 3 31 8 21 14 9 27 23 7 26
```

Verified (independently, via `main.is_costas_array` and explicit layer checks):
a valid permutation of `1..32`; all of shifts `1,2,4,8,16` have fully distinct
differences; **not** a full Costas array (it collides at non-dyadic widths
`3,5,6,7,9,10,11,12,13,14,17,18,19,20,21,22`). The witness is saved at
`artifacts/dyadic-witness/n32_dyadic_feasible.txt`.

This is not a fluke. Exhaustive counts show dyadic-feasible permutations are
strictly more abundant than Costas arrays and the gap grows fast:

| N | dyadic-feasible | full Costas (known total) | ratio |
|---|---|---|---|
| 6 | 116 | 116 | 1.0 |
| 7 | 252 | 200 | 1.3 |
| 8 | 580 | 444 | 1.3 |
| 9 | 1580 | 760 | 2.1 |
| 10 | 6524 | 2160 | 3.0 |
| 11 | 22976 | 4368 | 5.3 |
| 12 | 81788 | 7852 | 10.4 |

(Costas ⊆ dyadic-feasible always — verified. For `N<=6` the non-dyadic shifts
are vacuous or implied, so the counts coincide.) Extrapolating, dyadic-feasible
permutations of `[32]` number in the (many) billions.

## Conclusion: the dyadic / power-of-two structure of 32 is NOT the obstruction

Two independent rigorous results kill the dyadic line of attack:

1. No single-layer sum/residue lemma prunes endpoint shards (any modulus).
2. The dyadic layers are jointly satisfiable at `N=32` (witness above), so
   Target A is false.

Therefore any valid impossibility proof for `N=32` **must** use the non-dyadic
shifts (3,5,6,7,...). The special role of `32 = 2^5` does not produce a
finite-difference obstruction.

## Global / Sidon (additive-combinatorics) analysis — also no obstruction

A Costas array is a planar Sidon set (`B_2` set in `Z^2`) that is also a
permutation matrix: all `C(n,2)` difference vectors `(h, f(i+h)-f(i))` are
distinct. The natural global necessary condition is a **second-moment /
additive-energy packing bound**.

Identity (permutation-invariant, verified on a stored array):

```
sum_{h} sum_i (f(i+h)-f(i))^2 = sum_{i<j} (f(j)-f(i))^2 = n*sum f^2 - (sum f)^2 = T.
```

Because each layer's `n-h` differences are distinct, each layer's squared-sum
has a hard minimum (using `±1,±2,...`), so `sum_h minQ(n-h) <= T` is necessary.
**It is far from binding:** for `N=32`, `min-sum = 23256` vs `T = 87296` — slack
`64040` (~73%). Same loose picture for every `n`.

Why it cannot work (diagnosed): `T` is within ~3% of the *random-permutation*
expectation (`N=32`: ratio 1.032), and real Costas arrays' per-layer `Q_h`
deviate from the random expectation by only +5-8% on average (stdev ~0.45). So
the second moment is **blind to the Costas/Sidon property** — Costas arrays look
essentially random at this level. Additive energy / moment inequalities are
therefore structurally incapable of obstructing `N=32`. A real obstruction would
have to exploit the exact combinatorial distinctness (the full Sidon structure),
which is precisely the intractable search rather than a closed-form inequality.

## Symmetry breaking is already (nearly) maximal — not a lever

Costas arrays have an 8-element dihedral symmetry (rotations + reflections of the
square), so searching only canonical representatives is a sound up-to-8x
reduction. Module: `costas_symmetry.py` (orbit, `is_canonical`, `to_canonical`;
verified across all 9217 stored arrays — every orbit size divides 8, every orbit
member is Costas).

**But the 8x is already captured.** The SAT encoding (and the native solver)
hand-code complement (`f(1) <= n/2`), reversal (the first/last band), and
transpose row constraints. Exhaustively comparing the *kept* set against the
number of orbits for small `N`:

| N | dihedral orbits | kept by existing scheme | kept / orbits |
|---|---|---|---|
| 6 | 17 | 27 | 1.6 |
| 7 | 30 | 43 | 1.4 |
| 8 | 60 | 103 | 1.7 |
| 9 | 100 | 148 | 1.5 |

The existing scheme is **sound** (keeps >=1 representative of every orbit —
regression in `tests/test_symmetry.py`) and already within ~1.5x of the optimum.
Adding full lex-leader canonicalization would therefore buy at most ~1.5x, and
only by *replacing* the existing sound scheme (stacking a second, differently
oriented scheme risks dropping an entire orbit -> false UNSAT). Low value, real
risk; not pursued.

## Witness search (local search) empirically does not scale to N=32

To pursue the *positive* direction (find an order-32 array rather than prove
none exists) we built a stochastic local search: energy = number of colliding
difference pairs, min-conflicts + tabu moves with iterated-local-search kicks and
random restarts (`costas_local_search.py`; parallel runner
`scripts/search_witness.py`). The engine is correct — it recovers from a
single-swap perturbation 20/20 and solves small orders — but the per-restart
success probability collapses with order:

| N | per-restart solve rate |
|---|---|
| 8 | 40/40 (100%) |
| 12 | ~99% (310/312) |
| 16 | ~1-2% (≈1/40) |
| 20 | 0 observed |
| 24 | 0 observed |

This ~10-20x decay per +4 in order is intrinsic: the all-distances-distinct
constraint makes the energy landscape rugged with the global optimum an
exponentially shrinking target. Extrapolated, the N=32 per-restart success
probability is ~1e-8 or worse — even a year of cluster compute would almost
certainly find nothing. (This is why large non-construction-order Costas arrays
are found by algebra, not search, and why the near-miss cloud's "energy 2" was a
landscape trap, not near-success.) The tool is useful up to ~N=14 and only a
very-long-odds probe beyond that.

## Non-dyadic shifts: probe is inconclusive (intractable), no obstruction found

Since the dyadic shifts are jointly satisfiable, any obstruction must use the
non-dyadic shifts (3,5,6,7,...). We probed *which* non-dyadic shift, added to the
dyadic set {1,2,4,8,16}, resists at N=32, via randomized backtracking for a
witness of {1,2,4,8,16,h}:

- At N=32, no {dyadic + h} witness was found within 9M nodes for any tested h.
- **But this is budget-limited, not evidence of infeasibility.** Calibration on
  orders where {dyadic + h} is *guaranteed* feasible (they have Costas arrays)
  shows nodes-to-find growing explosively — worst case h=3: **29k (N=16) ->
  142k (N=20) -> 4.28M (N=24)**. Extrapolated, a feasible witness at N=32 needs
  far more than 9M nodes. CP-SAT on {1,2,3,4,8,16} at N=32 also returned UNKNOWN
  after 100s.
- So deciding even a 6-shift *relaxation* at N=32 is itself intractable for both
  complete (CP-SAT) and incomplete (backtracking) methods — the probe cannot
  distinguish "infeasible" from "feasible but hard," and the calibration says the
  latter is expected. **No non-dyadic obstruction is established.**

Structural signal (not an obstruction): shift 3 is consistently the hardest
non-dyadic shift to add (highest node count at every order). This is explained by
tight additive coupling `D_3(i) = D_1(i) + D_2(i+1)` — layer-3 distinctness is
strongly entangled with the dyadic layers 1 and 2 — which makes it search-hard,
not impossible.

## Overall conclusion

The natural elementary obstruction classes — parity/residue, dyadic/power-of-two
structure, and additive-energy/moment counting — are all systematically ruled
out for `N=32`, and the non-dyadic probe shows that even deciding a 6-shift
*relaxation* at `N=32` is intractable for both complete and incomplete solvers
(so it yields no obstruction). This is consistent with `N=32` being a genuinely
open problem whose only established theory is asymptotic exponential sparsity
(Warnke, Correll, Swanson) and whose only decision method is exhaustive search.
Realistic remaining options:

- **Massive exhaustive search** (long per-shard CP-SAT/native runs; the shard
  harness exists). Decision-grade but compute-heavy and uncertain.
- **A genuine research breakthrough** beyond elementary methods (e.g. a tailored
  structural argument using the non-dyadic shifts, or new additive-combinatorics
  technique). Open-research-grade; not achievable by the counting/moment tools
  exercised here.

Tooling: `scripts/mine_dyadic_invariants.py` (laws + reachability),
`tests/test_dyadic_invariants.py` (regressions incl. the witness).
