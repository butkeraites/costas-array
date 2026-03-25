from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import Any

import networkx as nx

ROOT_DIR = Path(__file__).resolve().parents[1]
for path in (ROOT_DIR, ROOT_DIR / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from local_window4 import iter_consecutive_window4_feasible_tuples, allowed_rows_by_column


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mine structural cliques from Costas compatibility graphs.")
    parser.add_argument("order", type=int, help="Order N to study.")
    parser.add_argument(
        "--assign",
        action="append",
        default=[],
        metavar="COLUMN=ROW",
        help="Fix a 1-based column to a 1-based row.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=ROOT_DIR / "clique_cuts.json",
        help="Destination to save the extracted cliques.",
    )
    return parser


def parse_assignment_specs(specs: list[str], *, order: int) -> list[tuple[int, int]]:
    assignments = []
    for spec in specs:
        col_str, row_str = spec.split("=")
        col, row = int(col_str), int(row_str)
        if not (1 <= col <= order and 1 <= row <= order):
            raise ValueError(f"Assignment out of bounds: {spec}")
        assignments.append((col, row))
    return assignments


def configurations_conflict(
    order: int,
    start1: int,
    rows1: tuple[int, int, int, int],
    start2: int,
    rows2: tuple[int, int, int, int],
) -> bool:
    """
    Returns True if the 4-column assignment 1 CONFLICTS with the 4-column assignment 2.
    They conflict if they cannot coexist in a valid Costas Array.
    """
    # Build complete point set
    points = {}
    
    # Add points from configuration 1
    for i, r in enumerate(rows1):
        c = start1 + i
        points[c] = r
        
    # Check configurations 2 against 1
    for i, r in enumerate(rows2):
        c = start2 + i
        if c in points:
            if points[c] != r:
                return True # Overlap disagreement
        else:
            points[c] = r

    # Now verify if the united points dictionary represents a locally valid Costas structure
    coords = sorted(points.items())
    
    # 1. Row collisions
    seen_rows = set()
    for c, r in coords:
        if r in seen_rows:
            return True
        seen_rows.add(r)
        
    # 2. Difference collisions
    seen_diffs: set[tuple[int, int]] = set()
    n_points = len(coords)
    for i in range(n_points):
        for j in range(i + 1, n_points):
            c1, r1 = coords[i]
            c2, r2 = coords[j]
            dc = c2 - c1
            dr = r2 - r1
            if (dc, dr) in seen_diffs:
                return True
            seen_diffs.add((dc, dr))
            
    return False


def main_entry(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    order = args.order
    assignments = parse_assignment_specs(args.assign, order=order)

    domain_result = allowed_rows_by_column(order, assignments)
    if domain_result.status == "infeasible":
        print("Initial assignments are infeasible.")
        return 0

    print(f"Generating valid 4-column patterns for N={order}...")
    
    # We will build a Conflict Graph
    # Nodes: (start_col, (row0, row1, row2, row3))
    G = nx.Graph()
    
    import random
    MAX_NODES = 20000
    all_patterns = []
    total_seen = 0
    
    # 1. Generate all feasible 4-col windows using Reservoir Sampling
    for start_col in range(1, order - 2):
        print(f"   Building domains for window starting at col {start_col}...")
        for p in iter_consecutive_window4_feasible_tuples(domain_result.allowed_rows, start_col):
            node = (start_col, p)
            if total_seen < MAX_NODES:
                all_patterns.append(node)
            else:
                j = random.randint(0, total_seen)
                if j < MAX_NODES:
                    all_patterns[j] = node
            total_seen += 1

    # Add the uniformly sampled reservoir to the graph
    for node in all_patterns:
        G.add_node(node)

    n_nodes = len(all_patterns)
    print(f"Sampled {n_nodes} nodes out of {total_seen} globally available Costas 4-column sub-patterns.")
    if n_nodes == 0:
        print("No candidates found.")
        return 0
        
    print("Building Conflict Graph O(N^2) edge insertions...")
    
    # 2. Add edges for structurally conflicting patterns
    # To optimize, we divide into overlap vs disjoint
    edges_added = 0
    for i in range(n_nodes):
        if i % 500 == 0 and i > 0:
            print(f"   Processed {i}/{n_nodes} nodes for edges...")
        node1 = all_patterns[i]
        start1, rows1 = node1
        
        for j in range(i + 1, n_nodes):
            node2 = all_patterns[j]
            start2, rows2 = node2
            
            # Fast check
            if configurations_conflict(order, start1, rows1, start2, rows2):
                G.add_edge(node1, node2)
                edges_added += 1

    print(f"Graph built with {n_nodes} nodes and {edges_added} conflicting edges.")
    
    # 3. Mine Maximal Cliques
    print("Mining maximal disjoint/overlapping cliques via approximation...")
    import networkx.algorithms.approximation as approx
    import time
    import random
    
    start_time = time.time()
    best_cliques = []
    
    G_copy = G.copy()
    for iteration in range(2000):
        if G_copy.number_of_nodes() == 0:
            break
            
        c = approx.max_clique(G_copy)
        if len(c) < 2:
            break
            
        # We want cliques that span MULTIPLE windows!
        windows_spanned = len(set(start for start, rows in c))
        if windows_spanned > 1:
            best_cliques.append(c)
            
        # Soft-remove: discard 50% of the clique's nodes to allow finding overlapping cliques
        nodes_to_remove = random.sample(list(c), max(1, len(c) // 2))
        G_copy.remove_nodes_from(nodes_to_remove)
        
        if time.time() - start_time > 60:
            print("Reached 60 second timeout for clique mining.")
            break

    print(f"Extracted {len(best_cliques)} dense structurally sound cliques.")
            
    best_cliques.sort(key=len, reverse=True)
    
    # Export the top 1000 largest cross-window cliques
    export_cliques = best_cliques[:1000]
    
    formatted_export = []
    for c in export_cliques:
        # Format: list of [start, r1, r2, r3, r4]
        formatted_export.append([ [start, rows[0], rows[1], rows[2], rows[3]] for start, rows in c ])
        
    print(f"Exporting top {len(export_cliques)} strongest structural conflict cliques.")
    args.output_file.write_text(json.dumps(formatted_export), encoding="utf-8")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
