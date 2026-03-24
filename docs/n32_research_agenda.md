# N=32 Research Agenda

This note focuses on the open order `N=32` case and records a concrete attack
plan that combines mathematics and exact computation.

## Current Position

Sourced:

- Order `32` is treated as unresolved in [CSPLib problem 076](https://www.csplib.org/Problems/prob076/).
- Drakakis' review summarizes the classical algebraic constructions and open
  questions: [A review of Costas arrays](https://www.pure.ed.ac.uk/ws/portalfiles/portal/10369967/A_review_of_Costas_arrays.pdf).
- Jedwab and Wodlinger prove several structural restrictions that are useful as
  hard search constraints: [Structural properties of Costas arrays](https://www.aimsciences.org/article/doi/10.3934/amc.2014.8.241).
- Warnke, Correll, and Swanson show that Costas arrays are exponentially sparse
  among permutations: [The Density of Costas Arrays Decays Exponentially](https://mathweb.ucsd.edu/~lwarnke/CostasArrayExponentialDecay.pdf).
- APN-style finite-difference ideas connect to Costas permutations in
  [APN permutations on Z_n and Costas arrays](https://www.sciencedirect.com/science/article/pii/S0166218X09002789).
- A recent heuristic framework based on Universal Costas Matrices appears in
  [Universal Costas Matrices: Towards a General Framework for Costas Array Construction](https://arxiv.org/abs/2602.03407).

Inference:

- There is no known pure theorem that obviously settles `N=32`; otherwise the
  order would likely not remain open in the standard references.

## Algebraic Construction Check

Sourced:

- The standard finite-field families described in the review generate orders of
  the shape `q-1`, `q-2`, `q-3`, `q-4`, and in a rarer case `q-5` under extra
  primitive-root identities.

Inference:

- `32` does not fit the standard `q-k` families for `k = 1, 2, 3, 4` because
  `33`, `34`, `35`, and `36` are not prime powers.
- The only plausible rare `q-5` case is `q = 37`. A direct computation in this
  project found no primitive-root pair in `F_37` satisfying the relevant
  `G*_5` equations, so that exotic algebraic route does not produce order `32`.

Conclusion:

- A direct new algebraic construction for `32` is possible in principle, but it
  no longer looks like the shortest route.

## Best Mathematical Angles

### 1. Finite-Difference View

Sourced:

- The Costas condition is equivalent to saying that for every shift `h`, the
  differences `f(i + h) - f(i)` are all distinct.

Inference:

- This is the cleanest way to exploit the special role of `32 = 2^5`.
- The shifts `1, 2, 4, 8, 16` should be treated as a coupled dyadic system,
  not as independent constraints.
- A promising theorem target is a contradiction among the dyadic difference
  layers rather than a generic permutation count.

### 2. Additive Combinatorics / Sidon-Set View

Sourced:

- Costas arrays sit naturally inside the literature on distinct-difference
  configurations and Sidon-type structures.

Inference:

- This suggests looking for additive-energy bounds, container-style arguments,
  or local forbidden-pattern theorems that become sharp at `N=32`.

### 3. Structural Geometry

Sourced:

- Jedwab and Wodlinger prove hard structural restrictions, including forbidden
  corner regions and other geometric constraints.

Inference:

- These should be compiled directly into exact solvers as clauses or custom
  propagation rules.
- Even if they do not prove nonexistence alone, they can shrink the proof space
  enough to make a full exact proof realistic.

### 4. Cryptographic Difference Theory

Sourced:

- APN and low-collision difference frameworks are mathematically close to the
  Costas finite-difference condition.

Inference:

- Differential-uniformity techniques may yield new local impossibility tests for
  multiple shifts at once.

### 5. AI-Guided Candidate Search

Sourced:

- Recent work on UCMs aims to accelerate Costas-array discovery through
  structural reconstruction.

Inference:

- This is not a proof method.
- It is useful only as a front-end for exact proof search.

## Immediate Theorem Targets

These are conjectural or partially proved targets worth attacking now.

### Target A. Dyadic Injectivity Obstruction

Goal:

- Show that no permutation of `[32]` can make all layers
  `Delta_h(i) = f(i + h) - f(i)` injective for `h in {1, 2, 4, 8, 16}`.

Why it is plausible:

- `32` is the first unresolved power of two in the dataset.
- Power-of-two shifts create nested overlap patterns in the difference triangle.

### Target B. Half-Shift Parity Lemma

Direct derivation:

- For even `n`, the `h = n/2` layer pairs the columns into `n/2` disjoint pairs.
- Therefore the number of odd differences in that layer has the same parity as
  `n/2`.

Checked in the current dataset:

- This parity rule holds for every stored even order in the repository.

Why it matters:

- By itself it is weak, but it is the sort of invariant that could combine with
  sign or residue constraints from other dyadic layers.

### Target C. Endpoint-Forced Contradiction

Goal:

- Use the endpoint split `(f(1), f(32))` together with structural lemmas to
  prove whole families of shards unsatisfiable symbolically.

Why it matters:

- It matches the current exact-search decomposition and is directly usable in
  proof-logging SAT or native search.

## Exact-Search Program

### Highest-Priority Computational Work

1. Keep the sharded native search running with proof-oriented logging.
2. Export SAT subproblems per endpoint shard and use proof-producing SAT when a
   shard looks promising for an UNSAT certificate.
3. Translate structural lemmas into SAT clauses or native propagation.
4. Mine the database for dyadic profile regularities that can become lemmas.

### What Not To Overinvest In

- Pure random search.
- Generic algebraic family hunting with no `32`-specific obstruction in mind.
- ML heuristics without exact verification.

## Concrete Next Experiments

1. Build a dyadic-profile catalog for all stored arrays and look for invariants
   that survive across many orders.
2. Compare the `N=32` endpoint shards by node count and search depth, then
   isolate the "hard" endpoint families.
3. Add parity and residue bookkeeping for shifts `1, 2, 4, 8, 16` inside the
   native solver to create earlier contradictions.
4. Encode structural lemmas from Jedwab-Wodlinger as SAT clauses and rerun the
   proof-producing workflow.
5. Explore transformation neighborhoods around nearby known orders such as `31`
   and `34`, but only as witness-generation support for exact proof search.

## Working Thesis

The best chance of settling `N=32` is not a brand-new closed-form algebraic
construction. It is a hybrid attack:

- a finite-difference or additive-combinatorics obstruction specific to the
  dyadic structure of `32`, plus
- a proof-producing exact search that absorbs every available structural lemma.
