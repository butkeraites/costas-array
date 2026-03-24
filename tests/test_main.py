import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import main

HAS_KISSAT = shutil.which("kissat") is not None
HAS_CADICAL = shutil.which("cadical") is not None
HAS_GXX = shutil.which("g++") is not None


class CostasCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name) / "db"
        self.db_dir.mkdir()

        self.write_order_file(
            4,
            [
                "1 2 4 3",
                "1 3 4 2",
            ],
        )
        self.write_order_file(
            5,
            [
                "1 3 4 2 5",
                "1 4 3 5 2",
                "2 4 1 5 3",
            ],
        )
        self.write_order_file(6, ["No Costas arrays."])

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_order_file(self, order: int, lines: list[str]) -> None:
        path = self.db_dir / f"Costas_essense_N={order}.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main.main(["--db-dir", str(self.db_dir), *args])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_is_costas_array(self) -> None:
        self.assertTrue(main.is_costas_array([1, 2, 4, 3]))
        self.assertFalse(main.is_costas_array([1, 2, 3, 4]))
        self.assertFalse(main.is_costas_array([1, 1, 3, 4]))

    def test_parse_assignment_specs(self) -> None:
        self.assertEqual(main.parse_assignment_specs(["1=2", "4=3"], order=4), [(1, 2), (4, 3)])

        with self.assertRaises(ValueError):
            main.parse_assignment_specs(["1-2"], order=4)
        with self.assertRaises(ValueError):
            main.parse_assignment_specs(["5=2"], order=4)
        with self.assertRaises(ValueError):
            main.parse_assignment_specs(["1=2", "1=3"], order=4)
        with self.assertRaises(ValueError):
            main.parse_assignment_specs(["1=2", "3=2"], order=4)

    def test_default_command_is_summary(self) -> None:
        exit_code, stdout, stderr = self.run_cli()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Orders scanned: 3", stdout)
        self.assertIn("Total arrays: 5", stdout)
        self.assertIn("Orders with no stored arrays:", stdout)

    def test_summary_all_lists_each_order(self) -> None:
        exit_code, stdout, _stderr = self.run_cli("summary", "--all")

        self.assertEqual(exit_code, 0)
        self.assertIn("N=4: 2", stdout)
        self.assertIn("N=5: 3", stdout)
        self.assertIn("N=6: 0 (empty)", stdout)

    def test_show_respects_limit(self) -> None:
        exit_code, stdout, stderr = self.run_cli("show", "5", "--limit", "2")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Order N=5", stdout)
        self.assertIn("Stored arrays: 3", stdout)
        self.assertIn("Displayed 2 of 3 arrays.", stdout)

    def test_validate_reports_success(self) -> None:
        exit_code, stdout, stderr = self.run_cli("validate")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("5 arrays checked, no problems found.", stdout)

    def test_validate_reports_failure_for_invalid_array(self) -> None:
        self.write_order_file(7, ["1 2 3 4 5 6 7"])

        exit_code, stdout, stderr = self.run_cli("validate", "7")

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr, "")
        self.assertIn("Validation failed", stdout)
        self.assertIn("not a valid Costas array", stdout)

    def test_search_finds_example_for_small_order(self) -> None:
        exit_code, stdout, stderr = self.run_cli("search", "4", "--time-limit", "1")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Status: example found", stdout)
        self.assertIn("Repository status: 2 stored array(s)", stdout)
        self.assertIn("database: found", stdout)

    def test_database_shortcut_respects_fixed_assignments(self) -> None:
        attempt = main.search_via_database(4, self.db_dir, assignments=[(1, 4)])

        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.status, "unknown")
        self.assertIn("none satisfy the fixed assignments", attempt.detail)

    @unittest.skipUnless(HAS_GXX, "g++ is required for native backend tests")
    def test_native_backend_accepts_fixed_assignments(self) -> None:
        self.write_order_file(7, ["No Costas arrays."])
        exit_code, stdout, stderr = self.run_cli(
            "search",
            "7",
            "--backend",
            "native",
            "--time-limit",
            "3",
            "--assign",
            "1=1",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Winning backend: native", stdout)
        self.assertIn("native: found", stdout)
        self.assertIn("fixed assignment", stdout)

    def test_assign_requires_auto_native_or_sat_backend(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            "search",
            "6",
            "--backend",
            "z3",
            "--assign",
            "1=1",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("--assign can only be used with --backend auto, native, or sat", stderr)

    def test_export_cnf_writes_file(self) -> None:
        output = self.db_dir.parent / "order4.cnf"

        exit_code, stdout, stderr = self.run_cli("export-cnf", "4", str(output))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(output.exists())
        header = output.read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(header.startswith("p cnf "))
        self.assertIn("Wrote CNF for N=4", stdout)

    def test_export_cnf_accepts_assignments_and_window4_radius(self) -> None:
        output = self.db_dir.parent / "order4_fixed.cnf"

        exit_code, stdout, stderr = self.run_cli(
            "export-cnf",
            "4",
            str(output),
            "--assign",
            "1=1",
            "--assign",
            "4=2",
            "--sat-window4-radius",
            "1",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(output.exists())
        self.assertIn("Assignments: 1=1 4=2", stdout)
        self.assertIn("Window4 endpoint radius: 1", stdout)

    @unittest.skipUnless(HAS_KISSAT, "kissat is required for SAT backend tests")
    def test_sat_backend_finds_example_when_database_is_empty(self) -> None:
        self.write_order_file(5, ["No Costas arrays."])
        output = self.db_dir.parent / "order6.cnf"

        exit_code, stdout, stderr = self.run_cli(
            "search",
            "6",
            "--backend",
            "sat",
            "--time-limit",
            "5",
            "--cnf-path",
            str(output),
            "--keep-cnf",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(output.exists())
        self.assertIn("Winning backend: sat", stdout)
        self.assertIn("sat: found", stdout)

    @unittest.skipUnless(HAS_KISSAT, "kissat is required for SAT backend tests")
    def test_sat_backend_accepts_assignments_and_window4_radius(self) -> None:
        self.write_order_file(5, ["No Costas arrays."])
        output = self.db_dir.parent / "order6_fixed.cnf"

        exit_code, stdout, stderr = self.run_cli(
            "search",
            "6",
            "--backend",
            "sat",
            "--time-limit",
            "5",
            "--assign",
            "1=1",
            "--sat-window4-radius",
            "1",
            "--cnf-path",
            str(output),
            "--keep-cnf",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(output.exists())
        self.assertIn("Winning backend: sat", stdout)
        self.assertIn("sat: found", stdout)

    @unittest.skipUnless(HAS_CADICAL, "cadical is required for SAT backend tests")
    def test_cadical_backend_finds_example_when_database_is_empty(self) -> None:
        self.write_order_file(5, ["No Costas arrays."])
        output = self.db_dir.parent / "order6_cadical.cnf"

        exit_code, stdout, stderr = self.run_cli(
            "search",
            "6",
            "--backend",
            "sat",
            "--sat-solver",
            "cadical",
            "--time-limit",
            "5",
            "--cnf-path",
            str(output),
            "--keep-cnf",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(output.exists())
        self.assertIn("Winning backend: sat", stdout)
        self.assertIn("sat: found", stdout)


if __name__ == "__main__":
    unittest.main()
