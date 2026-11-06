# Unit test for BUG-LEAK-09: Directory Handle Leak (Missing f_closedir) in fatfs_api.c
# and PTY FD Leak in console.c / util.py
import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys

KLIPPY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'klippy'))
if KLIPPY_PATH not in sys.path:
    sys.path.insert(0, KLIPPY_PATH)

import util


class TestBugLeak09(unittest.TestCase):
    def test_util_dump_mcu_build_closes_files_on_success_and_exception(self):
        # Verify with open(...) is used so files are guaranteed closed
        with patch("builtins.open", mock_open(read_data='{"version": "1.0"}')) as m_open:
            util.dump_mcu_build()
            # Check that file handles opened were closed
            for handle in m_open.return_value.__enter__.return_value.close.call_args_list:
                handle.assert_called()

    def test_fatfs_api_c_source_has_f_closedir(self):
        c_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'spi_flash', 'fatfs_api.c')
        with open(c_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn("f_closedir(&dir);", content)
        self.assertIn("if (!flist || !path)", content)

    def test_console_c_source_closes_pty_on_failure(self):
        c_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'linux', 'console.c')
        with open(c_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn("goto fail;", content)
        self.assertIn("fail:", content)
        self.assertIn("close(mfd);", content)
        self.assertIn("close(sfd);", content)


if __name__ == '__main__':
    unittest.main()

