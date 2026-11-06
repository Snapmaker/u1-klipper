# Unit test for BUG-LOG-02: directory deletion and file flush in queuefile
import unittest
import tempfile
import os
import shutil
from unittest.mock import patch
import queuefile


class TestBugLog02(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='test_bug_log02_')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_delete_directory_recursively(self):
        listener = queuefile.QueueListener.__new__(queuefile.QueueListener)
        sub_dir = os.path.join(self.test_dir, 'subdir_to_delete')
        os.makedirs(sub_dir)
        nested_file = os.path.join(sub_dir, 'nested.txt')
        with open(nested_file, 'w') as f:
            f.write('nested content')

        self.assertTrue(os.path.isdir(sub_dir))
        op = queuefile.FileOperation('delete', sub_dir, sync=True)
        listener._process_operation(op)

        self.assertFalse(os.path.exists(sub_dir))
        self.assertIsNone(op.exception)

    def test_delete_regular_file(self):
        listener = queuefile.QueueListener.__new__(queuefile.QueueListener)
        file_path = os.path.join(self.test_dir, 'file_to_delete.txt')
        with open(file_path, 'w') as f:
            f.write('hello')

        self.assertTrue(os.path.isfile(file_path))
        op = queuefile.FileOperation('delete', file_path, sync=True)
        listener._process_operation(op)

        self.assertFalse(os.path.exists(file_path))
        self.assertIsNone(op.exception)

    def test_delete_nonexistent_path(self):
        listener = queuefile.QueueListener.__new__(queuefile.QueueListener)
        nonexistent = os.path.join(self.test_dir, 'nonexistent.txt')

        op = queuefile.FileOperation('delete', nonexistent, sync=True)
        listener._process_operation(op)

        self.assertFalse(os.path.exists(nonexistent))
        self.assertIsNone(op.exception)

    def test_write_and_append_with_flush(self):
        listener = queuefile.QueueListener.__new__(queuefile.QueueListener)
        file_path = os.path.join(self.test_dir, 'flush_test.txt')

        # Test safe write with flush
        op_write = queuefile.FileOperation(
            'write', file_path, content='first line\n',
            flush=True, safe_write=True, sync=True
        )
        listener._process_operation(op_write)
        self.assertTrue(os.path.exists(file_path))
        with open(file_path, 'r') as f:
            self.assertEqual(f.read(), 'first line\n')

        # Test append with flush
        op_append = queuefile.FileOperation(
            'append', file_path, content='second line\n',
            flush=True, safe_write=True, sync=True
        )
        listener._process_operation(op_append)
        with open(file_path, 'r') as f:
            self.assertEqual(f.read(), 'first line\nsecond line\n')

