import unittest

FM175XX_CHANNEL_NUMS = 4
FM175XX_OK = 0
FM175XX_CARD_COMM_ERR = 1

class MockOutParam:
    def __init__(self, bits_recved=4, recv_buff=None):
        self.bits_recved = bits_recved
        self.recv_buff = recv_buff if recv_buff is not None else []

class MockResult:
    def __init__(self, err_code=FM175XX_OK, bits_recved=4, recv_buff=None):
        self.err_code = err_code
        self.out_param = MockOutParam(bits_recved, recv_buff)

class MockPrinter:
    def command_error(self, msg):
        return ValueError(msg)

class MockSPI:
    def __init__(self, response):
        self.response = response
    def spi_transfer(self, data):
        return {'response': self.response}

class TestBugBuf12(unittest.TestCase):
    def test_fm175xx_channel_bounds(self):
        def check_channel(channel):
            if channel < 0 or channel >= FM175XX_CHANNEL_NUMS:
                return False
            return True

        self.assertTrue(check_channel(0))
        self.assertTrue(check_channel(3))
        # Off-by-one check: channel 4 was accepted under (channel > 4) bug
        self.assertFalse(check_channel(4))
        self.assertFalse(check_channel(-1))

    def test_fm175xx_empty_recv_buff(self):
        # Empty recv_buff would raise IndexError if unguarded
        result = MockResult(err_code=FM175XX_OK, bits_recved=4, recv_buff=[])

        # Mimic line 797 with defensive check
        if ((result.err_code != FM175XX_OK) or (result.out_param.bits_recved != 4) or
                not result.out_param.recv_buff or (result.out_param.recv_buff[0] & 0x0F != 0x0A)):
            ret = FM175XX_CARD_COMM_ERR
        else:
            ret = FM175XX_OK
        self.assertEqual(ret, FM175XX_CARD_COMM_ERR)

        # Mimic line 809 with defensive check
        if ((result.out_param.bits_recved != 4) or not result.out_param.recv_buff or
                (result.out_param.recv_buff[0] & 0x0F != 0x0A)):
            ret2 = FM175XX_CARD_COMM_ERR
        else:
            ret2 = FM175XX_OK
        self.assertEqual(ret2, FM175XX_CARD_COMM_ERR)

    def test_sc7a20_empty_spi_response(self):
        printer = MockPrinter()

        def read_reg(spi, reg):
            params = spi.spi_transfer([reg | 0x80, 0x00])
            response = bytearray(params.get('response', b''))
            if len(response) < 2:
                msg = f"Failed to read SC7A20 register [0x{reg:02x}]: response too short ({len(response)} bytes)"
                raise printer.command_error(msg)
            return response[1]

        # Valid 2-byte response
        spi_ok = MockSPI(b"\x00\x11")
        self.assertEqual(read_reg(spi_ok, 0x0F), 0x11)

        # Empty response raises command_error instead of IndexError
        spi_empty = MockSPI(b"")
        with self.assertRaises(ValueError) as ctx:
            read_reg(spi_empty, 0x0F)
        self.assertIn("response too short (0 bytes)", str(ctx.exception))

        # Single-byte response raises command_error
        spi_short = MockSPI(b"\x00")
        with self.assertRaises(ValueError) as ctx:
            read_reg(spi_short, 0x0F)
        self.assertIn("response too short (1 bytes)", str(ctx.exception))

if __name__ == '__main__':
    unittest.main()

