import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import main


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


if __name__ == "__main__":
    unittest.main()
