#include <string.h> // ffs
#include "board/irq.h" // irq_save
#include "board/misc.h"
#include "board/armcm_boot.h" // armcm_enable_irq
#include "command.h" // DECL_ENUMERATION_RANGE
#include "basecmd.h" // oid_alloc
#include "sched.h" // sched_shutdown
#include "autoconf.h" // CONFIG_CLOCK_FREQ
#include "inductance_coil.h"
#include "../sensor_bulk.h"

#define BYTES_PER_SAMPLE (4)
#define MAX_BUFFER_SIZE 50

typedef enum {
  OPEN = 0,
  TRIGGERED = 1,
} VIRTUAL_GPIO_STATE;

typedef enum {
  FIXED_TIME_CAL_MODE = 0,
  FIXED_PULSE_NUM_CAL_MODE = 1,
} FREQ_CAL_MODE;

typedef struct {
  uint32_t buffer[MAX_BUFFER_SIZE];
  uint32_t bufferSize;
  uint32_t head;
  uint32_t count;
  uint64_t sum;
} MOVING_SUM;

struct freq_cal_info {
  uint8_t trigger_mode;     // 0: Unidirectional Trigger  1:  Bidirectional Trigger
  uint8_t trigger_invert;
  uint32_t need_capture_pulse_sum;
  uint32_t cal_capture_pulse_window_size;
  uint32_t trg_freq_ht;
  uint32_t trg_freq_lt;
  volatile uint32_t cmp_trg_cnt_ht;
  volatile uint32_t cmp_trg_cnt_lt;
  volatile uint64_t capture_pulse_sum;
  volatile uint32_t update_cnt;
  double freq_cal_cycle;
  double freq_cal_timeout_cycle;
  double freq_cal_factor;
  volatile VIRTUAL_GPIO_STATE virtual_gpio_state;
  FREQ_CAL_MODE freq_cal_mode;
  MOVING_SUM moving_sum;
};

struct timer_config_freq_param {
  uint8_t oid;
  uint8_t absolute_mode;
  uint8_t trigger_mode;
  uint8_t trigger_invert;
  uint8_t force_update;
  int32_t trg_freq_ht;
  int32_t trg_freq_lt;
};

struct inductance_coil_dev {
  struct timer timer;
  struct timer config_freq_timer;
  uint16_t dev_flags;
  uint32_t rest_tick;
  struct freq_cal_info cal_info;
  struct sensor_bulk sb;
  struct timer_config_freq_param config_freq_param;
};

static uint8_t inductance_coil_oid_malloc = 0;
static VIRTUAL_GPIO_STATE tmp_gpio_state = TRIGGERED;
static struct task_wake inductance_coil_wake;
struct freq_cal_info g_freq_cal_info = {
                                          .trigger_mode = 0,
                                          .trigger_invert = 0,
                                          .trg_freq_ht = 0,
                                          .trg_freq_lt = 0,
                                          .cmp_trg_cnt_ht = 0,
                                          .cmp_trg_cnt_lt = 0,
                                          .capture_pulse_sum = 0,
                                          .freq_cal_factor = 1,
                                          .freq_cal_cycle = 0.001,
                                          .freq_cal_timeout_cycle = 1,
                                          .freq_cal_mode = FIXED_TIME_CAL_MODE,
                                          .need_capture_pulse_sum = 1000,
                                          .virtual_gpio_state = TRIGGERED,
                                          .update_cnt = 0,
                                          .cal_capture_pulse_window_size = 1,
                                        };

// For faster performance no legality checking is done, the call needs to ensure that the parameters are legal
void init_moving_sum(MOVING_SUM *ms, uint32_t bufferSize) {
  if (bufferSize == 0 || bufferSize > MAX_BUFFER_SIZE) {
    shutdown("Invalid buff size!!!");
  }
  ms->bufferSize = bufferSize;
  ms->head = 0;
  ms->count = 0;
  ms->sum = 0;
}

void add_value(MOVING_SUM *ms, uint32_t value) {
  if (ms->count >= ms->bufferSize) {
    ms->sum -= ms->buffer[ms->head];
  } else {
    ++ms->count;
  }

  ms->sum += value;
  ms->buffer[ms->head] = value;

  if (++ms->head >= ms->bufferSize) {
    ms->head = 0;
  }
}

void reset_buffer(MOVING_SUM *ms) {
  for (uint32_t i = 0; i < ms->bufferSize; ++i) {
    ms->buffer[i] = 0;
  }
  ms->head = 0;
  ms->count = 0;
  ms->sum = 0;
}

