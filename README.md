# Costas Array Dataset

This repository stores a curated dataset of Costas arrays and provides a small
Python CLI for exploring and validating that data.

To use the solver-backed search command, install dependencies first:

```bash
python3 -m pip install -r requirements.txt
```

To use the external SAT backend, install `kissat`:

```bash
brew install kissat
```

## What Is A Costas Array?

A Costas array is a permutation of `1..N` with two defining properties:

1. Each row and column contains exactly one dot.
2. Every displacement vector between two dots is unique.

These structures are studied in combinatorics and are useful in areas such as
radar, sonar, and frequency-hopping sequence design.

In this repository, each array is written as a 1-based permutation. For
example, the order-4 array `1 2 4 3` means:

- Column 1 has a dot in row 1
- Column 2 has a dot in row 2
- Column 3 has a dot in row 4
- Column 4 has a dot in row 3

## Repository Layout

- [main.py](./main.py) contains the CLI and validation logic.
- [db/](./db/) contains the stored arrays, one file per order.
- [tests/](./tests/) contains automated tests for the CLI and validator.

## Data Format

Data files follow this naming scheme:

```text
db/Costas_essense_N=<order>.txt
```

Rules for each file:

- Each non-empty line is a whitespace-separated permutation of `1..N`.
- Blank lines are ignored.
- Files with no stored arrays contain the marker `No Costas arrays.`

Important: an empty file in this repository means "no stored example is
currently recorded here". It should not be interpreted as a mathematical proof
that no Costas array exists for that order.

The dataset currently ships with files for orders `2` through `100`.

## Command Line Usage

Show a dataset summary:

```bash
python3 main.py summary
```

Show a full per-order count table:

```bash
python3 main.py summary --all
```

Print arrays for one order:

```bash
python3 main.py show 10
```

Limit the number of arrays shown:

```bash
python3 main.py show 10 --limit 5
```

Validate the entire dataset:

```bash
python3 main.py validate
```

Validate a single order:

```bash
python3 main.py validate 34
```

Search for an example or a proof of impossibility for one order:

```bash
python3 main.py search 32 --time-limit 30
```

Choose a specific solver backend:

```bash
python3 main.py search 32 --backend ortools --time-limit 60
```

Use the native C++ backtracking backend:

```bash
python3 main.py search 32 --backend native --time-limit 60
```

Fix one or more native-search coordinates for a subproblem:

```bash
python3 main.py search 32 --backend native --time-limit 60 --assign 1=1 --assign 32=17
```

Use the external SAT backend:

```bash
python3 main.py search 32 --backend sat --time-limit 60
```

Use shard assignments with SAT too, and optionally add redundant local 4-column
endpoint clauses:

```bash
python3 main.py search 32 --backend sat --time-limit 60 --assign 1=1 --assign 32=13 --sat-window4-radius 2
```

Pick the SAT solver explicitly:

```bash
python3 main.py search 32 --backend sat --sat-solver cadical --time-limit 180
```

Export the DIMACS CNF without solving it:

```bash
python3 main.py export-cnf 32 /tmp/costas_32.cnf
```

Export a shard-aware CNF with fixed assignments and the same endpoint-window
clauses:

```bash
python3 main.py export-cnf 32 /tmp/costas_32_hybrid.cnf --assign 1=1 --assign 32=13 --sat-window4-radius 2
```

Run a repeatable backend comparison suite and store logs:

```bash
python3 scripts/run_search_suite.py 32 --time-limit 180
```

Run native endpoint shards in parallel and store one result per shard:

```bash
python3 scripts/run_native_shards.py 32 --time-limit 300 --workers 8
```

Split the shard set across multiple machines:

```bash
python3 scripts/run_native_shards.py 32 --time-limit 300 --workers 8 --shard-stride 2 --shard-offset 0
```

Summarize dyadic difference-layer statistics for research work:

```bash
python3 scripts/analyze_dyadic_profiles.py 16 31 34
```

Build a low-energy near-miss cloud for function-space analysis of one order:

```bash
python3 scripts/build_near_miss_cloud.py 32 --restarts 32 --steps 60 --samples-per-step 80 --top-k 120
```

This writes canonicalized near-miss nodes, a sampled transposition graph, and
reference feature rows for nearby stored orders under
`artifacts/near-miss-cloud/n<order>/`.

Mine recurring bad widths from that cloud and feed them back into the native
search as branch-order guidance:

```bash
python3 scripts/mine_width_pressure.py artifacts/near-miss-cloud/n32/near_miss_nodes.csv --max-energy 20 --top-widths 8
python3 scripts/run_native_shards.py 32 --time-limit 300 --workers 8 --focus-widths 1,2,3,4
```

Solve a shard-aware LP relaxation on selected widths:

```bash
python3 scripts/lp_shard_relaxation.py 32 --assign 1=1 --assign 32=13 --widths all --triangles window4 --solver PDLP --time-limit 60
python3 scripts/run_lp_shards.py 32 --widths all --triangles window4 --solver PDLP --time-limit 60 --workers 8
```

Add a 4-column endpoint-window layer on top of the triangle relaxation:

```bash
python3 scripts/lp_shard_relaxation.py 32 --assign 1=1 --assign 32=13 --widths 1,2,3,4 --triangles window4 --quads endpoints --quad-radius 2 --solver PDLP --time-limit 60
python3 scripts/run_lp_shards.py 32 --widths 1,2,3,4 --triangles window4 --quads endpoints --quad-radius 2 --solver PDLP --time-limit 60 --workers 8
```

Use a different database directory:

```bash
python3 main.py --db-dir /path/to/db summary
```

If you run `python3 main.py` without a subcommand, it defaults to `summary`.

## Development

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

The validator checks that each stored row:

- has the correct length for its order
- is a permutation of `1..N`
- is unique within its file
- satisfies the Costas property

The search command uses [Z3](https://github.com/Z3Prover/z3) and
[OR-Tools CP-SAT](https://developers.google.com/optimization) with a standard
Costas-array encoding:

- variables form a permutation of `1..N`
- for each distance `d`, all differences `x[i + d] - x[i]` are distinct
- small symmetry-breaking constraints reduce duplicate search work
- before invoking a solver, the `auto` backend also tries fast witness searches
  based on neighboring stored orders
- the `native` backend compiles and runs a C++ depth-first searcher with
  fail-first branching, optional fixed assignments, shard-friendly endpoint
  splitting, and dyadic parity/mod-4 pruning
- the `sat` backend exports a DIMACS CNF and invokes
  [kissat](https://github.com/arminbiere/kissat)

For the open `N=32` case, see the research memo at
[`docs/n32_research_agenda.md`](./docs/n32_research_agenda.md).

## Notes

- The repository is intentionally lightweight: it validates stored data, but it
  does not generate Costas arrays from scratch.
- The file naming convention keeps the original `Costas_essense` prefix already
  present in the dataset.
- For background on the open search problem, see the
  [CSPLib Costas array page](https://www.csplib.org/Problems/prob076/), which
  notes that some orders such as `32` remain unresolved in the literature.
