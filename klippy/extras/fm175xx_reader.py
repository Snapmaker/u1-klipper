import logging, time, threading, copy
import spidev
import hmac, hashlib

# channels
FM175XX_CHANNEL_NUMS                    = 4
FM175XX_CHANNEL_1                       = 0
FM175XX_CHANNEL_2                       = 1
FM175XX_CHANNEL_3                       = 2
FM175XX_CHANNEL_4                       = 3

# Error code
FM175XX_OK                              = 0
FM175XX_ERR                             = -1
FM175XX_PARAM_ERR                       = -2
FM175XX_CHIP_TYPE_ERR                   = -10
FM175XX_CHIP_COMM_ERR                   = -11
FM175XX_CARD_TIMER_ERR                  = -20
FM175XX_CARD_LENGTH_ERR                 = -21
FM175XX_CARD_COMM_ERR                   = -22
FM175XX_CARD_AUTH_ERR                   = -23
FM175XX_CARD_WAKEUP_ERR                 = -24
FM175XX_CARD_COLL_ERR                   = -25
FM175XX_CARD_SELECT_ERR                 = -26
FM175XX_CARD_ACTIVATE_ERR               = -27
FM175XX_CARD_HALT_ERR                   = -28
FM175XX_CARD_READ_ERR                   = -29
FM175XX_CARD_WRITE_ERR                  = -30

# Mask
FM175XX_RESET                           = 0
FM175XX_SET                             = 1

# FM175xx register address
FM175XX_COMMAND_REG                     = 0x01
FM175XX_COM_I_EN_REG                    = 0x02
FM175XX_DIV_I_EN_REG                    = 0x03
FM175XX_COM_IRQ_REG                     = 0x04
FM175XX_DIV_IRQ_REG                     = 0x05
FM175XX_ERROR_REG                       = 0x06
FM175XX_STATUS_1_REG                    = 0x07
FM175XX_STATUS_2_REG                    = 0x08
FM175XX_FIFO_DATA_REG                   = 0x09
FM175XX_FIFO_LEVEL_REG                  = 0x0A
FM175XX_WATER_LEVEL_REG                 = 0x0B
FM175XX_CONTROL_REG                     = 0x0C
FM175XX_BIT_FRAMING_REG                 = 0x0D
FM175XX_COLL_REG                        = 0x0E
FM175XX_MODE_REG                        = 0x11
FM175XX_TX_MODE_REG                     = 0x12
FM175XX_RX_MODE_REG                     = 0x13
FM175XX_TX_CONTROL_REG                  = 0x14
FM175XX_TX_AUTO_REG                     = 0x15
FM175XX_TX_SEL_REG                      = 0x16
FM175XX_RX_SEL_REG                      = 0x17
FM175XX_RX_THRESHOLD_REG                = 0x18
FM175XX_DEMOD_REG                       = 0x19
FM175XX_MF_TX_REG                       = 0x1C
FM175XX_MF_RX_REG                       = 0x1D
FM175XX_TPYE_B_REG                      = 0x1E
FM175XX_SERIAL_SPEED_REG                = 0x1F
FM175XX_CRC_MSB_REG                     = 0x21
FM175XX_CRC_LSB_REG                     = 0x22
FM175XX_GSN_OFF_REG                     = 0x23
FM175XX_MODE_WIDTH_REG                  = 0x24
FM175XX_RF_CFG_REG                      = 0x26
FM175XX_GSN_ON_REG                      = 0x27
FM175XX_CW_GSP_REG                      = 0x28
FM175XX_MOD_GSP_REG                     = 0x29
FM175XX_T_MODE_REG                      = 0x2A
FM175XX_T_PRESCALER_REG                 = 0x2B
FM175XX_T_RELOAD_MSB_REG                = 0x2C
FM175XX_T_RELOAD_LSB_REG                = 0x2D
FM175XX_T_COUNTER_VAL_MSB_REG           = 0x2E
FM175XX_T_COUNTER_VAL_LSB_REG           = 0x2f
FM175XX_TEST_SEL_1_REG                  = 0x31
FM175XX_TEST_SEL_2_REG                  = 0x32
FM175XX_TEST_PIN_EN_REG                 = 0x33
FM175XX_TEST_PIN_VALUE_REG              = 0x34
FM175XX_TEST_BUS_REG                    = 0x35
FM175XX_TEST_CTRL_REG                   = 0x36
FM175XX_VERSION_REG                     = 0x37
FM175XX_TEST_DAC_1_REG                  = 0x39
FM175XX_TEST_DAC_2_REG                  = 0x3A
FM175XX_TEST_ADC_REG                    = 0x3B

# FM175xx command code
FM175XX_CMD_IDLE                        = 0x00
FM175XX_CMD_GEN_RANDOM_ID               = 0x02
FM175XX_CMD_CALC_CRC                    = 0x03
FM175XX_CMD_TRANSMIT                    = 0x04
FM175XX_CMD_NO_CMD_CHANGE               = 0x07
FM175XX_CMD_RECEIVE                     = 0x08
FM175XX_CMD_TRANSCEIVE                  = 0x0C
FM175XX_CMD_MF_AUTHENT                  = 0x0E
FM175XX_CMD_SOFT_RESET                  = 0x0F

# FM175XX RF command code
FM175XX_RF_CMD_REQA                     = 0x26
FM175XX_RF_CMD_WUPA                     = 0x52
FM175XX_RF_CMD_ANTICOL                  = [0x93, 0x95, 0x97]
FM175XX_RF_CMD_SELECT                   = [0x93, 0x95, 0x97]
FM175XX_RF_CMD_HALT                     = [0x50, 0x00]

# Chip Type
FM175XX_CHIP_TYPE_UNKNOWN               = 0x00
FM175XX_CHIP_TYPE_FM17580               = 0x01

# Chip version
FM175XX_CHIP_VER_FM17580                = 0xA1

# Carrier wave setting
FM175XX_CW_DISABLE                      = 0
FM175XX_CW1_ENABLE                      = 1
FM175XX_CW2_ENABLE                      = 2
FM175XX_CW_ENABLE                       = 3

FM175XX_CARD_INFO_READ                  = 0
FM175XX_CARD_INFO_CLEAR                 = 1

