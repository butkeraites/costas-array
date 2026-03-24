from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from itertools import combinations
import json
from pathlib import Path
import random
import sys
from time import time
from typing import Iterable, Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (ROOT_DIR, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import main
from export_function_features import secant_features


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a low-energy near-miss cloud for one Costas order."
    )
    parser.add_argument("order", type=int, help="Order N to study.")
    parser.add_argument(
        "--db-dir",
        type=Path,
        default=ROOT_DIR / "db",
        help="Directory containing Costas_essense_N=<n>.txt files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "artifacts" / "near-miss-cloud",
        help="Directory for the exported cloud.",
    )
    parser.add_argument(
        "--restarts",
        type=int,
        default=120,
        help="Number of local-search restarts.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=250,
        help="Maximum search steps per restart.",
    )
    parser.add_argument(
        "--samples-per-step",
        type=int,
        default=96,
        help="Number of swap moves to evaluate per step, including adjacent swaps.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=200,
        help="Maximum number of canonical near-miss states to retain.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=32,
        help="PRNG seed for reproducibility.",
    )
    parser.add_argument(
        "--reference-orders",
        nargs="*",
        type=int,
        help="Optional stored orders to export as a comparison feature cloud.",
    )
    return parser


@dataclass
class NearMissRecord:
    array: tuple[int, ...]
    energy: int
    violating_rows: int
    max_row_collisions: int
    visits: int
    source: str
    restart: int
    step: int


def permutation_to_points(array: Sequence[int]) -> list[tuple[int, int]]:
    return [(index + 1, value) for index, value in enumerate(array)]


def points_to_permutation(points: Iterable[tuple[int, int]], order: int) -> tuple[int, ...]:
    array = [0] * order
    seen_columns = set()
    seen_rows = set()
    for column, row in points:
        if not 1 <= column <= order or not 1 <= row <= order:
            raise ValueError("point lies outside the array bounds")
        if column in seen_columns or row in seen_rows:
            raise ValueError("transformed points do not define a permutation")
        seen_columns.add(column)
        seen_rows.add(row)
        array[column - 1] = row
    return tuple(array)


def transform_points(points: Iterable[tuple[int, int]], order: int, transform: str) -> list[tuple[int, int]]:
    transformed = []
    for column, row in points:
        if transform == "identity":
            transformed.append((column, row))
        elif transform == "vertical":
            transformed.append((order + 1 - column, row))
        elif transform == "horizontal":
            transformed.append((column, order + 1 - row))
        elif transform == "rotate180":
            transformed.append((order + 1 - column, order + 1 - row))
        elif transform == "diagonal":
            transformed.append((row, column))
        elif transform == "antidiagonal":
            transformed.append((order + 1 - row, order + 1 - column))
        elif transform == "rotate90":
            transformed.append((order + 1 - row, column))
        elif transform == "rotate270":
            transformed.append((row, order + 1 - column))
        else:
            raise ValueError(f"unknown transform: {transform}")
    return transformed


def d4_transforms(array: Sequence[int]) -> list[tuple[int, ...]]:
    points = permutation_to_points(array)
    order = len(array)
    transforms = [
        "identity",
        "vertical",
        "horizontal",
        "rotate180",
        "diagonal",
        "antidiagonal",
        "rotate90",
        "rotate270",
    ]
    seen = set()
    results = []
    for transform in transforms:
        candidate = points_to_permutation(transform_points(points, order, transform), order)
        if candidate not in seen:
            seen.add(candidate)
            results.append(candidate)
    return results


def canonical_array(array: Sequence[int]) -> tuple[int, ...]:
    return min(d4_transforms(array))


