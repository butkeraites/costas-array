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

import build_near_miss_cloud as cloud


class NearMissCloudTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_dir = self.root / "db"
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

    def test_canonical_array_is_d4_invariant(self) -> None:
        array = (1, 3, 4, 2)
        canonical = cloud.canonical_array(array)

        for transform in cloud.d4_transforms(array):
            self.assertEqual(cloud.canonical_array(transform), canonical)

    def test_collision_energy_detects_valid_and_invalid_arrays(self) -> None:
        energy, profile = cloud.collision_energy([1, 2, 4, 3])
        self.assertEqual(energy, 0)
        self.assertEqual(profile, [0, 0, 0])

        bad_energy, _bad_profile = cloud.collision_energy([1, 2, 3, 4])
        self.assertGreater(bad_energy, 0)

    def test_main_entry_writes_cloud_artifacts(self) -> None:
        output_dir = self.root / "artifacts"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cloud.main_entry(
                [
                    "5",
                    "--db-dir",
                    str(self.db_dir),
                    "--output-dir",
                    str(output_dir),
                    "--restarts",
                    "6",
                    "--steps",
                    "12",
                    "--samples-per-step",
                    "18",
                    "--top-k",
                    "8",
                    "--seed",
                    "5",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Order N=5", stdout.getvalue())

        order_dir = output_dir / "n5"
        nodes_path = order_dir / "near_miss_nodes.csv"
        edges_path = order_dir / "near_miss_edges.csv"
        refs_path = order_dir / "reference_features.csv"
        summary_path = order_dir / "summary.json"

        self.assertTrue(nodes_path.exists())
        self.assertTrue(edges_path.exists())
        self.assertTrue(refs_path.exists())
        self.assertTrue(summary_path.exists())

        with nodes_path.open(encoding="utf-8", newline="") as handle:
            nodes = list(csv.DictReader(handle))
        self.assertTrue(nodes)
        self.assertLessEqual(len(nodes), 8)
        self.assertIn("energy", nodes[0])
        self.assertIn("mirror_width_1", nodes[0])

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["order"], 5)
        self.assertEqual(summary["records"], len(nodes))
        self.assertGreaterEqual(summary["stats"]["states_evaluated"], len(nodes))


if __name__ == "__main__":
    unittest.main()