uint64_t get_sum(MOVING_SUM *ms) {
  if (ms->bufferSize == 0 || ms->count < ms->bufferSize)
    return 0;
  return ms->sum;
}

#if CONFIG_MACH_AT32F4x
// currently it only works with the AT32F415 chip from artery.
  #if CONFIG_MACH_AT32F415
    #include "at32f415_crm.h"
    #include "at32f415_tmr.h"
  #elif CONFIG_MACH_AT32F403A
    #include "at32f403a_407_crm.h"
    #include "at32f403a_407_tmr.h"
  #endif

// use channel 1 of timer2, expand for more channels and timers in the future
// DECL_CONSTANT_STR("RESERVE_PINS_input_capture", "PA0");
#define INPUT_CAPTURE_CRM_TIM                     TMR2
#define INPUT_CAPTURE_CRM_TIM_MAX_PR_VALUE        0xFFFFFFFF
#define INPUT_CAPTURE_CRM_CLK                     CRM_TMR2_PERIPH_CLOCK

#define INPUT_CAPTURE_GPIO_CRM_CLK                CRM_GPIOA_PERIPH_CLOCK
#define INPUT_CAPTURE_PIN                         GPIO_PINS_0
#define INPUT_CAPTURE_GPIO                        GPIOA
#define INVALID_FREQ_VALUE                        0xFFFFFFFF
#define DAFAULT_CAL_CYCLE_TIME                    (0.001)     // calculate the capture frequency once in 1ms
#define DAFAULT_TIM_PR_VALUE                      (CONFIG_CLOCK_FREQ * DAFAULT_CAL_CYCLE_TIME)

#define INPUT_CAPTURE_CAL_CRM_TIM                 TMR5
#define INPUT_CAPTURE_CAL_CRM_TIM_CLOCK_FREQ      CONFIG_CLOCK_FREQ
#define INPUT_CAPTURE_CAL_CRM_CLK                 CRM_TMR5_PERIPH_CLOCK
#define INPUT_CAPTURE_CAL_CRM_DIV                 (1)
#define INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE    0xFFFFFFFF
#define INPUT_CAPTURE_CAL_CRM_TIM_PR(CYCLE)       ((double)CONFIG_CLOCK_FREQ / INPUT_CAPTURE_CAL_CRM_DIV * CYCLE - 1)
#define INPUT_CAPTURE_OVER_CNT                    (1000)
#define INPUT_CAPTURE_CAL_IRQn                    (TMR5_GLOBAL_IRQn)
#define INPUT_CAPTURE_CAL_COMPENSATION_TICK       (0)

void
InputCapture_IRQHandler(void)
{
  if (INPUT_CAPTURE_CAL_CRM_TIM->ists & TMR_OVF_FLAG)
  {
    INPUT_CAPTURE_CAL_CRM_TIM->ists = ~TMR_OVF_FLAG;
    // if (g_freq_cal_info.freq_cal_mode == FIXED_PULSE_NUM_CAL_MODE)
    //   g_freq_cal_info.capture_pulse_sum = 0;
    // else
    //   g_freq_cal_info.capture_pulse_sum = INPUT_CAPTURE_CRM_TIM->cval;
    if (g_freq_cal_info.freq_cal_mode == FIXED_PULSE_NUM_CAL_MODE) {
      reset_buffer(&g_freq_cal_info.moving_sum);
    }
    else {
      add_value(&g_freq_cal_info.moving_sum, INPUT_CAPTURE_CRM_TIM->cval);
    }
    INPUT_CAPTURE_CRM_TIM->cval =  0;
  }

  if (INPUT_CAPTURE_CAL_CRM_TIM->ists & TMR_C1_FLAG) {
    INPUT_CAPTURE_CAL_CRM_TIM->ists = ~TMR_C1_FLAG;
    if (g_freq_cal_info.freq_cal_mode == FIXED_PULSE_NUM_CAL_MODE)
      add_value(&g_freq_cal_info.moving_sum, INPUT_CAPTURE_CAL_CRM_TIM->c1dt);
    // if (g_freq_cal_info.freq_cal_mode == FIXED_PULSE_NUM_CAL_MODE)
    //   g_freq_cal_info.capture_pulse_sum = INPUT_CAPTURE_CAL_CRM_TIM->c1dt;
  }

  g_freq_cal_info.capture_pulse_sum = get_sum(&g_freq_cal_info.moving_sum);

  if (g_freq_cal_info.capture_pulse_sum != 0) {
    if (g_freq_cal_info.freq_cal_mode == FIXED_PULSE_NUM_CAL_MODE) {
      if (g_freq_cal_info.trigger_mode) {
        if (g_freq_cal_info.capture_pulse_sum + INPUT_CAPTURE_CAL_COMPENSATION_TICK <= g_freq_cal_info.cmp_trg_cnt_ht || \
            g_freq_cal_info.capture_pulse_sum + INPUT_CAPTURE_CAL_COMPENSATION_TICK >= g_freq_cal_info.cmp_trg_cnt_lt)
          tmp_gpio_state = TRIGGERED;
        else
          tmp_gpio_state = OPEN;
      }
      else {
        if (g_freq_cal_info.capture_pulse_sum + INPUT_CAPTURE_CAL_COMPENSATION_TICK <= g_freq_cal_info.cmp_trg_cnt_ht)
          tmp_gpio_state = TRIGGERED;
        else
          tmp_gpio_state = OPEN;
      }
    }
    else {
      if (g_freq_cal_info.trigger_mode) {
        if (g_freq_cal_info.capture_pulse_sum + INPUT_CAPTURE_CAL_COMPENSATION_TICK >= g_freq_cal_info.cmp_trg_cnt_ht || \
            g_freq_cal_info.capture_pulse_sum + INPUT_CAPTURE_CAL_COMPENSATION_TICK <= g_freq_cal_info.cmp_trg_cnt_lt)
          tmp_gpio_state = TRIGGERED;
        else
          tmp_gpio_state = OPEN;
      }
      else {
        if (g_freq_cal_info.capture_pulse_sum + INPUT_CAPTURE_CAL_COMPENSATION_TICK >= g_freq_cal_info.cmp_trg_cnt_ht)
          tmp_gpio_state = TRIGGERED;
        else
          tmp_gpio_state = OPEN;
      }
    }

    if (g_freq_cal_info.trigger_invert)
      g_freq_cal_info.virtual_gpio_state = !tmp_gpio_state;
    else
      g_freq_cal_info.virtual_gpio_state = tmp_gpio_state;
  }
  else {
    g_freq_cal_info.virtual_gpio_state = TRIGGERED;
  }
  g_freq_cal_info.update_cnt++;
}

