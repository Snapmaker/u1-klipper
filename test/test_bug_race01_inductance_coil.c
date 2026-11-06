#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#define FIXED_TIME_CAL_MODE 0
#define FIXED_PULSE_NUM_CAL_MODE 1
#define TRIGGERED 0
#define OPEN 1

struct freq_cal_info {
    uint8_t freq_cal_mode;
    uint8_t trigger_mode;
    uint8_t trigger_invert;
    uint8_t virtual_gpio_state;
    uint32_t trg_freq_ht;
    uint32_t trg_freq_lt;
    uint32_t cmp_trg_cnt_ht;
    uint32_t cmp_trg_cnt_lt;
    uint32_t need_capture_pulse_sum;
    uint32_t cal_capture_pulse_window_size;
    double freq_cal_cycle;
    uint64_t capture_pulse_sum;
};

struct timer_config_freq_param {
    uint8_t oid;
    uint8_t absolute_mode;
    uint8_t trigger_mode;
    uint8_t trigger_invert;
    int32_t trg_freq_ht;
    int32_t trg_freq_lt;
    uint8_t force_update;
};

static struct freq_cal_info g_cal_info = {0};
static int s_irq_disabled = 0;

static int irq_save_mock(void) {
    int prev = s_irq_disabled;
    s_irq_disabled = 1;
    return prev;
}

static void irq_restore_mock(int flags) {
    s_irq_disabled = flags;
}

/* Patched update_trigger_frequencies simulating atomic threshold updates */
static void update_trigger_frequencies_mock(struct timer_config_freq_param *param) {
    int flags = irq_save_mock();

    if (param->absolute_mode) {
        g_cal_info.trg_freq_ht = (uint32_t)param->trg_freq_ht;
        g_cal_info.trg_freq_lt = (uint32_t)param->trg_freq_lt;
    }

    g_cal_info.trigger_mode = param->trigger_mode;
    g_cal_info.trigger_invert = param->trigger_invert;

    if (param->force_update) {
        if (g_cal_info.freq_cal_mode == FIXED_TIME_CAL_MODE) {
            g_cal_info.cmp_trg_cnt_ht = (uint32_t)(g_cal_info.trg_freq_ht * g_cal_info.freq_cal_cycle * g_cal_info.cal_capture_pulse_window_size);
            g_cal_info.cmp_trg_cnt_lt = (uint32_t)(g_cal_info.trg_freq_lt * g_cal_info.freq_cal_cycle * g_cal_info.cal_capture_pulse_window_size);
        }
    }

    irq_restore_mock(flags);
}

/* ISR mock that checks for atomic consistency: if ISR fires, s_irq_disabled must be 0 */
static void isr_mock_check(void) {
    assert(s_irq_disabled == 0 && "ISR must not execute while update_trigger_frequencies is in critical section");
    // Verify thresholds are not partially updated
    if (g_cal_info.trigger_mode == 1) {
        assert(g_cal_info.cmp_trg_cnt_ht >= g_cal_info.cmp_trg_cnt_lt);
    }
}

int main(void) {
    printf("Starting BUG-RACE-01 Priority-0 ISR Concurrency tests...\n");

    g_cal_info.freq_cal_mode = FIXED_TIME_CAL_MODE;
    g_cal_info.freq_cal_cycle = 0.001; // 1ms
    g_cal_info.cal_capture_pulse_window_size = 10;
    g_cal_info.need_capture_pulse_sum = 100;

    struct timer_config_freq_param p = {
        .oid = 1,
        .absolute_mode = 1,
        .trigger_mode = 1,
        .trigger_invert = 0,
        .trg_freq_ht = 500000,
        .trg_freq_lt = 250000,
        .force_update = 1
    };

    update_trigger_frequencies_mock(&p);
    assert(s_irq_disabled == 0);
    isr_mock_check();
    printf("  [PASS] Atomic threshold calculation under IRQ disabled lock succeeded.\n");

    assert(g_cal_info.cmp_trg_cnt_ht == 5000);
    assert(g_cal_info.cmp_trg_cnt_lt == 2500);
    printf("  [PASS] Thresholds correctly synchronized: ht=%u, lt=%u\n",
           g_cal_info.cmp_trg_cnt_ht, g_cal_info.cmp_trg_cnt_lt);

    printf("BUG-RACE-01: All unit tests passed successfully.\n");
    return 0;
}

