import unittest

from local_window4 import (
    endpoint_window_starts,
    is_consecutive_window4_costas,
    iter_consecutive_window4_feasible_tuples,
)


class LocalWindow4Tests(unittest.TestCase):
    def test_endpoint_window_starts_deduplicates_small_orders(self) -> None:
        self.assertEqual(endpoint_window_starts(4, 2), [1])
        self.assertEqual(endpoint_window_starts(8, 2), [1, 2, 4, 5])

    def test_local_costas_check_matches_examples(self) -> None:
        self.assertTrue(is_consecutive_window4_costas((1, 2, 4, 3)))
        self.assertFalse(is_consecutive_window4_costas((1, 2, 3, 4)))

    def test_feasible_tuple_iterator_respects_local_costas(self) -> None:
        tuples = list(
            iter_consecutive_window4_feasible_tuples(
                [
                    [1],
                    [2, 3],
                    [3, 4],
                    [2, 4],
                ],
                1,
            )
        )
        self.assertIn((1, 3, 4, 2), tuples)
        self.assertNotIn((1, 2, 3, 4), tuples)


if __name__ == "__main__":
    unittest.main()
