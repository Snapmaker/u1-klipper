// Test harness for BUG-INT-01: 32-bit Integer Overflow in SDIO timeout and uint8_t Underflow in clkdiv
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <assert.h>

#define TIMEOUT_MSEC 500
#define SDIO_CLK_FREQ 48000000U

// Unpatched calculation (32-bit arithmetic)
static uint32_t calc_timeout_unpatched(uint32_t speed)
{
    // Under 32-bit arithmetic, TIMEOUT_MSEC * speed overflows uint32_t when speed >= 8589935
    uint32_t timeout = (uint32_t)(TIMEOUT_MSEC * speed) / 1000;
    return timeout;
}

// Patched calculation (64-bit arithmetic)
static uint32_t calc_timeout_patched(uint32_t speed)
{
    uint32_t timeout = (uint32_t)((uint64_t)TIMEOUT_MSEC * speed / 1000);
    return timeout;
}

// Unpatched clock divider calculation (uint8_t underflow / truncation)
static uint8_t calc_clkdiv_unpatched(uint32_t speed)
{
    return (uint8_t)((SDIO_CLK_FREQ / speed) - 2);
}

// Patched clock divider calculation (bounded and saturating)
static uint8_t calc_clkdiv_patched(uint32_t speed)
{
    if (!speed)
        return 255;
    uint32_t div = SDIO_CLK_FREQ / speed;
    uint8_t clkdiv = (div <= 2) ? 0 : ((div - 2 > 255) ? 255 : (uint8_t)(div - 2));
    return clkdiv;
}

int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    printf("Starting BUG-INT-01 SDIO timeout & clkdiv tests...\n");

    // Part 1: Timeout overflow test
    uint32_t test_speeds[] = {
        400000U,
        8000000U,
        9000000U,
        24000000U,
        25000000U,
        48000000U,
        50000000U
    };
    size_t num_speeds = sizeof(test_speeds) / sizeof(test_speeds[0]);

    printf("--- Part 1: Timeout Calculation Tests ---\n");
    for (size_t i = 0; i < num_speeds; i++) {
        uint32_t speed = test_speeds[i];
        uint32_t expected_timeout = (uint32_t)((uint64_t)TIMEOUT_MSEC * speed / 1000);
        uint32_t patched = calc_timeout_patched(speed);

        assert(patched == expected_timeout);

        if (speed >= 8589935U) {
            uint32_t unpatched = calc_timeout_unpatched(speed);
            printf("Speed %u Hz: Expected %u, Unpatched %u (DIFF: %u -> OVERFLOW!)\n",
                   speed, expected_timeout, unpatched, expected_timeout - unpatched);
            assert(unpatched != expected_timeout);
        } else {
            printf("Speed %u Hz: Expected %u, Patched %u (OK)\n",
                   speed, expected_timeout, patched);
        }
    }

    printf("--- Part 2: Clock Divider Underflow & Saturation Tests ---\n");
    // High speeds (speed > 24MHz causes div <= 1, (div - 2) underflows uint8_t to 254/255)
    uint8_t div_48m = calc_clkdiv_patched(48000000U);
    uint8_t div_48m_unpatched = calc_clkdiv_unpatched(48000000U);
    printf("Speed 48MHz: Patched clkdiv=%u, Unpatched clkdiv=%u (UNDERFLOW to 255!)\n",
           div_48m, div_48m_unpatched);
    assert(div_48m == 0);
    assert(div_48m_unpatched == 255);

    uint8_t div_25m = calc_clkdiv_patched(25000000U);
    uint8_t div_25m_unpatched = calc_clkdiv_unpatched(25000000U);
    printf("Speed 25MHz: Patched clkdiv=%u, Unpatched clkdiv=%u (UNDERFLOW to 255!)\n",
           div_25m, div_25m_unpatched);
    assert(div_25m == 0);
    assert(div_25m_unpatched == 255);

    // Standard 400kHz init clock: div = 48000000 / 400000 = 120 -> clkdiv = 118
    uint8_t div_400k = calc_clkdiv_patched(400000U);
    printf("Speed 400kHz: Patched clkdiv=%u (OK)\n", div_400k);
    assert(div_400k == 118);

    // Very low clock (100kHz): div = 480 -> div - 2 = 478 > 255. Unpatched truncates 478 % 256 = 222
    uint8_t div_100k = calc_clkdiv_patched(100000U);
    uint8_t div_100k_unpatched = calc_clkdiv_unpatched(100000U);
    printf("Speed 100kHz: Patched clkdiv=%u (Saturated to 255), Unpatched clkdiv=%u (TRUNCATED!)\n",
           div_100k, div_100k_unpatched);
    assert(div_100k == 255);
    assert(div_100k_unpatched == 222);

    printf("ALL BUG-INT-01 TESTS PASSED SUCCESSFULLY!\n");
    return 0;
}
