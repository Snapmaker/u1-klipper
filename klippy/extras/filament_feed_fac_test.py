import logging
from . import pulse_counter

TEST_STATE_IDLE                                 = 'idle'
TEST_STATE_TESTING                              = 'testing'
TEST_STATE_FAILED                               = 'failed'
TEST_STATE_SUCCESSFUL                           = 'successful'

FEED_MOTOR_DIR_IDLE                             = 0
FEED_MOTOR_DIR_A                                = 1
FEED_MOTOR_DIR_B                                = 2

FEED_MOTOR_HARD_PROTECT_TIME                    = 2.5

FEED_MIN_TIME                                   = 0.100

class FeedTachometer:
    def __init__(self, printer, pin, ppr, sample_time, poll_time):
        self.frequence = pulse_counter.FrequencyCounter(printer, pin, sample_time, poll_time)
        self.ppr = ppr

    def get_rpm(self):
        rpm = self.frequence.get_frequency()  * 30. / self.ppr
        return rpm
    
    def get_counts(self):
        return self.frequence.get_count() / 2
    
class FeedPwmCfg:
    def __init__(self):
        self.a_pin = None
        self.b_pin = None
        self.cycle_time = 0.010
        self.max_value = 1.0

class FeedMotor:
    def __init__(self, printer, reactor, cfg:FeedPwmCfg):
        self.printer = printer
        self.reactor = reactor
        ppins = printer.lookup_object('pins')
        self.max_value = cfg.max_value
        self._motor_a = ppins.setup_pin('pwm', cfg.a_pin)
        self._motor_a.setup_max_duration(0.)
        self._motor_a.setup_cycle_time(cfg.cycle_time, False)
        self._motor_a.setup_start_value(0, 0)
        self._motor_b = ppins.setup_pin('pwm', cfg.b_pin)
        self._motor_b.setup_max_duration(0.)
        self._motor_b.setup_cycle_time(cfg.cycle_time, False)
        self._motor_b.setup_start_value(0, 0)
        self._mutex_lock = False
        self._dir = FEED_MOTOR_DIR_IDLE

    def get_mcu(self):
        return self._motor_a.get_mcu()
    
    def _run(self, dir, value):
        systime = self.reactor.monotonic()
        systime += FEED_MIN_TIME
        print_time = self._motor_a.get_mcu().estimated_print_time(systime)
        if FEED_MOTOR_DIR_A == dir:
            self._motor_b.set_pwm(print_time, 0)
            self._motor_a.set_pwm(print_time, value)
        elif FEED_MOTOR_DIR_B == dir:
            self._motor_a.set_pwm(print_time, 0)
            self._motor_b.set_pwm(print_time, value)
        else:
            self._motor_b.set_pwm(print_time, 0)
            self._motor_a.set_pwm(print_time, 0)

    def _run_one_cycle(self, dir, value):
        systime = self.reactor.monotonic()
        systime += FEED_MIN_TIME
        print_time = self._motor_a.get_mcu().estimated_print_time(systime)
        if FEED_MOTOR_DIR_A == dir:
            self._motor_b.set_pwm(print_time, 0)
            self._motor_a.set_pwm(print_time, value)
            self._motor_a.set_pwm(print_time + 0.01, 0)
        elif FEED_MOTOR_DIR_B == dir:
            self._motor_a.set_pwm(print_time, 0)
            self._motor_b.set_pwm(print_time, value)
            self._motor_b.set_pwm(print_time + 0.01, 0)
    
    def run(self, dir, value):
        while self._mutex_lock and not self.printer.is_shutdown():
            self.reactor.pause(self.reactor.monotonic() + 0.1)
        if self.printer.is_shutdown():
            return
        self._mutex_lock = True
        try:
            val = max(0, min(self.max_value, value))
            if val == 0:
                dir = FEED_MOTOR_DIR_IDLE

            while 1:
                if FEED_MOTOR_DIR_IDLE == self._dir:
                    if FEED_MOTOR_DIR_IDLE == dir:
                        break
                    self._dir = dir
                    self._run(dir, val)
                    self.reactor.pause(self.reactor.monotonic() + 2 * FEED_MIN_TIME)
                else:
                    if dir == self._dir:
                        self._run(dir, val)
                        self.reactor.pause(self.reactor.monotonic() + 2 * FEED_MIN_TIME)
                    else:
                        self._run(FEED_MOTOR_DIR_IDLE, 0)
                        self.reactor.pause(self.reactor.monotonic() + FEED_MOTOR_HARD_PROTECT_TIME)
                        self._dir = FEED_MOTOR_DIR_IDLE
                        if FEED_MOTOR_DIR_IDLE != dir:
                            self._dir = dir
                            self._run(dir, val)
                            self.reactor.pause(self.reactor.monotonic() + 2 * FEED_MIN_TIME)
                break
        finally:
            self._mutex_lock = False

    def run_one_cycle(self, dir, value):
        while self._mutex_lock and not self.printer.is_shutdown():
            self.reactor.pause(self.reactor.monotonic() + 0.1)
        if self.printer.is_shutdown():
            return
        self._mutex_lock = True
        try:
            val = max(0, min(self.max_value, value))
            if val == 0:
                dir = FEED_MOTOR_DIR_IDLE

            while 1:
                if FEED_MOTOR_DIR_IDLE == self._dir:
                    if FEED_MOTOR_DIR_IDLE == dir:
                        break
                    self._dir = dir
                    self._run_one_cycle(dir, val)
                    self.reactor.pause(self.reactor.monotonic() + 2 * FEED_MIN_TIME)
                    self._dir = FEED_MOTOR_DIR_IDLE
                else:
                    self._run(FEED_MOTOR_DIR_IDLE, 0)
                    self.reactor.pause(self.reactor.monotonic() + FEED_MOTOR_HARD_PROTECT_TIME)
                    self._dir = FEED_MOTOR_DIR_IDLE
                    if FEED_MOTOR_DIR_IDLE != dir:
                        self._dir = dir
                        self._run_one_cycle(dir, val)
                        self.reactor.pause(self.reactor.monotonic() + 2 * FEED_MIN_TIME)
                        self._dir = FEED_MOTOR_DIR_IDLE
                break
        finally:
            self._mutex_lock = False


