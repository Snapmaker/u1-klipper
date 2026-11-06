# Unit test for BUG-LOG-07: circle center math, lstsq validation, and hole_z fallback
import unittest
from unittest.mock import MagicMock
import extras.probe_inductance_coil as pic


class TestBugLog07(unittest.TestCase):
    def test_find_circle_center_exact_math(self):
        # Circle with center (3.0, 2.0) and r = sqrt(5)
        # Points: (1, 1), (2, 4), (5, 3)
        h, k = pic.find_circle_center((1, 1), (2, 4), (5, 3))
        self.assertAlmostEqual(h, 3.0, places=6)
        self.assertAlmostEqual(k, 2.0, places=6)

    def test_find_circle_center_collinear_raises(self):
        # Collinear points on line y = x
        with self.assertRaises(ValueError):
            pic.find_circle_center((0, 0), (1, 1), (2, 2))

    def test_least_squares_circle_center_valid(self):
        helper = pic.ProbeCommandHelper.__new__(pic.ProbeCommandHelper)
        # Circle centered at (50.0, 60.0) with radius 10.0
        # Points at 0, 90, 180, 270 degrees
        pts = [
            [60.0, 60.0],
            [50.0, 70.0],
            [40.0, 60.0],
            [50.0, 50.0]
        ]
        cx, cy = helper.find_circle_center_least_squares(pts)
        self.assertAlmostEqual(cx, 50.0, places=4)
        self.assertAlmostEqual(cy, 60.0, places=4)

    def test_least_squares_collinear_and_underdetermined_raises(self):
        helper = pic.ProbeCommandHelper.__new__(pic.ProbeCommandHelper)
        # Less than 3 points
        with self.assertRaises(ValueError):
            helper.find_circle_center_least_squares([[1.0, 2.0], [3.0, 4.0]])

        # Collinear points
        with self.assertRaises(ValueError):
            helper.find_circle_center_least_squares([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])

    def test_macro_hole_z_fallback(self):
        # Simulate macro where hole_z is omitted
        initial_hole_x = 150.0
        initial_hole_y = 120.0
        initial_hole_z = 2.5

        macro = MagicMock()
        macro.variables = {
            'hole_x': 155.0,
            'hole_y': 125.0
            # 'hole_z' intentionally omitted
        }

        hole_position = [
            macro.variables.get('hole_x', initial_hole_x),
            macro.variables.get('hole_y', initial_hole_y),
            macro.variables.get('hole_z', initial_hole_z)
        ]

        self.assertEqual(hole_position[0], 155.0)
        self.assertEqual(hole_position[1], 125.0)
        # Must retain initial_hole_z (2.5), NOT fallback to hole_x (150.0 or 155.0)
        self.assertEqual(hole_position[2], 2.5)