void
crm_configuration(void)
{
  // input capture tmr clock enable
  crm_periph_clock_enable(INPUT_CAPTURE_CRM_CLK, TRUE);

  // freq cal tmr clock enable
  crm_periph_clock_enable(INPUT_CAPTURE_CAL_CRM_CLK, TRUE);

  // gpio clock enable
  crm_periph_clock_enable(INPUT_CAPTURE_GPIO_CRM_CLK, TRUE);
}

void
gpio_configuration(void)
{
  gpio_init_type  gpio_init_struct = {0};
  gpio_init_struct.gpio_pins = INPUT_CAPTURE_PIN;
  gpio_init_struct.gpio_mode = GPIO_MODE_INPUT;
  gpio_init_struct.gpio_out_type = GPIO_OUTPUT_PUSH_PULL;
  gpio_init_struct.gpio_pull = GPIO_PULL_DOWN;
  gpio_init_struct.gpio_drive_strength = GPIO_DRIVE_STRENGTH_STRONGER;
  gpio_init(INPUT_CAPTURE_GPIO, &gpio_init_struct);
}

void
inductance_coil_crm_tmr_init(struct freq_cal_info *info)
{
  uint32_t tmp_pr_value = 0;

  // turn off the timer.
  NVIC_DisableIRQ(INPUT_CAPTURE_CAL_IRQn);
  tmr_counter_enable(INPUT_CAPTURE_CRM_TIM, FALSE);
  tmr_counter_enable(INPUT_CAPTURE_CAL_CRM_TIM, FALSE);
  tmr_interrupt_enable(INPUT_CAPTURE_CAL_CRM_TIM, TMR_OVF_INT | TMR_C1_INT, FALSE);

  // reset the flags
  INPUT_CAPTURE_CRM_TIM->ists &= 0;
  INPUT_CAPTURE_CAL_CRM_TIM->ists &= 0;

  // cal info init
  irqstatus_t irq_flags = irq_save();
  g_freq_cal_info.capture_pulse_sum = 0;
  g_freq_cal_info.need_capture_pulse_sum = info->need_capture_pulse_sum;
  g_freq_cal_info.freq_cal_cycle = info->freq_cal_cycle;
  g_freq_cal_info.freq_cal_timeout_cycle = info->freq_cal_timeout_cycle;
  g_freq_cal_info.virtual_gpio_state = TRIGGERED;
  g_freq_cal_info.update_cnt = 0;
  g_freq_cal_info.freq_cal_mode = info->freq_cal_mode;
  // g_freq_cal_info.trigger_freq = info->trigger_freq;
  g_freq_cal_info.trigger_mode = info->trigger_mode;
  g_freq_cal_info.trg_freq_ht = info->trg_freq_ht;
  g_freq_cal_info.trg_freq_lt = info->trg_freq_lt;
  g_freq_cal_info.trigger_invert = info->trigger_invert;
  g_freq_cal_info.cal_capture_pulse_window_size = info->cal_capture_pulse_window_size;

  init_moving_sum(&g_freq_cal_info.moving_sum, g_freq_cal_info.cal_capture_pulse_window_size);
  if (g_freq_cal_info.trigger_mode == 1 && g_freq_cal_info.freq_cal_mode == FIXED_TIME_CAL_MODE) {
    irq_restore(irq_flags);
    shutdown("fixed time cal mode cannot set bidirectional trigger!!!");
  }

  if (g_freq_cal_info.freq_cal_mode == FIXED_TIME_CAL_MODE) {
    g_freq_cal_info.cmp_trg_cnt_ht = g_freq_cal_info.trg_freq_ht * g_freq_cal_info.freq_cal_cycle * g_freq_cal_info.cal_capture_pulse_window_size;
    g_freq_cal_info.cmp_trg_cnt_lt = g_freq_cal_info.trg_freq_lt * g_freq_cal_info.freq_cal_cycle * g_freq_cal_info.cal_capture_pulse_window_size;
  }
  else {
    if (g_freq_cal_info.trigger_mode == 1 && (g_freq_cal_info.trg_freq_ht < g_freq_cal_info.trg_freq_lt)) {
      irq_restore(irq_flags);
      shutdown("trg freq ht is smaller than trg freq lt!!!");
    }

    if (g_freq_cal_info.trg_freq_ht) {
      g_freq_cal_info.cmp_trg_cnt_ht = ((double)INPUT_CAPTURE_CAL_CRM_TIM_CLOCK_FREQ /
                                          g_freq_cal_info.trg_freq_ht) * g_freq_cal_info.need_capture_pulse_sum * g_freq_cal_info.cal_capture_pulse_window_size;
    }
    else {
      g_freq_cal_info.cmp_trg_cnt_ht = 0xFFFFFFFF;
    }

    if (g_freq_cal_info.trg_freq_lt) {
      g_freq_cal_info.cmp_trg_cnt_lt = ((double)INPUT_CAPTURE_CAL_CRM_TIM_CLOCK_FREQ /
                                          g_freq_cal_info.trg_freq_lt) * g_freq_cal_info.need_capture_pulse_sum * g_freq_cal_info.cal_capture_pulse_window_size;
    }
    else {
      g_freq_cal_info.cmp_trg_cnt_lt = 0;
    }
  }
  irq_restore(irq_flags);

  // expanded to 32-bit timer
  tmr_input_config_type  tmr_input_config_struct;
  tmr_32_bit_function_enable(INPUT_CAPTURE_CRM_TIM, TRUE);
  tmr_32_bit_function_enable(INPUT_CAPTURE_CAL_CRM_TIM, TRUE);

  if (g_freq_cal_info.freq_cal_mode == FIXED_TIME_CAL_MODE) {
    double calc_pr = INPUT_CAPTURE_CAL_CRM_TIM_PR(g_freq_cal_info.freq_cal_cycle);
    if (calc_pr < 0.0 || calc_pr > (double)INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE) {
      shutdown("input capture calculation cycle is too long!!!");
    }
    tmp_pr_value = (uint32_t)calc_pr;
    tmr_base_init(INPUT_CAPTURE_CAL_CRM_TIM, tmp_pr_value, INPUT_CAPTURE_CAL_CRM_DIV -1);
    tmr_counter_value_set(INPUT_CAPTURE_CAL_CRM_TIM, 0);
    tmr_cnt_dir_set(INPUT_CAPTURE_CAL_CRM_TIM, TMR_COUNT_UP);
    if (info->freq_cal_cycle <= 0.0 || g_freq_cal_info.cal_capture_pulse_window_size == 0) {
      shutdown("Invalid frequency calculation parameters!");
    }
    g_freq_cal_info.freq_cal_factor = 1.0 / (info->freq_cal_cycle * g_freq_cal_info.cal_capture_pulse_window_size);

    tmr_base_init(INPUT_CAPTURE_CRM_TIM, INPUT_CAPTURE_CRM_TIM_MAX_PR_VALUE, 0);
    tmr_counter_value_set(INPUT_CAPTURE_CRM_TIM, 0);
    tmr_cnt_dir_set(INPUT_CAPTURE_CRM_TIM, TMR_COUNT_UP);
    tmr_external_clock_mode1_config(INPUT_CAPTURE_CRM_TIM, TMR_ES_FREQUENCY_DIV_1, TMR_ES_POLARITY_NON_INVERTED, 0);
  }
  else {
    tmr_primary_mode_select(INPUT_CAPTURE_CRM_TIM, TMR_PRIMARY_SEL_OVERFLOW);
    tmr_sub_sync_mode_set(INPUT_CAPTURE_CRM_TIM, TRUE);
    tmr_base_init(INPUT_CAPTURE_CRM_TIM, g_freq_cal_info.need_capture_pulse_sum - 1, 0);
    tmr_counter_value_set(INPUT_CAPTURE_CRM_TIM, 0);
    tmr_cnt_dir_set(INPUT_CAPTURE_CRM_TIM, TMR_COUNT_UP);

    g_freq_cal_info.freq_cal_factor = g_freq_cal_info.need_capture_pulse_sum * g_freq_cal_info.cal_capture_pulse_window_size;
    double timeout_pr = INPUT_CAPTURE_CAL_CRM_TIM_PR(g_freq_cal_info.freq_cal_timeout_cycle);
    if (timeout_pr < 0.0 || timeout_pr > (double)INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE) {
      shutdown("input capture timeout cycle is invalid!!!");
    }
    tmp_pr_value = (uint32_t)timeout_pr;
    tmr_base_init(INPUT_CAPTURE_CAL_CRM_TIM, tmp_pr_value, INPUT_CAPTURE_CAL_CRM_DIV -1);
    tmr_counter_value_set(INPUT_CAPTURE_CAL_CRM_TIM, 0);
    tmr_cnt_dir_set(INPUT_CAPTURE_CAL_CRM_TIM, TMR_COUNT_UP);
    tmr_trigger_input_select(INPUT_CAPTURE_CAL_CRM_TIM, TMR_SUB_INPUT_SEL_IS0);
    tmr_sub_mode_select(INPUT_CAPTURE_CAL_CRM_TIM, TMR_SUB_RESET_MODE);
    tmr_input_config_struct.input_channel_select = TMR_SELECT_CHANNEL_1;
    tmr_input_config_struct.input_mapped_select = TMR_CC_CHANNEL_MAPPED_STI;
    tmr_input_config_struct.input_polarity_select = TMR_INPUT_RISING_EDGE;
    tmr_input_channel_init(INPUT_CAPTURE_CAL_CRM_TIM, &tmr_input_config_struct, TMR_CHANNEL_INPUT_DIV_1);
    tmr_external_clock_mode1_config(INPUT_CAPTURE_CRM_TIM, TMR_ES_FREQUENCY_DIV_1, TMR_ES_POLARITY_NON_INVERTED, 0);
  }

  //interrupt enable
  tmr_overflow_request_source_set(INPUT_CAPTURE_CAL_CRM_TIM, TRUE);
  tmr_interrupt_enable(INPUT_CAPTURE_CAL_CRM_TIM, TMR_OVF_INT, TRUE);
  if (g_freq_cal_info.freq_cal_mode == FIXED_PULSE_NUM_CAL_MODE)
    tmr_interrupt_enable(INPUT_CAPTURE_CAL_CRM_TIM, TMR_C1_INT, TRUE);
  armcm_enable_irq(InputCapture_IRQHandler, INPUT_CAPTURE_CAL_IRQn, 0);

  //tmr enable counter
  tmr_counter_enable(INPUT_CAPTURE_CRM_TIM, TRUE);
  tmr_counter_enable(INPUT_CAPTURE_CAL_CRM_TIM, TRUE);
}