class FeedFacTest:
    def __init__(self, config) -> None:
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        gcode = self.printer.lookup_object('gcode')
        self.module_name = config.get_name().split()[1]
        ppins = self.printer.lookup_object('pins')
        printer_buttons = self.printer.lookup_object('buttons')

        self._test_state = TEST_STATE_IDLE

        # Please confirm the order of input and output pins
        # output pin
        self._output_pin_list = []
        self._output_pin_state = 0
        tmp_pin = config.get('light_ch_1_white')
        tmp_obj = ppins.setup_pin('digital_out', tmp_pin)
        tmp_obj.setup_max_duration(0.)
        self._output_pin_list.append(tmp_obj)
        tmp_pin = config.get('light_ch_2_white')
        tmp_obj = ppins.setup_pin('digital_out', tmp_pin)
        tmp_obj.setup_max_duration(0.)
        self._output_pin_list.append(tmp_obj)
        tmp_pin = config.get('wheel_tach_ch_1_1_pin')
        tmp_obj = ppins.setup_pin('digital_out', tmp_pin)
        tmp_obj.setup_max_duration(0.)
        self._output_pin_list.append(tmp_obj)
        tmp_pin = config.get('wheel_tach_ch_2_1_pin')
        tmp_obj = ppins.setup_pin('digital_out', tmp_pin)
        tmp_obj.setup_max_duration(0.)
        self._output_pin_list.append(tmp_obj)
        tmp_pin = config.get('port_ch_1_pin')
        tmp_obj = ppins.setup_pin('digital_out', tmp_pin)
        tmp_obj.setup_max_duration(0.)
        self._output_pin_list.append(tmp_obj)

        # input pin
        self._input_pin_state = 0
        self._button_list = []
        tmp_pin = config.get('light_ch_1_red')
        self._button_list.append(tmp_pin)
        tmp_pin = config.get('light_ch_2_red')
        self._button_list.append(tmp_pin)
        tmp_pin = config.get('wheel_tach_ch_1_2_pin')
        self._button_list.append(tmp_pin)
        tmp_pin = config.get('wheel_tach_ch_2_2_pin')
        self._button_list.append(tmp_pin)
        tmp_pin = config.get('port_ch_2_pin')
        self._button_list.append(tmp_pin)
        printer_buttons.register_buttons(self._button_list, self._button_handler)

        # motor
        self._rpm = 0
        motor_cfg = FeedPwmCfg()
        motor_cfg.a_pin = config.get('motor_ch_1_pin')
        motor_cfg.b_pin = config.get('motor_ch_2_pin')
        motor_cfg.cycle_time = config.getfloat('motor_cycle_time')
        motor_cfg.max_value = config.getfloat('motor_max_value', maxval=1.0)
        self.motor = FeedMotor(self.printer, self.reactor, motor_cfg)
        # motor tachometer
        tmp_pin = config.get('motor_tach_pin')
        motor_tach_ppr = config.getint('motor_tach_ppr', 2, minval=1)
        poll_time = config.getfloat('motor_tach_poll_interval', 0.0005, above=0.)
        self.motor_tachometer = FeedTachometer(
                                self.printer, 
                                tmp_pin, 
                                motor_tach_ppr,
                                0.200, 
                                poll_time)
        self._motor_dest_rpm_min = config.getint('motor_dest_rpm_min')
        self._motor_dest_rpm_max = config.getint('motor_dest_rpm_max')
        
        gcode.register_mux_command("FEED_FACTORY_TEST", "MODULE",
                                self.module_name,
                                self.cmd_FEED_FACTORY_TEST)
    
    def _button_handler(self, eventtime, state):
        self._input_pin_state = state

    def get_status(self, eventtime=None):
        return {
            'state': self._test_state,
            'output_state': self._output_pin_state,
            'input_state': self._input_pin_state,
            'rpm': self._rpm}

    def cmd_FEED_FACTORY_TEST(self, gcmd):
        rpm_idle = 0
        rpm_dir_a = 0
        rpm_dir_b = 0

        try:
            self._test_state = TEST_STATE_TESTING

            self._output_pin_state = 0
            for i in range (len(self._output_pin_list)):
                systime = self.reactor.monotonic()
                systime += FEED_MIN_TIME
                print_time = self._output_pin_list[i].get_mcu().estimated_print_time(systime)
                if i % 2 == 0:
                    self._output_pin_list[i].set_digital(print_time, 1)
                    self._output_pin_state |= 1 << i
                else:
                    self._output_pin_list[i].set_digital(print_time, 0)

            self.reactor.pause(self.reactor.monotonic() + 2 * FEED_MIN_TIME)
            
            if self._output_pin_state != self._input_pin_state:
                raise Exception("Output and input pin state mismatch")

            self._output_pin_state = 0
            for i in range (len(self._output_pin_list)):
                systime = self.reactor.monotonic()
                systime += FEED_MIN_TIME
                print_time = self._output_pin_list[i].get_mcu().estimated_print_time(systime)
                if i % 2 == 0:
                    self._output_pin_list[i].set_digital(print_time, 0)
                else:
                    self._output_pin_list[i].set_digital(print_time, 1)
                    self._output_pin_state |= 1 << i

            self.reactor.pause(self.reactor.monotonic() + 2 * FEED_MIN_TIME)
            
            if self._output_pin_state != self._input_pin_state:
                raise Exception("Output and input pin state mismatch")

            self.motor.run(FEED_MOTOR_DIR_A, 0.5)
            self.reactor.pause(self.reactor.monotonic() + 0.5)
            rpm_dir_a = self.motor_tachometer.get_rpm()
            if self.motor_tachometer.get_rpm() < self._motor_dest_rpm_min or \
                    self.motor_tachometer.get_rpm() > self._motor_dest_rpm_max:
                raise

            self.motor.run(FEED_MOTOR_DIR_B, 0.5)
            self.reactor.pause(self.reactor.monotonic() + 0.5)
            self._rpm = rpm_dir_b = self.motor_tachometer.get_rpm()
            if self.motor_tachometer.get_rpm() < self._motor_dest_rpm_min or \
                    self.motor_tachometer.get_rpm() > self._motor_dest_rpm_max:
                raise

            self.motor.run(FEED_MOTOR_DIR_IDLE, 0)
            rpm_idle = self.motor_tachometer.get_rpm()
            if self.motor_tachometer.get_rpm() > 0:
                raise

            self._test_state = TEST_STATE_SUCCESSFUL

        except Exception as e:
            self._test_state = TEST_STATE_FAILED
            self.motor.run(FEED_MOTOR_DIR_IDLE, 0)

        msg = ("filament_feed_fac_test: state = %s, output_state = 0x%X, input_state = 0x%X\r\n" 
               "rpm_idle = %d, rpm_dir_a = %d, rpm_dir_b = %d\r\n" % (
            self._test_state, self._output_pin_state, self._input_pin_state,
            rpm_idle, rpm_dir_a, rpm_dir_b))
        gcmd.respond_info(msg, log=False)

def load_config_prefix(config):
    return FeedFacTest(config)