# RFID card type
FM175XX_MIFARE_CARD_TYPE_UNKNOWN        = 0xFF  # unknown type
FM175XX_MIFARE_CARD_TYPE_M1             = 0x08  # M1
FM175XX_MIFARE_CARD_TYPE_NTAG           = 0x00  # NTAG215/216 (NFC Forum Type 2)

# About M1 Card
# EEPROM
FM175XX_M1_CARD_EEPROM_SIZE             = 1024
FM175XX_M1_CARD_SECTORS                 = 16
FM175XX_M1_CARD_BLOCKS_PER_SEC          = 4
FM175XX_M1_CARD_BYTES_PER_BLK           = 16
FM175XX_M1_CARD_BYTES_PER_SEC           = 64
# Authentication mode
FM175XX_M1_CARD_AUTH_MODE_A             = 0
FM175XX_M1_CARD_AUTH_MODE_B             = 1
# Access Control Block
FM175XX_M1_CARD_ACCESS_CODE             = [0x87, 0x87, 0x87, 0x69]
FM175XX_M1_CARD_HKDF_SALT_KEY_A         = b"Snapmaker_qwertyuiop[,.;]"
FM175XX_M1_CARD_HKDF_SALT_KEY_B         = b"Snapmaker_qwertyuiop[,.;]_1q2w3e"

# Self test
FM175XX_SELF_TEST_STAGE_READY           = 0
FM175XX_SELF_TEST_STAGE_DOING           = 1
FM175XX_SELF_TEST_STAGE_STOP            = 2

FM175XX_MIN_TIME                        = 0.200

# Picc meta data
class Fm175xxPiccMetaData:
    def __init__(self) -> None:
        self.CASCADE_LEVEL = 0
        self.ATQA = [0] * 2
        self.UID = [0] * 12
        self.BCC = [0] * 3
        self.SAK = [0] * 3
    def reset(self):
        self.CASCADE_LEVEL = 0
        self.ATQA = [0] * 2
        self.UID = [0] * 12
        self.BCC = [0] * 3
        self.SAK = [0] * 3

# Reader command
class Fm175xxCmdMetaData:
    def __init__(self) -> None:
        self.cmd : int
        self.send_crc_en : int
        self.recv_crc_en : int
        self.bits_to_send : int
        self.bytes_to_send : int
        self.bits_to_recv : int
        self.bytes_to_recv : int
        self.bits_recved : int
        self.bytes_recved : int
        self.send_buff : list
        self.recv_buff : list
        self.coll_pos : int
        self.error : int
        self.timeout : int

# Return value
class Fm175xxReturnVal:
    def __init__(self) -> None:
        self.err_code = None
        self.out_param = None