void inductance_coil_dev_init(struct freq_cal_info *info) {
  crm_configuration();
  gpio_configuration();
  inductance_coil_crm_tmr_init(info);
}

#else

#define INPUT_CAPTURE_CAL_COMPENSATION_TICK       (0)

// Todo: adaptation of other chips
void inductance_coil_dev_init(struct freq_cal_info *info)
{

}

#endif

uint8_t pulse_gpio_read(void)
{
  return g_freq_cal_info.virtual_gpio_state;
}

uint32_t frequency_conversion(uint64_t tick)
{
  uint32_t freq = 0;
  if (tick) {
    if (g_freq_cal_info.freq_cal_mode == FIXED_TIME_CAL_MODE) {
      double f = (double)tick * g_freq_cal_info.freq_cal_factor;
      if (f > (double)UINT32_MAX)
        freq = UINT32_MAX;
      else
        freq = (uint32_t)f;
    }
    else {
      double single_pulse_tick = 0;
      if (g_freq_cal_info.freq_cal_factor > 0)
        single_pulse_tick = (double)(tick + INPUT_CAPTURE_CAL_COMPENSATION_TICK) / g_freq_cal_info.freq_cal_factor;
      if (single_pulse_tick > 0.0) {
        double f = (double)CONFIG_CLOCK_FREQ / single_pulse_tick;
        if (f > (double)UINT32_MAX)
          freq = UINT32_MAX;
        else
          freq = (uint32_t)f;
      }
    }
  }
  return freq;
}

