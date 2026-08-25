import logging
from . import bus, adxl345, bulk_sensor

#SC7A20 registers
REG_SC7A20_SPI_CTRL_ADDR        = 0x0E
REG_SC7A20_WHO_AM_I_ADDR        = 0x0F
REG_SC7A20_MODE_CTRL_ADDR       = 0x1F
REG_SC7A20_CTRL_REG1_ADDR       = 0x20
REG_SC7A20_CTRL_REG2_ADDR       = 0x21
REG_SC7A20_CTRL_REG3_ADDR       = 0x22
REG_SC7A20_CTRL_REG4_ADDR       = 0x23
REG_SC7A20_CTRL_REG5_ADDR       = 0x24
REG_SC7A20_CTRL_REG6_ADDR       = 0x25
REG_SC7A20_STATUS_REG_ADDR      = 0x27
REG_SC7A20_OUT_X_L_ADDR         = 0x28
REG_SC7A20_OUT_X_H_ADDR         = 0x29
REG_SC7A20_OUT_Y_L_ADDR         = 0x2A
REG_SC7A20_OUT_Y_H_ADDR         = 0x2B
REG_SC7A20_OUT_Z_L_ADDR         = 0x2C
REG_SC7A20_OUT_Z_H_ADDR         = 0x2D
REG_SC7A20_FIFO_CTRL_ADDR       = 0x2E
REG_SC7A20_FIFO_SRC_ADDR        = 0x2F
REG_SC7A20_SOFT_RESET_ADDR      = 0x68
REG_SC7A20_VERSION_ADDR         = 0x70


REG_ADDR_AUTO_INC       = 0x40
REG_MOD_READ            = 0x80

SC7A20_DEV_ID           = 0x11

FREEFALL_ACCEL          = 9.80665
SCALE                   = FREEFALL_ACCEL * 7.8125 / 16
BATCH_UPDATES           = 0.100

