# Unit test for BUG-DEAD-02: Mutex deadlocks in filament_feed and filament_feed_fac_test
import unittest
from unittest.mock import MagicMock
from extras import filament_feed
from extras import filament_feed_fac_test


class TestBugDead02(unittest.TestCase):
    def setUp(self):
        self.printer = MagicMock()
        self.reactor = MagicMock()
        self.printer.is_shutdown.return_value = False
        self.cfg = MagicMock()
        self.cfg.max_value = 100

    def test_feed_motor_release_on_exception(self):
        motor = filament_feed.FeedMotor(self.printer, self.reactor, self.cfg)
        motor._run = MagicMock(side_effect=RuntimeError("PWM hardware failure"))

        with self.assertRaises(RuntimeError):
            motor.run(1, 100)

        # Mutex must be released in finally block
        self.assertFalse(motor._mutex_lock)

    def test_feed_motor_fac_test_release_on_exception(self):
        motor = filament_feed_fac_test.FeedMotor(
            self.printer, self.reactor, self.cfg
        )
        motor._run = MagicMock(side_effect=RuntimeError("Test motor error"))

        with self.assertRaises(RuntimeError):
            motor.run(1, 100)

        # Mutex must be released in finally block
        self.assertFalse(motor._mutex_lock)

    def test_feed_motor_shutdown_immediate_return(self):
        self.printer.is_shutdown.return_value = True
        motor = filament_feed.FeedMotor(self.printer, self.reactor, self.cfg)
        motor._mutex_lock = True

        # Should not block in pause loop
        motor.run(1, 100)
        motor.run_one_cycle(1, 100, 1.0)

    def test_feed_motor_one_cycle_release_on_exception(self):
        motor = filament_feed.FeedMotor(self.printer, self.reactor, self.cfg)
        motor._run_one_cycle = MagicMock(
            side_effect=RuntimeError("Cycle timer exception")
        )

        with self.assertRaises(RuntimeError):
            motor.run_one_cycle(1, 100, 0.5)

        self.assertFalse(motor._mutex_lock)


if __name__ == '__main__':
    unittest.main()

