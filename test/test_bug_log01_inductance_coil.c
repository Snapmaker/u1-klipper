#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <assert.h>

#define MAX_BUFFER_SIZE 32

typedef struct {
    uint32_t buffer[MAX_BUFFER_SIZE];
    uint32_t head;
    uint32_t count;
    uint32_t bufferSize;
    uint64_t sum;
} MOVING_SUM;

static void init_moving_sum(MOVING_SUM *ms, uint32_t size) {
    if (size > MAX_BUFFER_SIZE) size = MAX_BUFFER_SIZE;
    ms->bufferSize = size;
    ms->head = 0;
    ms->count = 0;
    ms->sum = 0;
    for (uint32_t i = 0; i < MAX_BUFFER_SIZE; ++i) {
        ms->buffer[i] = 0;
    }
}

static void add_value(MOVING_SUM *ms, uint32_t value) {
    if (ms->bufferSize == 0) return;
    ms->sum -= ms->buffer[ms->head];
    ms->sum += value;
    ms->buffer[ms->head] = value;
    ms->head = (ms->head + 1) % ms->bufferSize;
    if (ms->count < ms->bufferSize) {
        ms->count++;
    }
}

/* Patched get_sum logic */
static uint64_t get_sum(MOVING_SUM *ms) {
    if (ms->bufferSize == 0 || ms->count < ms->bufferSize)
        return 0;
    return ms->sum;
}

/* Original buggy get_sum logic for comparison */
static uint64_t get_sum_buggy(MOVING_SUM *ms) {
    if (ms->count + 1 < ms->bufferSize || ms->bufferSize == 0)
        return 0;
    return ms->sum;
}

int main(void) {
    printf("Starting BUG-LOG-01 Moving Sum Off-By-One tests...\n");

    MOVING_SUM ms;

    // Test 1: Window size 2 (Snapmaker standard configuration)
    init_moving_sum(&ms, 2);
    assert(get_sum(&ms) == 0);
    assert(get_sum_buggy(&ms) == 0);

    // Add first sample: 1000
    add_value(&ms, 1000);
    assert(ms.count == 1);

    // Buggy implementation returns 1000 prematurely (1 + 1 < 2 is false!)
    assert(get_sum_buggy(&ms) == 1000);

    // Patched implementation correctly waits for window saturation
    assert(get_sum(&ms) == 0);
    printf("  [PASS] Single sample in window size 2 correctly returns 0.\n");

    // Add second sample: 1200
    add_value(&ms, 1200);
    assert(ms.count == 2);
    assert(get_sum(&ms) == 2200);
    assert(get_sum_buggy(&ms) == 2200);
    printf("  [PASS] Full window returns correct sum (2200).\n");

    // Add third sample: 1500 (rolls over 1000, new window: 1200 + 1500 = 2700)
    add_value(&ms, 1500);
    assert(ms.count == 2);
    assert(get_sum(&ms) == 2700);
    printf("  [PASS] Rolling window calculates correct updated sum (2700).\n");

    // Test 2: Window size 4
    init_moving_sum(&ms, 4);
    add_value(&ms, 10);
    assert(get_sum(&ms) == 0);
    add_value(&ms, 20);
    assert(get_sum(&ms) == 0);
    add_value(&ms, 30);
    // At count=3, buggy returns sum(60), patched returns 0
    assert(get_sum_buggy(&ms) == 60);
    assert(get_sum(&ms) == 0);
    add_value(&ms, 40);
    assert(get_sum(&ms) == 100);
    printf("  [PASS] Window size 4 verified: suppresses partial sums until all 4 samples arrive.\n");

    // Test 3: Zero buffer size
    init_moving_sum(&ms, 0);
    assert(get_sum(&ms) == 0);
    printf("  [PASS] Zero buffer size correctly returns 0.\n");

    printf("BUG-LOG-01: All unit tests passed successfully.\n");
    return 0;
}