class SC7A20:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.name = config.get_name().split()[-1]
        adxl345.AccelCommandHelper(config, self)
        self.axes_map = adxl345.read_axes_map(config, SCALE, SCALE, SCALE)
        self.data_rate = 2660
        spi_reuse = config.get('spi_reuse', None)
        self.spi = None
        if spi_reuse is not None:
            spi_reuse_obj = self.printer.lookup_object(spi_reuse)
            self.spi = spi_reuse_obj.spi
        else:
            self.spi = bus.MCU_SPI_from_config(config, 3, default_speed=5000000)
        self.mcu = mcu = self.spi.get_mcu()
        self.oid = oid = mcu.create_oid()
        self.query_sc7a20_cmd = None
        mcu.add_config_cmd("config_sc7a20 oid=%d spi_oid=%d"
                           % (oid, self.spi.get_oid()))
        mcu.add_config_cmd("query_sc7a20 oid=%d rest_ticks=0"
                           % (oid,), on_restart=True)
        mcu.register_config_callback(self._build_config)

        # Bulk sample message reading
        chip_smooth = self.data_rate * BATCH_UPDATES * 2
        self.ffreader = bulk_sensor.FixedFreqReader(mcu, chip_smooth, "<hhh")
        self.last_error_count = 0
        # Process messages in batches
        self.batch_bulk = bulk_sensor.BatchBulkHelper(
            self.printer, self._process_batch,
            self._start_measurements, self._finish_measurements, BATCH_UPDATES)
        self.name = config.get_name().split()[-1]
        hdr = ('time', 'x_acceleration', 'y_acceleration', 'z_acceleration')
        self.batch_bulk.add_mux_endpoint("sc7a20/dump_sc7a20", "sensor",
                                         self.name, {'header': hdr})

    def _build_config(self):
        cmdqueue = self.spi.get_command_queue()
        self.query_sc7a20_cmd = self.mcu.lookup_command(
            "query_sc7a20 oid=%c rest_ticks=%u", cq=cmdqueue)
        self.ffreader.setup_query_command("query_sc7a20_status oid=%c",
                                          oid=self.oid, cq=cmdqueue)


    def soft_reset(self):
        self.set_reg(REG_SC7A20_SPI_CTRL_ADDR, 0x10)
        self.spi.spi_send([REG_SC7A20_SOFT_RESET_ADDR, 0xA5])

    def read_reg(self, reg):
        params = self.spi.spi_transfer([reg | REG_MOD_READ, 0x00])
        response = bytearray(params['response'])
        return response[1]

    def set_reg(self, reg, val, minclock=0):
        self.spi.spi_send([reg, val & 0xFF], minclock=minclock)
        stored_val = self.read_reg(reg)
        if stored_val != val:
            msg = ("Failed to set SC7A20 register [0x%x] to 0x%x: got 0x%x. "
                  "This is generally indicative of connection problems "
                  "(e.g. faulty wiring) or a faulty SC7A20 chip." % (
                      reg, val, stored_val))
            err_msg = '{"coded": "0003-0522-0000-0009", "oneshot": 1, "msg":"%s"}' % msg
            raise self.printer.command_error(err_msg)

    def check_devid(self):
        return self.read_reg(REG_SC7A20_WHO_AM_I_ADDR) == SC7A20_DEV_ID

    def start_internal_client(self):
        aqh = adxl345.AccelQueryHelper(self.printer)
        self.batch_bulk.add_client(aqh.handle_batch)
        return aqh

    # Measurement decoding
    def _convert_samples(self, samples):
        (x_pos, x_scale), (y_pos, y_scale), (z_pos, z_scale) = self.axes_map
        count = 0
        for ptime, rx, ry, rz in samples:
            raw_xyz = (rx, ry, rz)
            x = round(raw_xyz[x_pos] * x_scale, 6)
            y = round(raw_xyz[y_pos] * y_scale, 6)
            z = round(raw_xyz[z_pos] * z_scale, 6)
            samples[count] = (round(ptime, 6), x, y, z)
            count += 1

    def _start_measurements(self):
        # In case of miswiring, testing SC7A20 device ID prevents treating
        # noise or wrong signal as a correctly initialized device
        dev_id = self.read_reg(REG_SC7A20_WHO_AM_I_ADDR)
        logging.info("sc7a20_dev_id: %x", dev_id)
        if dev_id != SC7A20_DEV_ID:
            msg = ("Invalid sc7a20 id (got %x vs %x). "
                  "Possible causes: connection problems (faulty wiring) "
                  "or a faulty sc7a20 chip."
                  % (dev_id, SC7A20_DEV_ID))
            err_msg = '{"coded": "0003-0522-0000-0010", "oneshot": 1, "msg":"%s"}' % msg
            raise self.printer.command_error(err_msg)
        # Setup chip in requested query rate
        # soft reset
        self.soft_reset()
        self.reactor.pause(self.reactor.monotonic() + 0.010)
        self.set_reg(REG_SC7A20_SPI_CTRL_ADDR, 0x00)
        self.reactor.pause(self.reactor.monotonic() + 0.1)

        # High-Performance Mode -- 2.660 KHz
        # Disable low-power mode
        self.set_reg(REG_SC7A20_CTRL_REG1_ADDR, 0xA7)
        # control mode
        # OSR = ODR
        # higher performance
        self.set_reg(REG_SC7A20_MODE_CTRL_ADDR, 0x03)
        # # HPCF: 11
        # self.set_reg(REG_SC7A20_CTRL_REG2_ADDR, 0x28)

        # +-16g
        # DLPF: 10
        self.set_reg(REG_SC7A20_CTRL_REG4_ADDR, 0xB0)

        self.reactor.pause(self.reactor.monotonic() + 0.1)

        # self.ffreader.note_start()
        # self.last_error_count = 0

        # Start bulk reading
        rest_ticks = self.mcu.seconds_to_clock(0.5 / self.data_rate)
        # rest_ticks = self.mcu.seconds_to_clock(65.0/1000000)
        self.query_sc7a20_cmd.send([self.oid, rest_ticks])
        # self.set_reg(REG_SC7A20_FIFO_CTRL_ADDR, 0x80)
        logging.info("SC7A20 starting '%s' measurements", self.name)
        # Initialize clock tracking

        self.ffreader.note_start()
        self.last_error_count = 0

    def _finish_measurements(self):
        # Halt bulk reading
        self.ffreader.note_end()
        # self.set_reg(REG_SC7A20_FIFO_CTRL_ADDR, 0x00)
        self.query_sc7a20_cmd.send_wait_ack([self.oid, 0])
        logging.info("SC7A20 finished '%s' measurements", self.name)
        # self.set_reg(REG_SC7A20_FIFO_CTRL_ADDR, 0x00)

    def _process_batch(self, eventtime):
        samples = self.ffreader.pull_samples()
        self._convert_samples(samples)
        if not samples:
            return {}
        return {'data': samples, 'errors': self.last_error_count,
                'overflows': self.ffreader.get_last_overflows()}

def load_config_prefix(config):
    return SC7A20(config)