static uint_fast8_t
inductance_coil_event(struct timer *t)
{
  struct inductance_coil_dev *d = container_of(t, struct inductance_coil_dev, timer);

  sched_wake_task(&inductance_coil_wake);

  // Reschedule timer
  d->timer.waketime += d->rest_tick;
  return SF_RESCHEDULE;
}

void
command_inductance_coil_config(uint32_t *args)
{
  uint8_t count = 0, existing_oid;
  struct inductance_coil_dev *existing_dev;
  foreach_oid(existing_oid, existing_dev, command_inductance_coil_config) {
    count++;
  }
  if (count > 0)
    shutdown("currently only one input_capture resource is supported");

  struct inductance_coil_dev *dev = oid_alloc(args[0], command_inductance_coil_config, sizeof(*dev));

  inductance_coil_oid_malloc = args[0];
  irqstatus_t irq_flags = irq_save();
  dev->cal_info.freq_cal_mode = args[1];
  dev->cal_info.need_capture_pulse_sum = args[2];
  dev->cal_info.freq_cal_cycle = (double)args[3] / 1000000;
  dev->cal_info.freq_cal_timeout_cycle = (double)args[4] / 1000000;
  dev->cal_info.trigger_mode = args[5];
  dev->cal_info.trigger_invert = args[6];
  dev->cal_info.trg_freq_ht = args[7];
  dev->cal_info.trg_freq_lt = args[8];
  dev->cal_info.cal_capture_pulse_window_size = args[9];
  irq_restore(irq_flags);

  // initialize peripherals
  inductance_coil_dev_init(&dev->cal_info);

  dev->timer.func = inductance_coil_event;
}
DECL_COMMAND(command_inductance_coil_config,
            "inductance_coil_config oid=%c cal_mode=%u capture_over_cnt=%u freq_cal_cycle=%u cal_time_out=%u"
            " trigger_mode=%u trigger_invert=%u trg_freq_ht=%u trg_freq_lt=%u cal_window_size=%u");

