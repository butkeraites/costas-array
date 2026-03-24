# Function-Space Roadmap For Costas Arrays

This note explains how to reinterpret a Costas array as a function and what
"topology of the family" could reasonably mean in a useful computational sense.

## 1. The Basic Reinterpretation

An order-`n` Costas array is the graph of a permutation

`f : {1, ..., n} -> {1, ..., n}`.

The Costas property says that for every shift `h` with `1 <= h < n`, the
discrete derivative

`D_h f(i) = f(i + h) - f(i)` for `1 <= i <= n - h`

is injective.

So a Costas array is not just a permutation. It is a function whose entire
family of discrete difference operators is collision-free.

## 2. Why Literal Topology Is Not Enough

For fixed `n`, the family of Costas arrays is finite, so as a literal
topological space it is just a discrete set.

To get useful structure we need to embed it into a larger geometric object.
There are several natural choices.

## 3. Three Good Geometric Models

### A. Graph-of-a-Function Model

Embed the permutation as a normalized piecewise-linear function

`g_f : [0, 1] -> [0, 1]`

through the points

`(i / n, f(i) / n)`.

This lets us study:

- coarse shape
- convexity / concavity tendencies
- sign changes of discrete curvature
- endpoint geometry

This is especially useful if order-`32` arrays, if they exist, have to look
like discretizations of a narrow family of continuous Costas-like functions.

### B. Secant-Surface Model

For each function define the secant set

`S_f = {(h / n, (f(i + h) - f(i)) / n) : 1 <= h < n, 1 <= i <= n - h}`.

The Costas property is exactly the statement that for each fixed `h`, the
vertical coordinates in the `h`-slice are all distinct.

This is the most faithful "function-space" model because Costasness is a
statement about secants, not just point values.

This model suggests studying:

- dyadic slices `h = 1, 2, 4, 8, 16`
- residue patterns of secants
- mirror-pair structure
- boundary-sum identities

### C. Energy-Landscape Model

Define an energy on all permutations by

`E(f) = number of repeated values among all rows of the difference triangle`.

Then:

- `E(f) = 0` iff `f` is Costas
- small `E(f)` means "near-Costas"

This turns the problem into a landscape problem on `S_n`. The zero set may be
empty at `n = 32`, but the shape of the low-energy region can still reveal
structure.

## 4. A Better Meaning Of "Topology"

The most useful topology here is probably not the Euclidean topology of
interpolated graphs. It is one of these:

- the topology of the low-energy landscape
- the geometry of the secant-profile point cloud
- the graph topology of local moves between near-Costas permutations

Concretely, we can build a graph whose vertices are low-energy permutations and
whose edges are local moves such as:

- adjacent swaps
- arbitrary transpositions
- one-point insert/delete moves between nearby orders

Then we can ask:

- Are there multiple connected components?
- Do known Costas arrays lie on a thin manifold inside near-miss space?
- Do order-`32` near-misses get arbitrarily close to that manifold or do they
  hit a geometric wall?

## 5. Continuous Inspiration

There is real literature on continuum analogs of the Costas property:

- Drakakis and Rickard, [On the generalization of the Costas property in the continuum](https://arxiv.org/abs/0706.1379)
- Drakakis, [On nowhere continuous Costas functions and infinite Golomb rulers](https://arxiv.org/abs/0810.0933)

These do not solve the finite `n = 32` problem directly, but they justify the
idea that the Costas property can be studied as a property of functions and
their secants, not just as a matrix puzzle.

## 6. The Most Promising Computational Program

### Stage 1. Feature Geometry

For each stored array, compute a feature vector based on:

- normalized endpoints
- dyadic secant statistics
- mirror-pair counts
- sign balances in `D_h f`
- discrete curvature summaries

This gives a metric geometry on known examples.

### Stage 2. Near-Miss Cloud For `n = 32`

Generate many low-energy permutations of order `32` by local search and keep:

- the best energies found
- their secant features
- their local-move graph

Then compare the near-miss cloud to the known Costas cloud from neighboring
orders.

### Stage 3. Quotient By Symmetry

Costas arrays are naturally grouped by `D4` symmetries. Any geometric study
should quotient or canonically normalize by these symmetries, otherwise the
same object appears many times.

### Stage 4. Use Geometry To Feed Exact Search

The point is not just visualization. The point is to turn geometric regularities
into exact constraints:

- monotonicity tendencies
- forbidden secant residues
- endpoint restrictions
- necessary mirror-pair profiles

## 7. My Current View

Yes, this is worth trying.

Not because "topology" will magically prove nonexistence by itself, but because
the Costas property is naturally a statement about a whole family of discrete
derivatives. Recasting the problem in function-and-secant language may reveal
structure that is invisible in raw backtracking logs.

If this line works, the most likely output is not a direct proof at first. It is
one or more new exact invariants that can be fed back into SAT or native search.