# Fm175xx Reader
class FM175XXReader:
    def __init__(self, config) -> None:
        self.__printer = config.get_printer()
        self.__reactor = self.__printer.get_reactor()
        ppins = self.__printer.lookup_object('pins')

        # read config
        self.soc_spi_bus = config.getint('soc_spi_bus')
        self.soc_spi_dev_num = config.getint('soc_spi_dev_num')
        self.soc_spi_mode = config.getint('soc_spi_mode')
        self.soc_spi_speed_max = config.getint('soc_spi_speed_max')
        soc_rst_pin = config.get('soc_rst_pin')
        self.extra_spi_bus = config.getint('extra_spi_bus')
        self.extra_spi_dev_num = config.getint('extra_spi_dev_num')
        self.extra_spi_mode = config.getint('extra_spi_mode')
        self.extra_spi_speed_max = config.getint('extra_spi_speed_max')
        extra_rst_pin = config.get('extra_rst_pin')

        self.soc_ch_1 = config.getint('soc_ch_1')
        self.soc_ch_2 = config.getint('soc_ch_2')
        self.extra_ch_1 = config.getint('extra_ch_1')
        self.extra_ch_2 = config.getint('extra_ch_2')

        rf_1_pin = config.get('rf_1_pin')
        rf_2_pin = config.get('rf_2_pin')

        self._hkdf_key_a = None
        self._hkdf_key_b = None

        # SPI Commu
        self.__spi = spidev.SpiDev()

        # RST Pin
        self.__soc_rst_pin = ppins.setup_pin('digital_out', soc_rst_pin)
        self.__soc_rst_pin.setup_max_duration(0.)
        self.__extra_rst_pin = ppins.setup_pin('digital_out', extra_rst_pin)
        self.__extra_rst_pin.setup_max_duration(0.)

        self.__rst_pin = None
        self.__rst_ctrl_finish = False

        # rfid sw pin
        self.__rf_1_pin = ppins.setup_pin('digital_out', rf_1_pin)
        self.__rf_1_pin.setup_max_duration(0.)
        self.__rf_2_pin = ppins.setup_pin('digital_out', rf_2_pin)
        self.__rf_2_pin.setup_max_duration(0.)
        self.__select_channel_finish = False

        self.__card_info_read_flag = 0
        self.__card_info_clear_flag = 0
        self.__need_to_shutdown = False
        self.__card_info_deal_cb = None
        self.__picc_a = Fm175xxPiccMetaData()

        # self test
        self.__self_test_stage = FM175XX_SELF_TEST_STAGE_STOP
        self.__self_test_channel = 0
        self.__self_test_times = 100
        self.__self_test_success_cnt = 0

        self.__printer.register_event_handler("klippy:ready", self.__ready)
        self.__printer.register_event_handler("klippy:shutdown", self.__shutdown)

    def __ready(self):
        self.__select_fm175xx_obj(FM175XX_CHANNEL_1)
        self.__do_hard_reset()
        self.__select_fm175xx_obj(FM175XX_CHANNEL_3)
        self.__do_hard_reset()

        # Threading
        background_thread = threading.Thread(target=self.__bg_thread)
        background_thread.start()

    def __shutdown(self):
        self.__need_to_shutdown = True

    def __select_fm175xx_obj(self, channel):
        self.__spi.close()
        if (channel == FM175XX_CHANNEL_3 or channel == FM175XX_CHANNEL_4):
            self.__spi.open(self.soc_spi_bus, self.soc_spi_dev_num)
            self.__spi.mode = self.soc_spi_mode
            self.__spi.max_speed_hz = self.soc_spi_speed_max
            self.__rst_pin = self.__soc_rst_pin
        else:
            self.__spi.open(self.extra_spi_bus, self.extra_spi_dev_num)
            self.__spi.mode = self.extra_spi_mode
            self.__spi.max_speed_hz = self.extra_spi_speed_max
            self.__rst_pin = self.__extra_rst_pin

    # hardware reset
    def __do_hard_reset(self):
        delta_time = 0
        systime = self.__reactor.monotonic()
        systime += FM175XX_MIN_TIME + delta_time
        print_time = self.__rst_pin.get_mcu().estimated_print_time(systime)
        self.__rst_pin.set_digital(print_time, 0)
        delta_time += FM175XX_MIN_TIME

        systime = self.__reactor.monotonic()
        systime += FM175XX_MIN_TIME + delta_time
        print_time = self.__rst_pin.get_mcu().estimated_print_time(systime)
        self.__rst_pin.set_digital(print_time, 1)

        self.__rst_ctrl_finish = True

    def __hard_reset(self):
        self.__rst_ctrl_finish = False
        self.__reactor.register_async_callback(
            (lambda et, c=self.__do_hard_reset: c()))
        while 1:
            if self.__rst_ctrl_finish:
                break
            else:
                time.sleep(0.020)
        time.sleep(0.5)

    def __do_select_channel(self, channel):
        delta_time = 0
        if (channel == self.extra_ch_1 or channel == self.soc_ch_2):
            systime = self.__reactor.monotonic()
            systime += FM175XX_MIN_TIME + delta_time
            print_time = self.__rf_1_pin.get_mcu().estimated_print_time(systime)
            self.__rf_1_pin.set_digital(print_time, 1)
            delta_time += 0.100

            systime = self.__reactor.monotonic()
            systime += FM175XX_MIN_TIME + delta_time
            print_time = self.__rf_2_pin.get_mcu().estimated_print_time(systime)
            self.__rf_2_pin.set_digital(print_time, 0)

        else:
            systime = self.__reactor.monotonic()
            systime += FM175XX_MIN_TIME + delta_time
            print_time = self.__rf_1_pin.get_mcu().estimated_print_time(systime)
            self.__rf_1_pin.set_digital(print_time, 0)
            delta_time += 0.100

            systime = self.__reactor.monotonic()
            systime += FM175XX_MIN_TIME + delta_time
            print_time = self.__rf_2_pin.get_mcu().estimated_print_time(systime)
            self.__rf_2_pin.set_digital(print_time, 1)

        self.__select_channel_finish = True

    def __select_channel(self, channel):
        self.__select_channel_finish = False
        self.__reactor.register_async_callback(
            (lambda et, c=self.__do_select_channel, ch=channel: c(ch)))
        while 1:
            if self.__select_channel_finish:
                break
            else:
                time.sleep(0.020)

        time.sleep(0.35)

    # read register
    def __register_read(self, addr:int) -> int:
        addr = (addr << 1) | 0x80
        to_send = [addr, 0x00]
        reg_data = self.__spi.xfer(to_send)
        return reg_data[1]

    # write register
    def __register_write(self, addr:int, reg_data:int) -> None:
        addr = (addr << 1) & 0x7E
        to_send = [addr, reg_data]
        self.__spi.xfer(to_send)

    # modify register
    def __register_modify(self, addr:int, mask:int, is_set:int) -> None:
        reg_data = self.__register_read(addr)
        old_data = reg_data
        if (is_set):
            reg_data |= mask
        else:
            reg_data &= ~mask
        if old_data != reg_data:
            self.__register_write(addr, reg_data)

    # read FIFO
    def __fifo_read(self, len:int) -> list:
        addr = [0x92] * len + [0x00]
        buff = self.__spi.xfer(addr)
        return buff[1 : len + 1]

    # write FIFO
    def __fifo_write(self, len:int, buff:list) -> None:
        to_write = [0x12]
        to_write += buff[0:len]
        self.__spi.xfer(to_write)

    # Enable/Disable CRC check generation during data transmission.
    def __set_send_crc(self, mode:int) -> None:
        if (mode):
            self.__register_modify(FM175XX_TX_MODE_REG, 0x80, FM175XX_SET)
        else:
            self.__register_modify(FM175XX_TX_MODE_REG, 0x80, FM175XX_RESET)

    # Enable/Disable CRC check generation during data reception.
    def __set_recv_crc(self, mode:int) -> None:
        if (mode):
            self.__register_modify(FM175XX_RX_MODE_REG, 0x80, FM175XX_SET)
        else:
            self.__register_modify(FM175XX_RX_MODE_REG, 0x80, FM175XX_RESET)

    # Set the timeout period for communication
    def __set_timeout(self, microseconds:int) -> None:
        prescaler = 0
        time_reload = 0

        if microseconds < 1 :
            microseconds = 1

        while( prescaler < 0xFFF ):
            time_reload = int((( microseconds * 13560 ) -1 ) / ( prescaler * 2 + 1))
            if (time_reload < 0xFFFF):
                break
            prescaler += 1

        time_reload &=  0xFFFF
        self.__register_write(FM175XX_T_MODE_REG, 0x80 | ((prescaler >> 8) & 0x0F) )
        self.__register_write(FM175XX_T_PRESCALER_REG, prescaler & 0xFF)
        self.__register_write(FM175XX_T_RELOAD_MSB_REG, time_reload >> 8 )
        self.__register_write(FM175XX_T_RELOAD_LSB_REG, time_reload & 0xFF )

    # set carrier wave
    def __set_carrier_wave(self, mode:int) -> None:
        if (FM175XX_CW1_ENABLE == mode):
            self.__register_modify(FM175XX_TX_CONTROL_REG, 0x01, FM175XX_SET)
            self.__register_modify(FM175XX_TX_CONTROL_REG, 0x02, FM175XX_RESET)
        elif (FM175XX_CW2_ENABLE == mode):
            self.__register_modify(FM175XX_TX_CONTROL_REG, 0x01, FM175XX_RESET)
            self.__register_modify(FM175XX_TX_CONTROL_REG, 0x02, FM175XX_SET)
        elif (FM175XX_CW_ENABLE == mode):
            self.__register_modify(FM175XX_TX_CONTROL_REG, 0x03, FM175XX_SET)
        else: # FM175XX_CW_DISABLE == mode
            self.__register_modify(FM175XX_TX_CONTROL_REG, 0x03, FM175XX_RESET)

    # Execute Command
    def __command_exe(self, cmd:Fm175xxCmdMetaData) -> Fm175xxReturnVal:
        reg_data = 0
        irq = 0
        result = FM175XX_ERR
        send_length = cmd.bytes_to_send
        receive_length = 0
        send_finish = 0
        cmd.bits_recved = 0
        cmd.bytes_recved = 0
        cmd.coll_pos = 0
        cmd.error = 0
        fifo_water_level  = 32
        last_time = time.time()

        self.__register_write(FM175XX_COMMAND_REG, FM175XX_CMD_IDLE)
        self.__register_write(FM175XX_FIFO_LEVEL_REG, 0x80)
        self.__register_write(FM175XX_COM_IRQ_REG, 0x7F)
        self.__register_write(FM175XX_DIV_IRQ_REG, 0x7F)
        self.__register_write(FM175XX_COM_I_EN_REG, 0x80)
        self.__register_write(FM175XX_DIV_I_EN_REG, 0x00)
        self.__register_write(FM175XX_WATER_LEVEL_REG, fifo_water_level)

        self.__set_send_crc(cmd.send_crc_en)
        self.__set_recv_crc(cmd.recv_crc_en)
        self.__set_timeout(cmd.timeout)

        # authentication
        if (cmd.cmd == FM175XX_CMD_MF_AUTHENT) :
            self.__fifo_write(send_length, cmd.send_buff)
            send_length = 0
            self.__register_write(FM175XX_COMMAND_REG, cmd.cmd)
            self.__register_write(FM175XX_BIT_FRAMING_REG, 0x80 | cmd.bits_to_send)

        if (cmd.cmd == FM175XX_CMD_TRANSCEIVE):
            self.__register_write(FM175XX_COMMAND_REG, cmd.cmd)
            self.__register_write(FM175XX_BIT_FRAMING_REG, (cmd.bits_to_recv << 4) | cmd.bits_to_send)

        last_time = time.time() * 1000
        while 1:
            # timeout
            new_time = time.time() * 1000
            if (new_time - last_time > 50 + cmd.timeout):
                result = FM175XX_CARD_TIMER_ERR
                break
            irq = self.__register_read(FM175XX_COM_IRQ_REG)

            # timeout
            if (irq & 0x01):
                self.__register_write(FM175XX_COM_IRQ_REG, 0x01)
                result = FM175XX_CARD_TIMER_ERR
                break

            # errors occurred
            if (irq & 0x02):
                reg_data = self.__register_read(FM175XX_ERROR_REG)
                cmd.error = reg_data

                if (cmd.error & 0x08):
                    reg_data = self.__register_read(FM175XX_COLL_REG)
                    cmd.coll_pos = reg_data & 0x1F
                    result = FM175XX_CARD_COLL_ERR
                    break

                result = FM175XX_CARD_COMM_ERR
                self.__register_write(FM175XX_COM_IRQ_REG, 0x02)
                break

            # low level alert
            if (irq & 0x04):
                # send data
                if (send_length > 0):
                    if (send_length > fifo_water_level):
                        self.__fifo_write(fifo_water_level, cmd.send_buff)
                        del cmd.send_buff[0:fifo_water_level]
                        send_length = send_length - fifo_water_level
                    else:
                        self.__fifo_write(send_length, cmd.send_buff)
                        send_length = 0
                    self.__register_modify(FM175XX_BIT_FRAMING_REG, 0x80, FM175XX_SET)
                self.__register_write(FM175XX_COM_IRQ_REG, 0x04)

            # high level alert
            if (irq & 0x08):
                # Waiting for data transmission to complete
                if (send_finish == 1):
                    cmd.recv_buff[cmd.bytes_recved:cmd.bytes_recved + fifo_water_level] = self.__fifo_read(fifo_water_level)
                    cmd.bytes_recved += fifo_water_level
                self.__register_write(FM175XX_COM_IRQ_REG, 0x08)

            # idle status
            if ((irq & 0x10) and (cmd.cmd == FM175XX_CMD_MF_AUTHENT)):
                self.__register_write(FM175XX_COM_IRQ_REG, 0x10)
                result = FM175XX_OK
                break

            # receice data
            if ((irq & 0x20) and (cmd.cmd == FM175XX_CMD_TRANSCEIVE)):
                reg_data = self.__register_read(FM175XX_CONTROL_REG)
                cmd.bits_recved = reg_data & 0x07
                reg_data = self.__register_read(FM175XX_FIFO_LEVEL_REG)
                receive_length = reg_data & 0x7F
                cmd.recv_buff[cmd.bytes_recved:cmd.bytes_recved+receive_length] = self.__fifo_read(receive_length)
                cmd.bytes_recved += receive_length
                if ((cmd.bytes_to_recv != cmd.bytes_recved) and (cmd.bytes_to_recv != 0)):
                    result = FM175XX_CARD_LENGTH_ERR
                    break
                self.__register_write(FM175XX_COM_IRQ_REG, 0x20)
                result = FM175XX_OK
                break

            # Completed data transmission
            if (irq & 0x40):
                self.__register_write(FM175XX_COM_IRQ_REG, 0x40)
                if (cmd.cmd == FM175XX_CMD_TRANSCEIVE):
                    send_finish = 1

            time.sleep(0.005)

        self.__register_modify(FM175XX_BIT_FRAMING_REG, 0x80, FM175XX_RESET)
        self.__register_write(FM175XX_COMMAND_REG, FM175XX_CMD_IDLE)

        ret = Fm175xxReturnVal()
        ret.err_code = result
        ret.out_param = cmd
        return ret

    # Reader-A: init
    def __reader_a_init(self) -> None:
        self.__register_write(FM175XX_TX_MODE_REG, 0x00)
        self.__register_write(FM175XX_RX_MODE_REG, 0x08)
        self.__register_modify(FM175XX_TX_AUTO_REG, 0x40, FM175XX_SET)
        self.__register_write(FM175XX_MODE_WIDTH_REG, 0x26)
        self.__register_write(FM175XX_CONTROL_REG, 0x10)
        self.__register_write(FM175XX_GSN_ON_REG, 0xF0)
        self.__register_write(FM175XX_CW_GSP_REG, 0x3F)
        self.__register_write(FM175XX_RF_CFG_REG, 0x60)
        self.__register_write(FM175XX_RX_THRESHOLD_REG, 0x84)
        self.__register_modify(FM175XX_STATUS_2_REG, 0x08, FM175XX_RESET)

    # Reader-A: wake up picc(s)
    def __reader_a_wakeup(self) -> int:
        ret = FM175XX_ERR
        outbuf = [0]
        inbuf = [0] * 2
        cmd = Fm175xxCmdMetaData()

        cmd.send_crc_en = FM175XX_RESET
        cmd.recv_crc_en = FM175XX_RESET
        cmd.send_buff = outbuf
        cmd.recv_buff = inbuf
        cmd.send_buff[0] = FM175XX_RF_CMD_WUPA
        cmd.bytes_to_send = 1
        cmd.bits_to_send = 7
        cmd.bits_to_recv = 0
        cmd.bytes_to_recv = 2
        cmd.timeout = 10
        cmd.cmd = FM175XX_CMD_TRANSCEIVE
        result = self.__command_exe(cmd)
        ret = result.err_code

        if (result.err_code == FM175XX_OK):
            if (result.out_param.bytes_recved == 2):
                self.__picc_a.ATQA[0] = result.out_param.recv_buff[0]
                self.__picc_a.ATQA[1] = result.out_param.recv_buff[1]
            else:
                ret = FM175XX_CARD_COMM_ERR

        return ret

    # Reader-A: anti-collision
    def __reader_a_anticoll(self, cascade_level:int) -> int:
        ret = FM175XX_ERR
        outbuf = [0] * 2
        inbuf = [0] * 5
        cmd = Fm175xxCmdMetaData()

        if(cascade_level > 2):
            return FM175XX_PARAM_ERR

        cmd.send_crc_en = FM175XX_RESET
        cmd.recv_crc_en = FM175XX_RESET
        cmd.send_buff = outbuf
        cmd.recv_buff = inbuf
        cmd.send_buff[0] = FM175XX_RF_CMD_ANTICOL[cascade_level]
        cmd.send_buff[1] = 0x20
        cmd.bytes_to_send = 2
        cmd.bits_to_send = 0
        cmd.bits_to_recv = 0
        cmd.bytes_to_recv = 5
        cmd.timeout = 10
        cmd.cmd = FM175XX_CMD_TRANSCEIVE
        result = self.__command_exe(cmd)
        ret = result.err_code
        self.__register_modify(FM175XX_COLL_REG, 0x80, FM175XX_SET)

        if (result.err_code == FM175XX_OK):
            if (result.out_param.bytes_recved == 5):
                if((result.out_param.recv_buff[0] ^ \
                    result.out_param.recv_buff[1] ^ \
                    result.out_param.recv_buff[2] ^ \
                    result.out_param.recv_buff[3] ^ \
                    result.out_param.recv_buff[4]) != 0):
                    ret = FM175XX_CARD_COMM_ERR
                else:
                    self.__picc_a.UID[cascade_level * 4:cascade_level*4 + 4] = result.out_param.recv_buff[0:4]
                    self.__picc_a.BCC[cascade_level] = result.out_param.recv_buff[4]
            else:
                ret = FM175XX_CARD_COMM_ERR

        return ret

    # Reader-A: select a picc
    def __reader_a_select(self, cascade_level:int) -> int:
        ret = FM175XX_ERR
        outbuf = [0] * 7
        inbuf = [0]
        cmd = Fm175xxCmdMetaData()

        if(cascade_level > 2):
            return FM175XX_PARAM_ERR

        cmd.send_crc_en = FM175XX_SET
        cmd.recv_crc_en = FM175XX_SET
        cmd.send_buff = outbuf
        cmd.recv_buff = inbuf
        cmd.send_buff[0] = FM175XX_RF_CMD_SELECT[cascade_level]
        cmd.send_buff[1] = 0x70
        cmd.send_buff[2] = self.__picc_a.UID[4 * cascade_level + 0]
        cmd.send_buff[3] = self.__picc_a.UID[4 * cascade_level + 1]
        cmd.send_buff[4] = self.__picc_a.UID[4 * cascade_level + 2]
        cmd.send_buff[5] = self.__picc_a.UID[4 * cascade_level + 3]
        cmd.send_buff[6] = self.__picc_a.BCC[cascade_level]
        cmd.bytes_to_send = 7
        cmd.bits_to_send = 0
        cmd.bits_to_recv = 0
        cmd.bytes_to_recv = 1
        cmd.timeout = 10
        cmd.cmd = FM175XX_CMD_TRANSCEIVE
        result = self.__command_exe(cmd)
        ret = result.err_code

        if (result.err_code == FM175XX_OK):
            if (result.out_param.bytes_recved == 1):
                self.__picc_a.SAK[cascade_level] = result.out_param.recv_buff[0]
            else:
                ret = FM175XX_CARD_COMM_ERR

        return ret

    # Reader-A: halt
    def __reader_a_halt(self) -> int:
        outbuf = [0] * 2
        inbuf = [0] * 2
        cmd = Fm175xxCmdMetaData()

        cmd.send_crc_en = FM175XX_SET
        cmd.recv_crc_en = FM175XX_SET
        cmd.send_buff = outbuf
        cmd.recv_buff = inbuf
        cmd.send_buff[0] = FM175XX_RF_CMD_HALT[0]
        cmd.send_buff[1] = FM175XX_RF_CMD_HALT[1]
        cmd.bytes_to_send = 2
        cmd.bits_to_send = 0
        cmd.bits_to_recv = 0
        cmd.bytes_to_recv = 0
        cmd.timeout = 10
        cmd.cmd = FM175XX_CMD_TRANSCEIVE
        result = self.__command_exe(cmd)

        # If there is no response within 1ms, the 'halt' is successful
        if (result.err_code == FM175XX_CARD_TIMER_ERR):
            result.err_code = FM175XX_OK
        else:
            result.err_code = FM175XX_CARD_HALT_ERR

        return result.err_code

    # Reader-A: activate a picc
    def __reader_a_activate(self) -> int:
        ret = FM175XX_ERR
        cascade_level = 0

        ret = self.__reader_a_wakeup()
        if (FM175XX_OK != ret):
            logging.error("wakeup err: %d", ret)
            return FM175XX_CARD_WAKEUP_ERR

        if ((self.__picc_a.ATQA[0] & 0xC0) == 0x00):
            cascade_level = 1
        elif ((self.__picc_a.ATQA[0] & 0xC0) == 0x40):
            cascade_level = 2
        elif ((self.__picc_a.ATQA[0] & 0xC0) == 0x80):
            cascade_level = 3
        else:
            pass  # RFU

        for i in range(cascade_level):
            self.__picc_a.CASCADE_LEVEL = i
            ret = self.__reader_a_anticoll(self.__picc_a.CASCADE_LEVEL)
            if (FM175XX_OK != ret):
                logging.error("anticoll err: %d", ret)
                ret = FM175XX_CARD_COLL_ERR
                break
            ret = self.__reader_a_select(self.__picc_a.CASCADE_LEVEL)
            if (FM175XX_OK != ret):
                logging.error("select err: %d", ret)
                ret = FM175XX_CARD_SELECT_ERR
                break

        return ret

    # Reader-A: M1 authentication
    def __reader_a_mifare_auth(self, mode:int, sector:int, mifare_key:list, card_uid:list) -> int:
        ret = FM175XX_ERR
        reg_data = 0
        outbuf = [0] * 12
        inbuf = [0] * 1
        cmd = Fm175xxCmdMetaData()

        cmd.send_crc_en = FM175XX_SET
        cmd.recv_crc_en = FM175XX_SET
        cmd.send_buff = outbuf
        cmd.recv_buff = inbuf
        if (FM175XX_M1_CARD_AUTH_MODE_A == mode):
            cmd.send_buff[0] = 0x60
        else:
            cmd.send_buff[0] = 0x61
        cmd.send_buff[1] = sector * 4
        cmd.send_buff[2] = mifare_key[0]
        cmd.send_buff[3] = mifare_key[1]
        cmd.send_buff[4] = mifare_key[2]
        cmd.send_buff[5] = mifare_key[3]
        cmd.send_buff[6] = mifare_key[4]
        cmd.send_buff[7] = mifare_key[5]
        cmd.send_buff[8] = card_uid[0]
        cmd.send_buff[9] = card_uid[1]
        cmd.send_buff[10] = card_uid[2]
        cmd.send_buff[11] = card_uid[3]
        cmd.bytes_to_send = 12
        cmd.bits_to_send = 0
        cmd.bits_to_recv = 0
        cmd.bytes_to_recv = 0
        cmd.timeout = 10
        cmd.cmd = FM175XX_CMD_MF_AUTHENT
        result = self.__command_exe(cmd)
        ret = result.err_code
        if (FM175XX_OK == result.err_code):
            reg_data = self.__register_read(FM175XX_STATUS_2_REG)
            if (reg_data & 0x08):
                ret =  FM175XX_OK
            else:
                ret =  FM175XX_CARD_COMM_ERR

        return ret

    # Reader-A: M1, read a block
    def __reader_a_m1_block_read(self, block:int) -> Fm175xxReturnVal:
        outbuf = [0] * 2
        inbuf = [0] * 16
        cmd = Fm175xxCmdMetaData()
        ret = Fm175xxReturnVal()

        cmd.send_crc_en = FM175XX_SET
        cmd.recv_crc_en = FM175XX_SET
        cmd.send_buff = outbuf
        cmd.recv_buff = inbuf
        cmd.send_buff[0] = 0x30
        cmd.send_buff[1] = block
        cmd.bytes_to_send = 2
        cmd.bits_to_send = 0
        cmd.bits_to_recv = 0
        cmd.bytes_to_recv = 16
        cmd.timeout = 10
        cmd.cmd = FM175XX_CMD_TRANSCEIVE
        result = self.__command_exe(cmd)
        ret.err_code = result.err_code

        if (FM175XX_OK == result.err_code):
            if (result.out_param.bytes_recved == 16):
                ret.out_param = result.out_param.recv_buff[0:16]
            else:
                ret.err_code = FM175XX_CARD_COMM_ERR

        return ret

    # Reader-A: M1, write a block
    def __reader_a_m1_block_write(self, block:int, buff:list) -> int:
        ret = 0
        outbuf = [0] * 16
        inbuf = [0] * 1
        cmd = Fm175xxCmdMetaData()

        cmd.send_crc_en = FM175XX_SET
        cmd.recv_crc_en = FM175XX_RESET
        cmd.send_buff = outbuf
        cmd.recv_buff = inbuf
        cmd.send_buff = outbuf
        cmd.recv_buff = inbuf
        cmd.send_buff[0] = 0xA0
        cmd.send_buff[1] = block
        cmd.bytes_to_send = 2
        cmd.bits_to_send = 0
        cmd.bits_to_recv = 0
        cmd.bytes_to_recv = 1
        cmd.timeout = 10
        cmd.cmd = FM175XX_CMD_TRANSCEIVE
        result = self.__command_exe(cmd)
        ret = result.err_code

        if ((result.err_code != FM175XX_OK) or (result.out_param.bits_recved != 4) or (result.out_param.recv_buff[0] & 0x0F != 0x0A)):
            if (result.err_code == FM175XX_OK):
                ret = FM175XX_CARD_COMM_ERR
        else:
            self.__set_timeout(10)
            cmd.send_buff[0:16] = buff[0:16]
            cmd.bytes_to_send = 16
            cmd.bytes_to_recv = 1
            cmd.cmd = FM175XX_CMD_TRANSCEIVE
            result = self.__command_exe(cmd)
            ret = result.err_code

            if ((result.out_param.bits_recved != 4) or (result.out_param.recv_buff[0] & 0x0F != 0x0A)):
                ret = FM175XX_CARD_COMM_ERR

        return ret

    # Reader-A: M1, read all data
    def __reader_a_m1_read_all_data(self, uid:list, auth_mode:int, auth_key:list, retry_times = 3) -> Fm175xxReturnVal:
        ret = Fm175xxReturnVal()
        card_data_tmp = [0] * FM175XX_M1_CARD_EEPROM_SIZE
        area = 0

        # Traverse all sectors
        for sector_no in range(FM175XX_M1_CARD_SECTORS):
            # Authentication
            result = FM175XX_ERR
            for retry in range(retry_times):
                result = self.__reader_a_mifare_auth(auth_mode, sector_no, auth_key[sector_no], uid)
                if (result == FM175XX_OK):
                    break
            if (FM175XX_OK != result):
                ret.err_code = FM175XX_CARD_AUTH_ERR
                logging.error( "------ M1 AUTH ERROR------\r\n" )
                return ret

            # Traverse all blocks
            for block_no in range(FM175XX_M1_CARD_BLOCKS_PER_SEC - 1):
                result = Fm175xxReturnVal()
                for retry in range(retry_times):
                    result = self.__reader_a_m1_block_read(sector_no * FM175XX_M1_CARD_BLOCKS_PER_SEC + block_no)
                    if (result.err_code == FM175XX_OK):
                        break
                if (result.err_code != FM175XX_OK):
                    ret.err_code = FM175XX_CARD_READ_ERR
                    return ret

                area = FM175XX_M1_CARD_BYTES_PER_BLK * (sector_no * FM175XX_M1_CARD_BLOCKS_PER_SEC + block_no)
                card_data_tmp[area : area + FM175XX_M1_CARD_BYTES_PER_BLK] = result.out_param[0 : FM175XX_M1_CARD_BYTES_PER_BLK]

            area = sector_no * FM175XX_M1_CARD_BYTES_PER_SEC + 3 * FM175XX_M1_CARD_BYTES_PER_BLK
            card_data_tmp[area : area + FM175XX_M1_CARD_BYTES_PER_BLK] = \
                    self._hkdf_key_a[sector_no] + FM175XX_M1_CARD_ACCESS_CODE + self._hkdf_key_b[sector_no]

        ret.err_code = FM175XX_OK
        ret.out_param = card_data_tmp
        return ret

    # Reader-A: NTAG, read user memory (pages 4+)
    def __reader_a_ntag_read_user_data(self, max_pages=40) -> Fm175xxReturnVal:
        ret = Fm175xxReturnVal()
        user_data = []
        page = 4  # NTAG user memory starts at page 4

        while page < 4 + max_pages:
            outbuf = [0] * 2
            inbuf = [0] * 16
            cmd = Fm175xxCmdMetaData()

            cmd.send_crc_en = FM175XX_SET
            cmd.recv_crc_en = FM175XX_SET
            cmd.send_buff = outbuf
            cmd.recv_buff = inbuf
            cmd.send_buff[0] = 0x30  # READ command
            cmd.send_buff[1] = page
            cmd.bytes_to_send = 2
            cmd.bits_to_send = 0
            cmd.bits_to_recv = 0
            cmd.bytes_to_recv = 16  # 4 pages * 4 bytes
            cmd.timeout = 10
            cmd.cmd = FM175XX_CMD_TRANSCEIVE
            result = self.__command_exe(cmd)

            if result.err_code != FM175XX_OK:
                if len(user_data) > 0:
                    # Partial read is OK -- we may have hit end of memory
                    break
                ret.err_code = FM175XX_CARD_READ_ERR
                return ret

            user_data.extend(result.out_param.recv_buff[0:16])

            # Check for NDEF Terminator TLV (0xFE) in the data just read
            if 0xFE in result.out_param.recv_buff[0:16]:
                break

            page += 4  # Advance 4 pages (each READ returns 4 pages)

        if len(user_data) == 0:
            ret.err_code = FM175XX_CARD_READ_ERR
            return ret

        ret.err_code = FM175XX_OK
        ret.out_param = user_data
        return ret

    def __bg_thread(self):
        time.sleep(0.5)
        self.__select_fm175xx_obj(FM175XX_CHANNEL_1)
        time.sleep(0.05)
        ver = self.__register_read(FM175XX_VERSION_REG)
        logging.info("fm175xx[extra] version = 0x%X", ver)
        self.__select_fm175xx_obj(FM175XX_CHANNEL_3)
        time.sleep(0.05)
        ver = self.__register_read(FM175XX_VERSION_REG)
        logging.info("fm175xx[soc] version = 0x%X", ver)

        while 1:
            if self.__need_to_shutdown :
                self.__need_to_shutdown = False
                break

            retry_times_1 = 10
            retry_times_2 = 15
            retry_times_3 = 10
            if (self.__self_test_stage == FM175XX_SELF_TEST_STAGE_READY):
                self.__card_info_read_flag = (1 << self.__self_test_channel)
                self.__card_info_clear_flag = 0
                retry_times_1 = self.__self_test_times
                retry_times_2 = 1
                retry_times_3 = 1
                self.__self_test_stage = FM175XX_SELF_TEST_STAGE_DOING

            # Traverse all channels
            for ch in range(FM175XX_CHANNEL_NUMS):
                if (self.__card_info_read_flag & (1 << ch)) == 0:
                    if (self.__card_info_clear_flag & (1 << ch)) != 0:
                        if (self.__card_info_deal_cb != None):
                            self.__card_info_deal_cb(ch, FM175XX_CARD_INFO_CLEAR, FM175XX_OK, None, None)
                            self.__card_info_clear_flag &= ~(1 << ch) & 0xFFFFFFFF
                    continue

                card_op = FM175XX_CARD_INFO_READ
                card_op_result = FM175XX_ERR
                card_type = FM175XX_MIFARE_CARD_TYPE_UNKNOWN
                card_data = None

                self.__select_fm175xx_obj(ch)
                self.__select_channel(ch)

                logging.info("channel[%d]: start to read card info", ch)

                for retry_1 in range(retry_times_1):
                    # init reader-A
                    self.__picc_a.reset()
                    self.__reader_a_init()

                    # enable carrier wave
                    self.__set_carrier_wave(FM175XX_CW_ENABLE)

                    while 1:
                        # activate a card
                        ret = FM175XX_ERR

                        for retry_2 in range(retry_times_2):
                            ret = self.__reader_a_activate()
                            if (FM175XX_OK == ret):
                                break
                        if (FM175XX_OK != ret):
                            logging.error("Activate M1 card err, ret = %d", ret)
                            card_op_result = FM175XX_CARD_ACTIVATE_ERR
                            break

                        try:
                            ikm = copy.copy(self.__picc_a.UID[0:4])
                            ikm = bytearray(ikm)
                            self._hkdf_key_a = self._hkdf_create_key(ikm,
                                                    FM175XX_M1_CARD_HKDF_SALT_KEY_A,
                                                    'a')
                            self._hkdf_key_b = self._hkdf_create_key(ikm,
                                                    FM175XX_M1_CARD_HKDF_SALT_KEY_B,
                                                    'b')
                        except:
                            logging.error("nfc hkdf error!")
                            break

                        # read all info
                        # M1 card
                        if (FM175XX_MIFARE_CARD_TYPE_M1 == self.__picc_a.SAK[0]):
                            card_type = FM175XX_MIFARE_CARD_TYPE_M1
                            ret = self.__reader_a_m1_read_all_data(self.__picc_a.UID,
                                                                   FM175XX_M1_CARD_AUTH_MODE_A,
                                                                   self._hkdf_key_a,
                                                                   retry_times_3)
                            if (FM175XX_OK != ret.err_code):
                                card_op_result = FM175XX_CARD_READ_ERR
                            else:
                                card_data = ret.out_param[0:FM175XX_M1_CARD_EEPROM_SIZE]
                                card_op_result = FM175XX_OK

                                if (self.__self_test_stage != FM175XX_SELF_TEST_STAGE_DOING):
                                    self.__card_info_read_flag &= ~(1 << ch) & 0xFFFFFFFF
                                else:
                                    self.__self_test_success_cnt += 1
                                    if (self.__card_info_deal_cb != None):
                                        self.__card_info_deal_cb(ch, card_op, card_op_result, card_type, card_data)
                        # NTAG215/216 (NFC Forum Type 2 Tag)
                        elif (FM175XX_MIFARE_CARD_TYPE_NTAG == self.__picc_a.SAK[0]):
                            card_type = FM175XX_MIFARE_CARD_TYPE_NTAG
                            ret = self.__reader_a_ntag_read_user_data()
                            if (FM175XX_OK != ret.err_code):
                                card_op_result = FM175XX_CARD_READ_ERR
                            else:
                                card_data = ret.out_param
                                card_op_result = FM175XX_OK

                                if (self.__self_test_stage != FM175XX_SELF_TEST_STAGE_DOING):
                                    self.__card_info_read_flag &= ~(1 << ch) & 0xFFFFFFFF
                                else:
                                    self.__self_test_success_cnt += 1
                                    if (self.__card_info_deal_cb != None):
                                        self.__card_info_deal_cb(ch, card_op, card_op_result, card_type, card_data)
                        break

                    # halt a card
                    self.__reader_a_halt()

                    # disable carrier wave
                    self.__set_carrier_wave(FM175XX_CW_DISABLE)

                    if (self.__card_info_read_flag & (1 << ch)) == 0:
                        break
                    else:
                        time.sleep(0.02)

                if (self.__self_test_stage == FM175XX_SELF_TEST_STAGE_DOING):
                    self.__self_test_stage = FM175XX_SELF_TEST_STAGE_STOP
                else:
                    if (self.__card_info_deal_cb != None):
                        self.__card_info_deal_cb(ch, card_op, card_op_result, card_type, card_data)

                self.__card_info_read_flag &= ~(1 << ch) & 0xFFFFFFFF

            time.sleep(0.2)

    def _hkdf_create_key(self, ikm, salt, key_type='a'):
        sector_count = 16
        key_len = 6
        hash_algo = hashlib.sha256

        if not isinstance(ikm, bytes):
            ikm = bytes(ikm)
        if not isinstance(salt, bytes):
            salt = salt.encode() if isinstance(salt, str) else bytes(salt)
        if salt.endswith(b'\0'):
            salt = salt[:-1]

        keys = []
        prk = hmac.new(salt, ikm, hash_algo).digest()
        for i in range(sector_count):
            info = f"key_{key_type}_{i}".encode()
            okm = bytearray()
            counter = 1
            while len(okm) < key_len:
                data = hmac.new(prk, info + bytes([counter]), hash_algo).digest()
                okm.extend(data)
                counter += 1
            okm_list = [int(byte) for byte in okm[:key_len]]
            keys.append(okm_list)

        return keys

    # Register a callback function for protocol parsing
    def register_cb_2_card_info_deal(self, cb) -> None:
        try:
            if callable(cb):
                self.__card_info_deal_cb = cb
            else:
                raise TypeError()
        except Exception as e:
            logging.error("Param[cb] is not a callable function")

    def request_read_card_info(self, channel):
        self.__card_info_clear_flag &= ~(1 << channel) & 0xFFFFFFFF
        self.__card_info_read_flag |= (1 << channel)

    def request_clear_card_info(self, channel):
        self.__card_info_read_flag &= ~(1 << channel) & 0xFFFFFFFF
        self.__card_info_clear_flag |= (1 << channel)

    def self_test(self, channel, times):
        if (channel < 0 or channel > FM175XX_CHANNEL_NUMS):
            logging.error("invalid channel[%d]", channel)
            return

        if (self.__self_test_stage != FM175XX_SELF_TEST_STAGE_STOP):
            logging.info("self testing....")
            return

        if times < 1 :
            times = 1

        self.__self_test_channel = channel
        self.__self_test_times = times
        self.__self_test_success_cnt = 0
        self.__self_test_stage = FM175XX_SELF_TEST_STAGE_READY

    def self_test_result(self):
        finish_flag = False
        if (self.__self_test_stage == FM175XX_SELF_TEST_STAGE_STOP):
            finish_flag = True
        return finish_flag, self.__self_test_times, self.__self_test_success_cnt

def load_config(config):
      return FM175XXReader(config)