static void
update_trigger_frequencies(struct timer_config_freq_param freq_param)
{
  struct inductance_coil_dev *d = oid_lookup(freq_param.oid, command_inductance_coil_config);
  irqstatus_t irq_flags = irq_save();
  if (freq_param.absolute_mode) {
    if (freq_param.trg_freq_ht < 0) freq_param.trg_freq_ht = 0;
    if (freq_param.trg_freq_lt < 0) freq_param.trg_freq_lt = 0;
    d->cal_info.trg_freq_ht = (uint32_t)freq_param.trg_freq_ht;
    d->cal_info.trg_freq_lt = (uint32_t)freq_param.trg_freq_lt;
  }
  else {
    uint64_t capture_sum = g_freq_cal_info.capture_pulse_sum;
    uint32_t cur_freq = frequency_conversion(capture_sum);

    int64_t calc_ht = (int64_t)freq_param.trg_freq_ht + (int64_t)cur_freq;
    if (calc_ht < 0)
      d->cal_info.trg_freq_ht = 0;
    else if (calc_ht > (int64_t)UINT32_MAX)
      d->cal_info.trg_freq_ht = UINT32_MAX;
    else
      d->cal_info.trg_freq_ht = (uint32_t)calc_ht;

    int64_t calc_lt = (int64_t)freq_param.trg_freq_lt + (int64_t)cur_freq;
    if (calc_lt < 0)
      d->cal_info.trg_freq_lt = 0;
    else if (calc_lt > (int64_t)UINT32_MAX)
      d->cal_info.trg_freq_lt = UINT32_MAX;
    else
      d->cal_info.trg_freq_lt = (uint32_t)calc_lt;
  }

  if (freq_param.trigger_mode == 1 && (d->cal_info.trg_freq_ht < d->cal_info.trg_freq_lt)) {
    irq_restore(irq_flags);
    shutdown("Bidirectional Trigger mode trg_freq_ht is smaller than trg_freq_lt!!!");
  }

  d->cal_info.trigger_mode = freq_param.trigger_mode;
  d->cal_info.trigger_invert = freq_param.trigger_invert;

  if (freq_param.force_update) {
    g_freq_cal_info.trg_freq_ht = d->cal_info.trg_freq_ht;
    g_freq_cal_info.trg_freq_lt = d->cal_info.trg_freq_lt;

    if (g_freq_cal_info.freq_cal_mode == FIXED_TIME_CAL_MODE) {
      g_freq_cal_info.cmp_trg_cnt_ht = g_freq_cal_info.trg_freq_ht * g_freq_cal_info.freq_cal_cycle * g_freq_cal_info.cal_capture_pulse_window_size;
      g_freq_cal_info.cmp_trg_cnt_lt = g_freq_cal_info.trg_freq_lt * g_freq_cal_info.freq_cal_cycle * g_freq_cal_info.cal_capture_pulse_window_size;
    }
    else {
      if (g_freq_cal_info.trg_freq_ht) {
        g_freq_cal_info.cmp_trg_cnt_ht = ((double)INPUT_CAPTURE_CAL_CRM_TIM_CLOCK_FREQ /
                                            g_freq_cal_info.trg_freq_ht) *  g_freq_cal_info.need_capture_pulse_sum * g_freq_cal_info.cal_capture_pulse_window_size;
      }
      else {
        g_freq_cal_info.cmp_trg_cnt_ht = 0xFFFFFFFF;
      }

      if (g_freq_cal_info.trg_freq_lt) {
        g_freq_cal_info.cmp_trg_cnt_lt = ((double)INPUT_CAPTURE_CAL_CRM_TIM_CLOCK_FREQ /
                                            g_freq_cal_info.trg_freq_lt) *  g_freq_cal_info.need_capture_pulse_sum * g_freq_cal_info.cal_capture_pulse_window_size;
      }
      else {
        g_freq_cal_info.cmp_trg_cnt_lt = 0;
      }
    }
    g_freq_cal_info.trigger_invert = d->cal_info.trigger_invert;
    g_freq_cal_info.trigger_mode = d->cal_info.trigger_mode;
  }
  irq_restore(irq_flags);
  }
}

