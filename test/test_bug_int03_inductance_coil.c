#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#define MAX_BUFFER_SIZE 50
#define INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE 0xFFFFFFFFU
#define CONFIG_CLOCK_FREQ 168000000U
#define INPUT_CAPTURE_CAL_CRM_DIV 1

#define INPUT_CAPTURE_CAL_CRM_TIM_PR(CYCLE) \
    ((double)CONFIG_CLOCK_FREQ / INPUT_CAPTURE_CAL_CRM_DIV * (CYCLE) - 1.0)

// Struct definitions: Unpatched (32-bit) vs Patched (64-bit)
typedef struct {
    uint32_t buffer[MAX_BUFFER_SIZE];
    uint32_t bufferSize;
    uint32_t head;
    uint32_t count;
    uint32_t sum;
} MOVING_SUM_UNPATCHED;

typedef struct {
    uint32_t buffer[MAX_BUFFER_SIZE];
    uint32_t bufferSize;
    uint32_t head;
    uint32_t count;
    uint64_t sum;
} MOVING_SUM_PATCHED;

static void add_value_unpatched(MOVING_SUM_UNPATCHED *ms, uint32_t value) {
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

static void add_value_patched(MOVING_SUM_PATCHED *ms, uint32_t value) {
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

static bool check_pr_unpatched(double cycle) {
    uint32_t tmp_pr_value = (uint32_t)INPUT_CAPTURE_CAL_CRM_TIM_PR(cycle);
    // Tautological check: always false for uint32_t
    return (tmp_pr_value > INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE);
}

static bool check_pr_patched(double cycle) {
    double calc_pr = INPUT_CAPTURE_CAL_CRM_TIM_PR(cycle);
    return (calc_pr < 0.0 || calc_pr > (double)INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE);
}

static uint32_t calc_freq_ht_unpatched(int32_t trg_freq_ht, uint32_t cur_freq) {
    if (trg_freq_ht + (int)cur_freq < 0) {
        return 0;
    } else {
        return trg_freq_ht + cur_freq;
    }
}

static uint32_t calc_freq_ht_patched(int32_t trg_freq_ht, uint32_t cur_freq) {
    int64_t calc_ht = (int64_t)trg_freq_ht + (int64_t)cur_freq;
    if (calc_ht < 0) {
        return 0;
    } else if (calc_ht > (int64_t)UINT32_MAX) {
        return UINT32_MAX;
    } else {
        return (uint32_t)calc_ht;
    }
}

int main(void) {
    printf("Starting BUG-INT-03 Inductance Coil unit tests...\n");

    // 1. Test PR bounds check tautology
    // A 30-second cycle exceeds 32-bit timer PR limit (168MHz * 30s = 5,040,000,000 > UINT32_MAX)
    double large_cycle = 30.0;
    bool unpatched_caught = check_pr_unpatched(large_cycle);
    bool patched_caught = check_pr_patched(large_cycle);

    printf("PR check for large cycle (30s):\n");
    printf("  Unpatched detected overflow: %s (BUG: tautology failed!)\n", unpatched_caught ? "YES" : "NO");
    printf("  Patched detected overflow:   %s (CORRECT)\n", patched_caught ? "YES" : "NO");
    assert(!unpatched_caught); // Demonstrates unpatched bug
    assert(patched_caught);    // Confirms patched protection

    // Negative cycle
    double neg_cycle = -0.5;
    assert(!check_pr_unpatched(neg_cycle)); // Unpatched fails to catch negative
    assert(check_pr_patched(neg_cycle));    // Patched catches negative

    // 2. Test MOVING_SUM 32-bit overflow
    MOVING_SUM_UNPATCHED ms_unpatched = {0};
    MOVING_SUM_PATCHED ms_patched = {0};
    ms_unpatched.bufferSize = 50;
    ms_patched.bufferSize = 50;

    // Add 50 samples of 200,000,000 (Expected sum = 10,000,000,000 > 2^32)
    uint32_t sample_val = 200000000U;
    for (int i = 0; i < 50; ++i) {
        add_value_unpatched(&ms_unpatched, sample_val);
        add_value_patched(&ms_patched, sample_val);
    }

    uint64_t expected_sum = 50ULL * (uint64_t)sample_val;
    printf("\nMOVING_SUM overflow test (50 * 200,000,000):\n");
    printf("  Expected sum:  %llu\n", (unsigned long long)expected_sum);
    printf("  Unpatched sum: %u (OVERFLOWED! diff: %llu)\n", ms_unpatched.sum,
           (unsigned long long)(expected_sum - ms_unpatched.sum));
    printf("  Patched sum:   %llu (CORRECT)\n", (unsigned long long)ms_patched.sum);

    assert(ms_unpatched.sum != expected_sum);
    assert(ms_patched.sum == expected_sum);

    // 3. Test signed integer overflow in frequency addition
    // trg_freq_ht = 1,500,000,000; cur_freq = 1,000,000,000
    // Sum = 2,500,000,000 (> INT32_MAX 2,147,483,647)
    int32_t trg_offset = 1500000000;
    uint32_t current_frequency = 1000000000U;

    uint32_t unpatched_freq = calc_freq_ht_unpatched(trg_offset, current_frequency);
    uint32_t patched_freq = calc_freq_ht_patched(trg_offset, current_frequency);

    printf("\nFrequency addition signed overflow test:\n");
    printf("  Expected frequency:  2500000000\n");
    printf("  Unpatched frequency: %u (WRONGLY RESET TO 0 DUE TO SIGNED OVERFLOW!)\n", unpatched_freq);
    printf("  Patched frequency:   %u (CORRECT)\n", patched_freq);

    assert(unpatched_freq == 0);
    assert(patched_freq == 2500000000U);

    // Negative offset exceeding cur_freq clamps cleanly to 0
    assert(calc_freq_ht_patched(-600000, 500000) == 0);
    // Positive offset added
    assert(calc_freq_ht_patched(50000, 500000) == 550000);

    printf("\nALL BUG-INT-03 TESTS PASSED SUCCESSFULLY!\n");
    return 0;
}

