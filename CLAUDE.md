# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A curated dataset of Costas arrays (orders 2–100) plus a Python CLI for
exploring/validating that data and an experimental search stack aimed at the
open `N=32` case. A Costas array is a permutation of `1..N` where every pairwise
displacement vector is unique; arrays are stored 1-based, one permutation per
line.

## Setup & commands

```bash
python3 -m pip install -r requirements.txt   # z3-solver, ortools, networkx
brew install kissat                           # external SAT backend (optional: cadical)
```

There is a checked-in `.venv/` (Python 3.11). Use `python3` directly.

```bash
# CLI (default subcommand is `summary`)
python3 main.py summary [--all]
python3 main.py show <order> [--limit N]
python3 main.py validate [<order>]
python3 main.py search <order> --time-limit 60 [--backend auto|native|sat|ortools|z3]
python3 main.py export-cnf <order> /tmp/out.cnf [--assign 1=1 --assign 32=13 --sat-window4-radius 2]
python3 main.py --db-dir /path/to/db summary   # override dataset location
```

### Tests

```bash
python3 -m unittest discover -s tests -v          # full suite
python3 -m unittest tests.test_main -v            # one module
python3 -m unittest tests.test_main.ClassName.test_method   # one test
```

## Architecture

The core logic lives in three flat top-level modules; `scripts/` are research
drivers built on top of them.

- **`main.py`** — the CLI, the dataset model, the validator, and the search
  orchestrator. `search_costas_array()` runs a fixed escalation ladder
  regardless of backend: (1) `search_via_database` (look for a stored example
  matching any `--assign` constraints), (2) `search_via_neighbors` (cheap
  witness search by augmenting/deleting stored arrays of nearby orders), then
  (3) the chosen solver backend. The `auto` backend splits the time budget
  40% native / 60% sat.
- **`costas_sat.py`** — DIMACS CNF encoding (grid variables + at-most-one /
  exactly-one with auxiliary vars + per-displacement distinctness) and the
  `kissat` / `cadical` subprocess runners. Supports redundant extra clause
  layers: local 4-column endpoint windows, mined forbidden patterns, and clique
  cuts.
- **`local_window4.py`** — enumerates feasible/forbidden consecutive 4-column
  sub-patterns; shared by the SAT extra-clause layer and the LP relaxation.
- **`native/costas_native.cpp`** — C++ depth-first searcher (fail-first
  branching, fixed assignments, endpoint sharding, dyadic parity/mod-4 pruning).
  `build_native_solver()` in `main.py` compiles it on demand with
  `g++ -O3 -std=c++17` and uses `native/costas_native.build.json` (a
  system/machine stamp) plus mtime to decide whether to rebuild. The committed
  binary is arm64/Darwin — it will be recompiled automatically on a different
  platform or when the source changes.

### Backends

`auto` (default), `native`, `sat`, `ortools`, `z3`. `native` and `sat` honor
`--assign col=row` for sharding subproblems. `sat` additionally accepts
`--sat-window4-radius`, mined `--sat-forbidden-patterns`, and
`--sat-clique-cuts` JSON files.

### Research scripts (`scripts/`)

These compose the modules above into experiments and write outputs under
`artifacts/<experiment>/n<order>/`. The pipeline is roughly: generate a
near-miss cloud → mine structure from it → feed structure back as search
guidance / extra constraints.

- `build_near_miss_cloud.py` — low-energy near-miss nodes + transposition graph.
- `mine_width_pressure.py`, `mine_window4_patterns.py`, `mine_clique_cuts.py` —
  mine reusable constraints/branch-order hints (e.g. `clique_cuts_n10.json`,
  `forbidden_patterns_n10.json`) from the cloud or enumeration.
- `run_native_shards.py`, `run_lp_shards.py` — parallel shard runners
  (`--workers`, `--shard-stride`/`--shard-offset` to split across machines).
- `lp_shard_relaxation.py` — OR-Tools LP relaxation over selected widths /
  triangle / 4-column quad layers.
- `run_search_suite.py` — repeatable backend comparison, logs to `artifacts/`.
- `analyze_dyadic_profiles.py`, `export_function_features.py` — analysis.

## Data format & conventions

- Files: `db/Costas_essense_N=<order>.txt` (keep the `Costas_essense` prefix).
- Each non-empty line is a whitespace-separated permutation of `1..N`; blank
  lines ignored; `No Costas arrays.` marks a file with no stored arrays.
- An empty/marker file means "no stored example here" — **not** a proof that no
  Costas array exists for that order. `N=32` is genuinely open; see
  `docs/n32_research_agenda.md` and `docs/function_space_roadmap.md`.
- The validator checks length, permutation-ness, in-file uniqueness, and the
  Costas property.