static uint_fast8_t
inductance_coil_config_freq_event(struct timer *t)
{
  struct inductance_coil_dev *d = container_of(t, struct inductance_coil_dev, config_freq_timer);
  update_trigger_frequencies(d->config_freq_param);
  return SF_DONE;
}

void
command_virtual_gpio_trigger_with_timer(uint32_t *args)
{
  uint8_t oid = args[0];
  uint32_t clock = args[7];
  struct inductance_coil_dev *d = oid_lookup(oid, command_inductance_coil_config);

  irqstatus_t irq_flags = irq_save();
  sched_del_timer(&d->config_freq_timer);

  d->config_freq_param.oid = oid;
  d->config_freq_param.absolute_mode = !!args[1];
  d->config_freq_param.trigger_mode = args[2];
  d->config_freq_param.trigger_invert = args[3];
  d->config_freq_param.trg_freq_ht = args[4];
  d->config_freq_param.trg_freq_lt = args[5];
  d->config_freq_param.force_update = !!args[6];

  uint32_t current_time = timer_read_time();
  if (!timer_is_before(current_time, clock)) {
    update_trigger_frequencies(d->config_freq_param);
  } else {
    d->config_freq_timer.func = inductance_coil_config_freq_event;
    uint32_t min_waketime = current_time + timer_from_us(100);
    d->config_freq_timer.waketime = timer_is_before(min_waketime, clock) ? clock : min_waketime;
    sched_add_timer(&d->config_freq_timer);
  }
  irq_restore(irq_flags);
}
DECL_COMMAND(command_virtual_gpio_trigger_with_timer,
            "virtual_gpio_trigger_with_timer oid=%c absolute_mode=%u trigger_mode=%u trigger_invert=%u"
            " trg_freq_ht=%u trg_freq_lt=%u force_update=%u clock=%u");

void
command_virtual_gpio_trigger(uint32_t *args)
{
  struct timer_config_freq_param freq_param;
  freq_param.oid = args[0];
  freq_param.absolute_mode = !!args[1];
  freq_param.trigger_mode = args[2];
  freq_param.trigger_invert = args[3];
  freq_param.trg_freq_ht = args[4];
  freq_param.trg_freq_lt = args[5];
  freq_param.force_update = !!args[6];
  update_trigger_frequencies(freq_param);
}
DECL_COMMAND(command_virtual_gpio_trigger,
            "virtual_gpio_trigger oid=%c absolute_mode=%u trigger_mode=%u trigger_invert=%u"
            " trg_freq_ht=%u trg_freq_lt=%u force_update=%u");

