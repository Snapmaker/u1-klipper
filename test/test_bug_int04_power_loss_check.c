#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#define TRM_OVER_FREQ 10000

static bool validate_and_calc_pr(double trigger_time, uint16_t *out_pr) {
    double calc_ticks = (double)TRM_OVER_FREQ * trigger_time - 1.0;
    if (calc_ticks < 0.0 || calc_ticks > 65535.0) {
        return false;
    }
    *out_pr = (uint16_t)calc_ticks;
    return true;
}

int main(void) {
    printf("Starting BUG-INT-04 16-Bit Timer Underflow/Overflow tests...\n");

    uint16_t pr = 0;

    // Test 1: Zero trigger time (underflow in unpatched code: calc_ticks < 0.0)
    double unpatched_zero_calc = (double)TRM_OVER_FREQ * 0.0 - 1.0;
    assert(unpatched_zero_calc < 0.0);
    assert(!validate_and_calc_pr(0.0, &pr));
    printf("  [PASS] Zero trigger time underflow detected and rejected.\n");

    // Test 2: Negative trigger time
    assert(!validate_and_calc_pr(-0.01, &pr));
    printf("  [PASS] Negative trigger time rejected.\n");

    // Test 3: Excessive trigger time (> 6.5535s overflows 16-bit)
    // 7.0 seconds * 10000 - 1.0 = 69999.0 ticks (> 65535.0)
    double unpatched_over_calc = (double)TRM_OVER_FREQ * 7.0 - 1.0;
    assert(unpatched_over_calc > 65535.0);
    assert(!validate_and_calc_pr(7.0, &pr));
    printf("  [PASS] >6.5535s trigger time overflow detected and rejected.\n");

    // Test 4: Valid standard value (0.0109s = 10.9ms -> 109 - 1 = 108 ticks)
    assert(validate_and_calc_pr(0.0109, &pr));
    assert(pr == 108);
    printf("  [PASS] Valid trigger time 0.0109s correctly calculated as %u ticks.\n", pr);

    // Test 5: Boundary value (6.5536s * 10000 - 1 = 65535 ticks)
    assert(validate_and_calc_pr(6.5536, &pr));
    assert(pr == 65535);
    printf("  [PASS] Upper bound trigger time 6.5536s correctly accepted as 65535 ticks.\n");

    printf("BUG-INT-04: All C unit tests passed successfully.\n");
    return 0;
}
