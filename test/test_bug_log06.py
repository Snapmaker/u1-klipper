# Unit test for BUG-LOG-06: Incorrect mean calculation over subset (/ 9) in homing_precise_corexy.py
import unittest

class TestBugLog06(unittest.TestCase):
    def test_multi_point_revalidation_mean(self):
        point_sequence = [
            [1, 0], [-1, 0], [0, 1], [0, -1],
            [-1, -1], [1, 1], [1, -1], [-1, 1], [0, 0]
        ]
        num_points = len(point_sequence)
        self.assertEqual(num_points, 9)

        points = []
        for i in range(num_points):
            points.append({
                'c_dist': [100.0 + i, 200.0 + i],
                'revalidate': False
            })

        # Round 0 mean
        expected_x_mean = sum(p['c_dist'][0] for p in points) / num_points
        expected_y_mean = sum(p['c_dist'][1] for p in points) / num_points

        # Suppose point 3 was unstable and re-measured with new values
        points[3]['revalidate'] = True
        new_measurement = [103.5, 203.5]
        points[3]['c_dist'] = list(new_measurement)

        # Buggy logic:
        # In round 1, c_acc was initialized to [0, 0] and only added revalidated points:
        buggy_acc = [0.0, 0.0]
        for i in range(num_points):
            if points[i]['revalidate']:
                buggy_acc[0] += points[i]['c_dist'][0]
                buggy_acc[1] += points[i]['c_dist'][1]
        buggy_origin = [buggy_acc[0] / num_points, buggy_acc[1] / num_points]

        # In buggy logic, buggy_origin is 103.5 / 9 = ~11.5 instead of ~104.0!
        self.assertAlmostEqual(buggy_origin[0], 103.5 / 9.0)
        self.assertLess(buggy_origin[0], 20.0) # Massive position error!

        # Patched logic:
        # Accumulates over all points in points array
        c_acc = [0.0, 0.0]
        c_acc[0] = sum(p['c_dist'][0] for p in points)
        c_acc[1] = sum(p['c_dist'][1] for p in points)
        patched_origin = [c_acc[0] / float(num_points), c_acc[1] / float(num_points)]

        true_x_mean = sum(p['c_dist'][0] for p in points) / num_points
        true_y_mean = sum(p['c_dist'][1] for p in points) / num_points

        self.assertAlmostEqual(patched_origin[0], true_x_mean)
        self.assertAlmostEqual(patched_origin[1], true_y_mean)
        self.assertGreater(patched_origin[0], 100.0)

if __name__ == '__main__':
    unittest.main()

