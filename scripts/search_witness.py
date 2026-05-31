"""Parallel stochastic search for a Costas-array witness of a given order.

Runs independent min-conflicts/tabu local-search workers (see
``costas_local_search``) across processes, each doing random restarts, and stops
as soon as any worker reaches energy 0 (a Costas array) or the time budget runs
out. A live status line shows elapsed/deadline, the global best energy, total
restarts and throughput.

IMPORTANT (measured): local search solves moderate orders well but its
per-restart success probability collapses with order (≈40/40 at N=8, ≈1/40 at
N=16, ≈0 by N=20). For the open order N=32 a witness is extremely unlikely to be
found this way — see docs/dyadic_obstruction_findings.md. This tool is most
useful up to ~N=14 and as a (very) long-odds probe beyond that.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import costas_local_search as ls
import main
from progress import ProgressBar


def worker(order, seed, target, deadline, steps_per_restart, found, queue):
    import random

    rng = random.Random(seed)
    base = list(range(1, order + 1))
    best_energy = None
    best_perm = None
    restarts = 0
    last_report = 0.0
    while not found.is_set() and time.time() < deadline:
        start = base[:]
        rng.shuffle(start)
        state = ls.CostasEnergy(start)
        e = ls.optimize(
            state,
            rng,
            max_steps=steps_per_restart,
            target=target,
            patience=3 * order,
            kick_strength=max(2, order // 5),
        )
        restarts += 1
        improved = best_energy is None or e < best_energy
        if improved:
            best_energy = e
            best_perm = state.perm[:]
        now = time.time()
        if improved or now - last_report > 0.5:
            queue.put((seed, restarts, best_energy, best_perm if improved else None))
            last_report = now
        if best_energy is not None and best_energy <= target:
            found.set()
            break
    queue.put((seed, restarts, best_energy, best_perm))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Parallel local search for a Costas-array witness.")
    p.add_argument("order", type=int)
    p.add_argument("--workers", type=int, default=max(1, (mp.cpu_count() or 2) - 1))
    p.add_argument("--time-limit", type=float, default=120.0, help="Wall-clock budget in seconds.")
    p.add_argument("--target", type=int, default=0, help="Stop when energy <= target (0 = a Costas array).")
    p.add_argument("--steps", type=int, default=4000, help="Local-search steps per restart.")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=None, help="Where to save the best permutation found.")
    p.add_argument("--no-progress", dest="progress", action="store_false")
    p.set_defaults(progress=True)
    return p


def main_entry(argv=None) -> int:
    args = build_parser().parse_args(argv)
    order = args.order
    out_path = args.out or (ROOT_DIR / "artifacts" / "witness" / f"n{order}_best.txt")

    ctx = mp.get_context("spawn")
    found = ctx.Event()
    queue = ctx.Queue()
    deadline = time.time() + args.time_limit
    start = time.time()

    procs = []
    for w in range(args.workers):
        proc = ctx.Process(
            target=worker,
            args=(order, args.seed + w * 100003, args.target, deadline, args.steps, found, queue),
        )
        proc.start()
        procs.append(proc)

    best_energy = None
    best_perm = None
    per_worker_restarts: dict[int, int] = {}

    bar = ProgressBar(
        int(args.time_limit),
        enabled=args.progress,
        show_rate=False,
        label=f"witness N={order}",
    )

    try:
        while any(p.is_alive() for p in procs) or not queue.empty():
            try:
                seed, restarts, energy, perm = queue.get(timeout=0.2)
            except Exception:
                pass
            else:
                per_worker_restarts[seed] = restarts
                if energy is not None and (best_energy is None or energy < best_energy):
                    best_energy = energy
                    if perm is not None:
                        best_perm = perm
            elapsed = time.time() - start
            total_restarts = sum(per_worker_restarts.values())
            rate = total_restarts / elapsed if elapsed > 0 else 0
            bar.update(
                done=min(int(elapsed), int(args.time_limit)),
                best=best_energy if best_energy is not None else "?",
                restarts=total_restarts,
                rps=f"{rate:.0f}/s",
                workers=args.workers,
            )
            if best_energy is not None and best_energy <= args.target:
                found.set()
                break
            if time.time() >= deadline:
                break
    finally:
        found.set()
        for proc in procs:
            proc.join(timeout=2)
            if proc.is_alive():
                proc.terminate()
        bar.close()

    print(f"\nOrder N={order}: best energy = {best_energy}  (target {args.target})")
    print(f"Total restarts: {sum(per_worker_restarts.values())}  over {args.workers} workers")
    if best_perm is not None:
        is_costas = main.is_costas_array(best_perm)
        print(f"Best permutation (is_costas={is_costas}):")
        print("  " + " ".join(str(v) for v in best_perm))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(" ".join(str(v) for v in best_perm) + "\n", encoding="utf-8")
        print(f"Saved to {out_path}")
        if is_costas:
            print("*** WITNESS FOUND: this is a valid Costas array. ***")
            return 0
    return 0 if (best_energy is not None and best_energy <= args.target) else 1


if __name__ == "__main__":
    raise SystemExit(main_entry())
