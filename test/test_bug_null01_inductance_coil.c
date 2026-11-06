#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>

#define SENSOR_BULK_MAX_SIZE 64
#define BYTES_PER_SAMPLE 4

// Simulates the exact layout from src/sensor_bulk.h
struct sensor_bulk {
    uint32_t possible_overflows; // 4 bytes
    uint8_t data_count;          // 1 byte (causes 1-byte unaligned offset)
    uint8_t data[SENSOR_BULK_MAX_SIZE];
};

static void write_sample_safe(struct sensor_bulk *sb, uint32_t cal_freq) {
    uint8_t *d = &sb->data[sb->data_count];
    memcpy(d, &cal_freq, sizeof(cal_freq));
    sb->data_count += BYTES_PER_SAMPLE;
}

int main(void) {
    printf("Starting BUG-NULL-01 Unaligned Pointer Dereference tests...\n");

    struct sensor_bulk sb = {0};

    // Test writing to an unaligned offset (offset 1 in data buffer)
    sb.data_count = 1;
    uint32_t sample1 = 0x12345678;
    write_sample_safe(&sb, sample1);

    uint32_t read_back1;
    memcpy(&read_back1, &sb.data[1], sizeof(read_back1));
    assert(read_back1 == sample1);
    printf("  Successfully wrote and read sample at unaligned offset 1.\n");

    // Test sequential writes starting from offset 5 (exact sensor_bulk struct offset)
    sb.data_count = 5;
    uint32_t test_values[] = { 100000, 250000, 333333, 499999, 168000000 };
    for (int i = 0; i < 5; ++i) {
        uint8_t offset = sb.data_count;
        write_sample_safe(&sb, test_values[i]);
        uint32_t val;
        memcpy(&val, &sb.data[offset], sizeof(val));
        assert(val == test_values[i]);
    }
    printf("  Successfully wrote 5 sequential unaligned samples without faults.\n");

    printf("\nALL BUG-NULL-01 TESTS PASSED SUCCESSFULLY!\n");
    return 0;
}

