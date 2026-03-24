from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = ROOT_DIR / "main.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a repeatable search suite for one Costas order."
    )
    parser.add_argument("order", type=int, help="Order N to search.")
    parser.add_argument(
        "--time-limit",
        type=float,
        default=60.0,
        help="Per-run time limit in seconds.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "artifacts" / "search-suite",
        help="Directory for logs and summary output.",
    )
    return parser


def run_command(command: list[str], log_path: Path) -> dict[str, object]:
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
    )
    log_path.write_text(result.stdout + ("\nSTDERR:\n" + result.stderr if result.stderr else ""), encoding="utf-8")
    return {
        "command": command,
        "exit_code": result.returncode,
        "log": str(log_path),
        "stdout_preview": result.stdout.strip().splitlines()[:8],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir.resolve() / f"n{args.order}"
    output_dir.mkdir(parents=True, exist_ok=True)

    cnf_path = output_dir / f"costas_{args.order}.cnf"
    commands = {
        "native": [
            sys.executable,
            str(MAIN_PY),
            "search",
            str(args.order),
            "--backend",
            "native",
            "--time-limit",
            str(args.time_limit),
        ],
        "kissat": [
            sys.executable,
            str(MAIN_PY),
            "search",
            str(args.order),
            "--backend",
            "sat",
            "--sat-solver",
            "kissat",
            "--time-limit",
            str(args.time_limit),
            "--cnf-path",
            str(cnf_path),
            "--keep-cnf",
        ],
        "cadical": [
            sys.executable,
            str(MAIN_PY),
            "search",
            str(args.order),
            "--backend",
            "sat",
            "--sat-solver",
            "cadical",
            "--time-limit",
            str(args.time_limit),
            "--cnf-path",
            str(cnf_path),
            "--keep-cnf",
        ],
    }

    summary = {
        "order": args.order,
        "time_limit": args.time_limit,
        "output_dir": str(output_dir),
        "runs": {},
    }

    for name, command in commands.items():
        log_path = output_dir / f"{name}.log"
        summary["runs"][name] = run_command(command, log_path)

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote search suite outputs to {output_dir}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
