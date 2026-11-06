# Unit test for BUG-DEAD-03: Self-deadlock on non-reentrant ReactorMutex
import unittest
from unittest.mock import MagicMock
from extras import machine_state_manager


class MockNonReentrantMutex:
    def __init__(self):
        self.locked = False

    def __enter__(self):
        if self.locked:
            raise RuntimeError("DEADLOCK: Non-reentrant lock acquired twice in same thread!")
        self.locked = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.locked = False


class TestBugDead03(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock()
        self.printer = MagicMock()
        self.reactor = MagicMock()
        self.printer.get_reactor.return_value = self.reactor
        self.reactor.mutex.side_effect = MockNonReentrantMutex
        self.config.get_printer.return_value = self.printer

        self.mgr = machine_state_manager.MachineStateManager(self.config)

    def test_reentrant_lock_in_post_hook(self):
        hook_called = []

        def recursive_post_hook(old_st, new_st):
            hook_called.append((old_st, new_st))
            # Nested call acquiring self.lock
            self.mgr.set_action_code("PRINTING")

        self.mgr.register_post_hook(recursive_post_hook)
        self.mgr.change_state(machine_state_manager.MachineMainState.PRINTING)

        self.assertEqual(len(hook_called), 1)
        self.assertEqual(self.mgr.action_code, "PRINTING")

    def test_reentrant_lock_in_pre_hook(self):
        pre_called = []

        def recursive_pre_hook(old_st, new_st):
            pre_called.append((old_st, new_st))
            # Nested call acquiring self.lock
            self.mgr.set_action_code("IDLE")
            return True

        self.mgr.register_pre_hook(recursive_pre_hook)
        self.mgr.change_state(machine_state_manager.MachineMainState.PRINTING)

        self.assertEqual(len(pre_called), 1)

    def test_hook_modification_during_iteration(self):
        def mutating_hook(old_st, new_st):
            # Mutates hooks list inside hook callback
            self.mgr.register_post_hook(lambda o, n: None)

        self.mgr.register_post_hook(mutating_hook)
        # Should not raise RuntimeError: Set changed size during iteration
        self.mgr.change_state(machine_state_manager.MachineMainState.PRINTING)


if __name__ == '__main__':
    unittest.main()

