import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT_DIR / "scripts"
for path in (ROOT_DIR, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import lp_shard_relaxation as lp_relaxation


class LpShardRelaxationTests(unittest.TestCase):
    def test_parse_width_spec(self) -> None:
        self.assertEqual(lp_relaxation.parse_width_spec("short4", 8), [1, 2, 3, 4])
        self.assertEqual(lp_relaxation.parse_width_spec("dyadic", 10), [1, 2, 4, 8])
        self.assertEqual(lp_relaxation.parse_width_spec("1,3,3,5", 8), [1, 3, 5])

    def test_small_feasible_shard(self) -> None:
        result = lp_relaxation.solve_relaxation(
            4,
            widths=[1, 2, 3],
            assignments=[(1, 1), (4, 2)],
            solver_name="PDLP",
            time_limit_seconds=5.0,
            triangle_mode="none",
        )
        self.assertEqual(result.status, "feasible")

    def test_small_infeasible_shard(self) -> None:
        result = lp_relaxation.solve_relaxation(
            4,
            widths=[1, 2, 3],
            assignments=[(1, 1), (4, 4)],
            solver_name="PDLP",
            time_limit_seconds=5.0,
            triangle_mode="none",
        )
        self.assertEqual(result.status, "infeasible")

    def test_symmetry_domain_shortcut_detects_impossible_endpoint(self) -> None:
        result = lp_relaxation.solve_relaxation(
            4,
            widths=[1, 2, 3],
            assignments=[(1, 3), (4, 2)],
            solver_name="PDLP",
            time_limit_seconds=5.0,
            triangle_mode="consecutive",
        )
        self.assertEqual(result.status, "infeasible")
        self.assertEqual(result.solver_status, "DOMAIN_INFEASIBLE")

    def test_triangle_mode_stays_feasible_on_small_shard(self) -> None:
        result = lp_relaxation.solve_relaxation(
            4,
            widths=[1, 2, 3],
            assignments=[(1, 1), (4, 2)],
            solver_name="PDLP",
            time_limit_seconds=5.0,
            triangle_mode="consecutive",
        )
        self.assertEqual(result.status, "feasible")

    def test_window4_triangle_mode_stays_feasible_on_small_shard(self) -> None:
        result = lp_relaxation.solve_relaxation(
            4,
            widths=[1, 2, 3],
            assignments=[(1, 1), (4, 2)],
            solver_name="PDLP",
            time_limit_seconds=5.0,
            triangle_mode="window4",
        )
        self.assertEqual(result.status, "feasible")

    def test_endpoint_quad_mode_stays_feasible_on_small_shard(self) -> None:
        result = lp_relaxation.solve_relaxation(
            4,
            widths=[1, 2, 3],
            assignments=[(1, 1), (4, 2)],
            solver_name="PDLP",
            time_limit_seconds=5.0,
            triangle_mode="window4",
            quad_mode="endpoints",
            quad_radius=1,
        )
        self.assertEqual(result.status, "feasible")

    def test_main_entry_prints_summary(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = lp_relaxation.main_entry(
                [
                    "4",
                    "--assign",
                    "1=1",
                    "--assign",
                    "4=2",
                    "--widths",
                    "1,2,3",
                    "--triangles",
                    "consecutive",
                    "--quads",
                    "endpoints",
                    "--quad-radius",
                    "1",
                    "--time-limit",
                    "5",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("status=feasible", stdout.getvalue())
        self.assertIn("variables=", stdout.getvalue())
        self.assertIn("triangles=consecutive", stdout.getvalue())
        self.assertIn("quads=endpoints", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
