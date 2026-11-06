#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#define SDIO_CLK_FREQ 48000000U
#define CONFIG_CLOCK_FREQ 168000000U
#define INPUT_CAPTURE_CAL_COMPENSATION_TICK 0

// Test SDIO speed division logic
static bool sdio_calc_clkdiv_safe(uint32_t speed, uint8_t *out_clkdiv) {
    if (speed == 0) {
        return false; // Error intercepted (shutdown)
    }
    uint32_t div = SDIO_CLK_FREQ / speed;
    *out_clkdiv = (div <= 2) ? 0 : ((div - 2 > 255) ? 255 : (uint8_t)(div - 2));
    return true;
}

// Test inductance_coil factor calculation
static bool inductance_calc_factor_safe(double cycle, uint32_t window_size, double *out_factor) {
    if (cycle <= 0.0 || window_size == 0) {
        return false; // Error intercepted (shutdown)
    }
    *out_factor = 1.0 / (cycle * (double)window_size);
    return true;
}

// Test frequency_conversion zero divisions
static uint32_t frequency_conversion_safe(uint64_t tick, int mode, double factor) {
    uint32_t freq = 0;
    if (tick) {
        if (mode == 0) { // FIXED_TIME_CAL_MODE
            double f = (double)tick * factor;
            if (f > (double)UINT32_MAX)
                freq = UINT32_MAX;
            else
                freq = (uint32_t)f;
        } else { // FIXED_PULSE_NUM_CAL_MODE
            double single_pulse_tick = 0;
            if (factor > 0.0) {
                single_pulse_tick = (double)(tick + INPUT_CAPTURE_CAL_COMPENSATION_TICK) / factor;
            }
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

int main(void) {
    printf("Starting BUG-DIV-01 Hardware Division by Zero tests...\n");

    // 1. SDIO speed=0 check
    uint8_t clkdiv = 0;
    assert(!sdio_calc_clkdiv_safe(0, &clkdiv));
    printf("  SDIO speed=0 safely rejected (no divide by zero).\n");

    // Normal SDIO speeds
    assert(sdio_calc_clkdiv_safe(48000000, &clkdiv)); // div=1 <= 2 -> 0
    assert(clkdiv == 0);
    assert(sdio_calc_clkdiv_safe(24000000, &clkdiv)); // div=2 <= 2 -> 0
    assert(clkdiv == 0);
    assert(sdio_calc_clkdiv_safe(12000000, &clkdiv)); // div=4 -> clkdiv = 2
    assert(clkdiv == 2);

    // 2. Inductance coil factor zero checks
    double factor = 0;
    assert(!inductance_calc_factor_safe(0.0, 2, &factor));
    assert(!inductance_calc_factor_safe(-0.01, 2, &factor));
    assert(!inductance_calc_factor_safe(0.01, 0, &factor));
    printf("  Inductance coil zero cycle/window parameters safely rejected.\n");

    assert(inductance_calc_factor_safe(0.01, 2, &factor));
    assert(factor == 50.0);

    // 3. frequency_conversion zero divisions
    assert(frequency_conversion_safe(1000, 1, 0.0) == 0); // factor = 0 -> no div by 0
    assert(frequency_conversion_safe(0, 1, 100.0) == 0);   // tick = 0 -> 0

    uint32_t f_ok = frequency_conversion_safe(1680, 1, 1.0); // 168MHz / 1680 = 100,000 Hz
    assert(f_ok == 100000);
    printf("  frequency_conversion safely handles factor=0 without division by zero.\n");

    printf("\nALL BUG-DIV-01 TESTS PASSED SUCCESSFULLY!\n");
    return 0;
}

