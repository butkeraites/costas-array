import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT_DIR / "scripts"
for path in (ROOT_DIR, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import mine_width_pressure as width_pressure


class WidthPressureTests(unittest.TestCase):
    def test_mine_width_pressure_ranks_repeated_widths(self) -> None:
        rows = [
            {"array": "1 2 3 4", "energy": "3"},
            {"array": "1 2 4 3", "energy": "0"},
            {"array": "1 3 2 4", "energy": "2"},
        ]

        pressure = width_pressure.mine_width_pressure(rows, max_energy=5)

        self.assertIn(1, pressure)
        self.assertGreater(pressure[1]["weighted_collisions"], 0)
        self.assertGreaterEqual(pressure[1]["weighted_collisions"], pressure.get(2, {"weighted_collisions": 0})["weighted_collisions"])

    def test_main_entry_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nodes_path = root / "near_miss_nodes.csv"
            with nodes_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["array", "energy"])
                writer.writeheader()
                writer.writerow({"array": "1 2 3 4", "energy": "3"})
                writer.writerow({"array": "1 3 2 4", "energy": "2"})

            output_path = root / "width_pressure.json"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = width_pressure.main_entry(
                    [
                        str(nodes_path),
                        "--max-energy",
                        "5",
                        "--top-widths",
                        "2",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertTrue(output_path.exists())
            self.assertIn("Selected widths:", stdout.getvalue())

            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["top_widths"], 2)
            self.assertTrue(result["selected_widths"])


if __name__ == "__main__":
    unittest.main()