void
command_inductance_coil_query(uint32_t *args)
{
    struct inductance_coil_dev *d = oid_lookup(args[0], command_inductance_coil_config);
    sched_del_timer(&d->timer);
    d->timer.waketime = args[1];
    d->rest_tick = args[2];
    if (!d->rest_tick)
        return;
    sched_add_timer(&d->timer);
}
DECL_COMMAND(command_inductance_coil_query,
             "inductance_coil_query oid=%c clock=%u rest_tick=%u");

void
command_query_inductance_coil(uint32_t *args)
{
  struct inductance_coil_dev *d = oid_lookup(args[0], command_inductance_coil_config);
  sched_del_timer(&d->timer);
  if (!args[1])
      return;

  d->rest_tick = args[1];
  sensor_bulk_reset(&d->sb);

  irq_disable();
  d->timer.waketime = timer_read_time() + d->rest_tick;
  sched_add_timer(&d->timer);
  irq_enable();
}
DECL_COMMAND(command_query_inductance_coil, "query_inductance_coil oid=%c rest_ticks=%u");

void
command_query_inductance_coil_status(uint32_t *args)
{
  struct inductance_coil_dev *icd = oid_lookup(args[0], command_inductance_coil_config);

  irq_disable();
  uint32_t time = timer_read_time();
  irq_enable();
  sensor_bulk_status(&icd->sb, args[0], time, 0, 0);
}
DECL_COMMAND(command_query_inductance_coil_status, "query_inductance_coil_status oid=%c");

static void
inductance_coil_query(struct inductance_coil_dev *icd, uint64_t capture_sum, uint8_t oid)
{
  uint32_t cal_freq = 0;
  cal_freq = frequency_conversion(capture_sum);

  uint8_t *d = &icd->sb.data[icd->sb.data_count];
  memcpy(d, &cal_freq, sizeof(cal_freq));
  icd->sb.data_count += BYTES_PER_SAMPLE;

  // check whether the buffer cannot eat next one sample
  // if not, must flush the buffer
  if (icd->sb.data_count + BYTES_PER_SAMPLE > ARRAY_SIZE(icd->sb.data)) {
    sensor_bulk_report(&icd->sb, oid);
  }
}

void
command_query_inductance_coil_config_info(uint32_t *args)
{
  sendf("inductance_coil_info oid=%c cal_mode=%u capture_over_cnt=%u freq_cal_cycle=%u cal_time_out=%u"
        " trigger_mode=%u trigger_invert=%u trg_freq_ht=%u trg_freq_lt=%u capture_freq=%u virtual_gpio=%u", args[0], g_freq_cal_info.freq_cal_mode,
        g_freq_cal_info.need_capture_pulse_sum, (uint32_t)(g_freq_cal_info.freq_cal_cycle*1000000), (uint32_t)(g_freq_cal_info.freq_cal_timeout_cycle*1000000),
        g_freq_cal_info.trigger_mode, g_freq_cal_info.trigger_invert, g_freq_cal_info.trg_freq_ht, g_freq_cal_info.trg_freq_lt,
        frequency_conversion(g_freq_cal_info.capture_pulse_sum), g_freq_cal_info.virtual_gpio_state);
}
DECL_COMMAND(command_query_inductance_coil_config_info, "query_inductance_coil_config_info oid=%c");

void
inductance_coil_task(void)
{
  if (!sched_check_wake(&inductance_coil_wake))
      return;

  uint8_t oid;
  struct inductance_coil_dev *dev;
  foreach_oid(oid, dev, command_inductance_coil_config) {
    inductance_coil_query(dev, g_freq_cal_info.capture_pulse_sum, oid);
  }
}
DECL_TASK(inductance_coil_task);

void
inductance_coil_shutdown(void)
{
  uint8_t i;
  struct inductance_coil_dev *d;
  foreach_oid(i, d, command_inductance_coil_config) {
    sched_del_timer(&d->timer);
    sched_del_timer(&d->config_freq_timer);
  }
#if CONFIG_MACH_AT32F4x
  tmr_interrupt_enable(INPUT_CAPTURE_CAL_CRM_TIM, TMR_OVF_INT | TMR_C1_INT, FALSE);
  tmr_counter_enable(INPUT_CAPTURE_CAL_CRM_TIM, FALSE);
  tmr_counter_enable(INPUT_CAPTURE_CRM_TIM, FALSE);
  NVIC_DisableIRQ(INPUT_CAPTURE_CAL_IRQn);
#endif
  inductance_coil_oid_malloc = 0;
}
DECL_SHUTDOWN(inductance_coil_shutdown);