def collision_profile(array: Sequence[int]) -> list[int]:
    profile = []
    order = len(array)
    for width in range(1, order):
        counts: dict[int, int] = {}
        for index in range(order - width):
            difference = array[index + width] - array[index]
            counts[difference] = counts.get(difference, 0) + 1
        profile.append(sum(count * (count - 1) // 2 for count in counts.values()))
    return profile


def collision_energy(array: Sequence[int]) -> tuple[int, list[int]]:
    profile = collision_profile(array)
    return sum(profile), profile


def evaluate_array(array: Sequence[int]) -> tuple[int, int, int]:
    energy, profile = collision_energy(array)
    violating_rows = sum(value > 0 for value in profile)
    max_row_collisions = max(profile, default=0)
    return energy, violating_rows, max_row_collisions


def random_permutation(order: int, rng: random.Random) -> list[int]:
    array = list(range(1, order + 1))
    rng.shuffle(array)
    return array


def sample_swap_moves(order: int, sample_count: int, rng: random.Random) -> list[tuple[int, int]]:
    moves = {(index, index + 1) for index in range(order - 1)}
    max_unique_moves = order * (order - 1) // 2
    target = min(max_unique_moves, max(sample_count, len(moves)))
    while len(moves) < target:
        left, right = sorted(rng.sample(range(order), 2))
        moves.add((left, right))
    return list(moves)


def swapped(array: Sequence[int], left: int, right: int) -> list[int]:
    candidate = list(array)
    candidate[left], candidate[right] = candidate[right], candidate[left]
    return candidate


def perturb(array: Sequence[int], rng: random.Random, strength: int = 3) -> list[int]:
    candidate = list(array)
    for _ in range(strength):
        left, right = sorted(rng.sample(range(len(candidate)), 2))
        candidate[left], candidate[right] = candidate[right], candidate[left]
    return candidate


def generate_neighbor_seeds(order: int, db_dir: Path, limit: int) -> list[list[int]]:
    candidates: list[tuple[int, tuple[int, ...]]] = []
    seen = set()

    previous_path = db_dir / f"Costas_essense_N={order - 1}.txt"
    if previous_path.is_file():
        for array in main.read_arrays_for_order(order - 1, db_dir):
            for insert_column in range(order):
                for insert_row in range(1, order + 1):
                    candidate = tuple(main.augment_array_by_one(array, insert_column, insert_row))
                    if candidate in seen:
                        continue
                    seen.add(candidate)
                    energy, _profile = collision_energy(candidate)
                    candidates.append((energy, candidate))

    for gap in (1, 2):
        higher_order = order + gap
        higher_path = db_dir / f"Costas_essense_N={higher_order}.txt"
        if not higher_path.is_file():
            continue
        arrays = main.read_arrays_for_order(higher_order, db_dir)
        if not arrays:
            continue
        for array in arrays:
            for positions in combinations(range(higher_order), gap):
                candidate = tuple(main.delete_positions(array, positions))
                if candidate in seen:
                    continue
                seen.add(candidate)
                energy, _profile = collision_energy(candidate)
                candidates.append((energy, candidate))

    candidates.sort(key=lambda item: (item[0], item[1]))
    return [list(candidate) for _energy, candidate in candidates[:limit]]


def update_record(
    retained: dict[tuple[int, ...], NearMissRecord],
    array: Sequence[int],
    *,
    source: str,
    restart: int,
    step: int,
) -> None:
    canonical = canonical_array(array)
    energy, violating_rows, max_row_collisions = evaluate_array(canonical)
    existing = retained.get(canonical)
    if existing is None:
        retained[canonical] = NearMissRecord(
            array=canonical,
            energy=energy,
            violating_rows=violating_rows,
            max_row_collisions=max_row_collisions,
            visits=1,
            source=source,
            restart=restart,
            step=step,
        )
        return

    existing.visits += 1
    if energy < existing.energy:
        retained[canonical] = NearMissRecord(
            array=canonical,
            energy=energy,
            violating_rows=violating_rows,
            max_row_collisions=max_row_collisions,
            visits=existing.visits,
            source=source,
            restart=restart,
            step=step,
        )


def prune_records(retained: dict[tuple[int, ...], NearMissRecord], top_k: int) -> None:
    if len(retained) <= top_k:
        return
    best = sorted(
        retained.values(),
        key=lambda record: (
            record.energy,
            record.violating_rows,
            record.max_row_collisions,
            -record.visits,
            record.array,
        ),
    )[:top_k]
    retained.clear()
    for record in best:
        retained[record.array] = record


def run_local_search(
    order: int,
    *,
    db_dir: Path,
    restarts: int,
    steps: int,
    sample_count: int,
    top_k: int,
    rng: random.Random,
) -> tuple[dict[tuple[int, ...], NearMissRecord], dict[str, int]]:
    retained: dict[tuple[int, ...], NearMissRecord] = {}
    stats = {
        "states_evaluated": 0,
        "improving_moves": 0,
        "plateau_moves": 0,
        "kick_moves": 0,
        "zero_energy_hits": 0,
    }

    neighbor_seeds = generate_neighbor_seeds(order, db_dir, limit=max(8, restarts // 4))
    for restart in range(restarts):
        if restart < len(neighbor_seeds):
            current = list(neighbor_seeds[restart])
            source = "neighbor"
        else:
            current = random_permutation(order, rng)
            source = "random"

        current_energy, _, _ = evaluate_array(current)
        update_record(retained, current, source=source, restart=restart, step=0)
        stats["states_evaluated"] += 1
        if current_energy == 0:
            stats["zero_energy_hits"] += 1

        stagnation = 0
        for step in range(1, steps + 1):
            best_candidate = None
            best_energy = current_energy
            for left, right in sample_swap_moves(order, sample_count, rng):
                candidate = swapped(current, left, right)
                candidate_energy, _, _ = evaluate_array(candidate)
                stats["states_evaluated"] += 1
                if candidate_energy == 0:
                    stats["zero_energy_hits"] += 1
                if candidate_energy < best_energy or best_candidate is None:
                    best_candidate = candidate
                    best_energy = candidate_energy

            if best_candidate is None:
                break

            if best_energy < current_energy:
                current = best_candidate
                current_energy = best_energy
                stats["improving_moves"] += 1
                stagnation = 0
            elif best_energy == current_energy:
                current = best_candidate
                stats["plateau_moves"] += 1
                stagnation += 1
            else:
                current = perturb(current, rng)
                current_energy, _, _ = evaluate_array(current)
                stats["states_evaluated"] += 1
                if current_energy == 0:
                    stats["zero_energy_hits"] += 1
                stats["kick_moves"] += 1
                stagnation = 0

            update_record(retained, current, source=source, restart=restart, step=step)
            if stagnation >= 6:
                current = perturb(current, rng, strength=4)
                current_energy, _, _ = evaluate_array(current)
                stats["states_evaluated"] += 1
                if current_energy == 0:
                    stats["zero_energy_hits"] += 1
                stats["kick_moves"] += 1
                stagnation = 0
                update_record(retained, current, source=source, restart=restart, step=step)

        prune_records(retained, top_k * 3)

    prune_records(retained, top_k)
    return retained, stats


def is_transposition_neighbor(left: Sequence[int], right: Sequence[int]) -> bool:
    different = [index for index, (a, b) in enumerate(zip(left, right)) if a != b]
    if len(different) != 2:
        return False
    first, second = different
    return left[first] == right[second] and left[second] == right[first]


def graph_edges(records: Sequence[NearMissRecord]) -> list[dict[str, int | str]]:
    edges = []
    for left_index, left_record in enumerate(records):
        for right_index in range(left_index + 1, len(records)):
            right_record = records[right_index]
            if is_transposition_neighbor(left_record.array, right_record.array):
                edge_type = "adjacent-swap"
                positions = [index for index, (a, b) in enumerate(zip(left_record.array, right_record.array)) if a != b]
                if positions[1] - positions[0] > 1:
                    edge_type = "transposition"
                edges.append(
                    {
                        "left_id": left_index,
                        "right_id": right_index,
                        "edge_type": edge_type,
                    }
                )
    return edges


def component_sizes(node_count: int, edges: Sequence[dict[str, int | str]]) -> list[int]:
    adjacency = [[] for _ in range(node_count)]
    for edge in edges:
        left = int(edge["left_id"])
        right = int(edge["right_id"])
        adjacency[left].append(right)
        adjacency[right].append(left)

    seen = [False] * node_count
    sizes = []
    for start in range(node_count):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        size = 0
        while stack:
            node = stack.pop()
            size += 1
            for neighbor in adjacency[node]:
                if not seen[neighbor]:
                    seen[neighbor] = True
                    stack.append(neighbor)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def export_rows_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def reference_orders(order: int, db_dir: Path, explicit: Sequence[int] | None) -> list[int]:
    if explicit:
        return list(explicit)
    candidates = []
    for candidate in (order - 2, order - 1, order + 1, order + 2):
        if candidate < 1:
            continue
        path = db_dir / f"Costas_essense_N={candidate}.txt"
        if path.is_file() and main.read_arrays_for_order(candidate, db_dir):
            candidates.append(candidate)
    return candidates


def node_rows(records: Sequence[NearMissRecord]) -> list[dict[str, object]]:
    rows = []
    for index, record in enumerate(records):
        row = {
            "node_id": index,
            "array": " ".join(str(value) for value in record.array),
            "energy": record.energy,
            "violating_rows": record.violating_rows,
            "max_row_collisions": record.max_row_collisions,
            "visits": record.visits,
            "source": record.source,
            "restart": record.restart,
            "step": record.step,
        }
        row.update(secant_features(len(record.array), record.array))
        rows.append(row)
    return rows


def reference_rows(db_dir: Path, orders: Sequence[int]) -> list[dict[str, object]]:
    rows = []
    for order in orders:
        for array in main.read_arrays_for_order(order, db_dir):
            row = {
                "array": " ".join(str(value) for value in array),
                "energy": 0,
            }
            row.update(secant_features(order, array))
            rows.append(row)
    return rows


def main_entry(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    order = args.order
    db_dir = args.db_dir.resolve()
    rng = random.Random(args.seed)

    started = time()
    retained, stats = run_local_search(
        order,
        db_dir=db_dir,
        restarts=args.restarts,
        steps=args.steps,
        sample_count=args.samples_per_step,
        top_k=args.top_k,
        rng=rng,
    )
    records = sorted(
        retained.values(),
        key=lambda record: (
            record.energy,
            record.violating_rows,
            record.max_row_collisions,
            -record.visits,
            record.array,
        ),
    )
    edges = graph_edges(records)
    components = component_sizes(len(records), edges)

    output_dir = args.output_dir.resolve() / f"n{order}"
    output_dir.mkdir(parents=True, exist_ok=True)

    export_rows_csv(output_dir / "near_miss_nodes.csv", node_rows(records))
    export_rows_csv(output_dir / "near_miss_edges.csv", edges)

    refs = reference_orders(order, db_dir, args.reference_orders)
    if refs:
        export_rows_csv(output_dir / "reference_features.csv", reference_rows(db_dir, refs))

    summary = {
        "order": order,
        "seed": args.seed,
        "restarts": args.restarts,
        "steps": args.steps,
        "samples_per_step": args.samples_per_step,
        "top_k": args.top_k,
        "records": len(records),
        "best_energy": records[0].energy if records else None,
        "worst_energy": records[-1].energy if records else None,
        "component_count": len(components),
        "largest_component": components[0] if components else 0,
        "reference_orders": refs,
        "elapsed_seconds": round(time() - started, 3),
        "stats": stats,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Order N={order}")
    print(f"Retained nodes: {len(records)}")
    if records:
        print(f"Best energy: {records[0].energy}")
        print(f"Worst retained energy: {records[-1].energy}")
    print(f"Graph components: {len(components)}")
    if components:
        print(f"Largest component: {components[0]}")
    print(f"Output: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
