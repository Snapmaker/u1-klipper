// Test harness for BUG-BUF-01: Integer Overflow in sdiocmds.c buffer bounds check
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>

// Mock structures and functions matching sdiocmds.c
struct sdio_config {
    void *sdio;
};

struct sdiodev_s {
    struct sdio_config sdio_config;
    uint32_t blocksize;
    uint32_t speed;
    uint8_t data_buffer[4096];
};

static struct sdiodev_s test_sdio_dev;
static uint8_t last_sent_len = 0;
static uint8_t last_sent_data[256];

struct sdiodev_s *sdiodev_oid_lookup(uint8_t oid)
{
    (void)oid;
    return &test_sdio_dev;
}

static uint8_t *g_test_data_ptr = NULL;

uint8_t *command_decode_ptr(uint32_t ptr_val)
{
    (void)ptr_val;
    return g_test_data_ptr;
}

void sendf(const char *fmt, ...)
{
    // Mock sendf: record sent length and buffer
    (void)fmt;
}

// Function implementations to test
#ifdef TEST_UNPATCHED
void command_sdio_read_data_buffer_unpatched(uint32_t *args)
{
    uint8_t oid = args[0];
    uint32_t offset = args[1];
    uint8_t len = args[2];
    struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
    uint8_t *buf = &(sdio->data_buffer[offset]);

    if (offset + len > sizeof(sdio->data_buffer)) {
        len = 0;
    }
    last_sent_len = len;
    if (len > 0) {
        memcpy(last_sent_data, buf, len);
    }
}

void command_sdio_write_data_buffer_unpatched(uint32_t *args)
{
    uint8_t oid = args[0];
    uint32_t offset = args[1];
    uint8_t write_data_len = args[2];
    uint8_t *write_data = command_decode_ptr(args[3]);
    struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
    uint8_t *buf = &(sdio->data_buffer[offset]);

    if (offset + write_data_len <= sizeof(sdio->data_buffer)) {
        memcpy(buf, write_data, write_data_len);
    }
}
#endif

// Patched implementation
void command_sdio_read_data_buffer_patched(uint32_t *args)
{
    uint8_t oid = args[0];
    uint32_t offset = args[1];
    uint8_t len = args[2];
    struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
    if (!sdio) {
        last_sent_len = 0;
        return;
    }

    if (offset >= sizeof(sdio->data_buffer) ||
        len > sizeof(sdio->data_buffer) - offset) {
        len = 0;
    }
    last_sent_len = len;
    if (len > 0) {
        uint8_t *buf = &sdio->data_buffer[offset];
        memcpy(last_sent_data, buf, len);
    }
}

void command_sdio_write_data_buffer_patched(uint32_t *args)
{
    uint8_t oid = args[0];
    uint32_t offset = args[1];
    uint8_t write_data_len = args[2];
    uint8_t *write_data = command_decode_ptr(args[3]);
    struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
    if (!sdio || !write_data) {
        return;
    }

    if (offset >= sizeof(sdio->data_buffer) ||
        write_data_len > sizeof(sdio->data_buffer) - offset) {
        return;
    }
    uint8_t *buf = &sdio->data_buffer[offset];
    memcpy(buf, write_data, write_data_len);
}

int main(int argc, char **argv)
{
    printf("Starting BUG-BUF-01 SDIO data buffer security tests...\n");

    // Initialize test device
    memset(&test_sdio_dev, 0x55, sizeof(test_sdio_dev));
    test_sdio_dev.blocksize = 512;
    test_sdio_dev.speed = 400000;

    uint8_t payload[32];
    memset(payload, 0xAA, sizeof(payload));
    g_test_data_ptr = payload;

    uint32_t args[4];

#ifdef TEST_UNPATCHED
    printf("[UNPATCHED TEST] Simulating integer overflow exploit...\n");
    // Offset = 0xFFFFFFF0 (-16 mod 2^32), Len = 32
    // 0xFFFFFFF0 + 32 = 16 <= 4096 -> Bypasses bounds check!
    args[0] = 1;
    args[1] = 0xFFFFFFF0U;
    args[2] = 32;
    args[3] = (uint32_t)(uintptr_t)payload;

    // This will trigger an out-of-bounds write or AddressSanitizer crash
    command_sdio_write_data_buffer_unpatched(args);
    printf("[UNPATCHED TEST] Exploit wrote out of bounds successfully!\n");
    return 0;
#else
    printf("[PATCHED TEST] 1. Testing normal write within bounds...\n");
    args[0] = 1;
    args[1] = 100;
    args[2] = 32;
    args[3] = (uint32_t)(uintptr_t)payload;
    command_sdio_write_data_buffer_patched(args);
    assert(memcmp(&test_sdio_dev.data_buffer[100], payload, 32) == 0);
    printf("-> PASS: Normal write succeeded.\n");

    printf("[PATCHED TEST] 2. Testing normal read within bounds...\n");
    args[0] = 1;
    args[1] = 100;
    args[2] = 32;
    command_sdio_read_data_buffer_patched(args);
    assert(last_sent_len == 32);
    assert(memcmp(last_sent_data, payload, 32) == 0);
    printf("-> PASS: Normal read succeeded.\n");

    printf("[PATCHED TEST] 3. Testing buffer boundary write (offset 4080, len 16)...\n");
    args[0] = 1;
    args[1] = 4096 - 16;
    args[2] = 16;
    command_sdio_write_data_buffer_patched(args);
    assert(memcmp(&test_sdio_dev.data_buffer[4080], payload, 16) == 0);
    printf("-> PASS: Exact boundary write succeeded.\n");

    printf("[PATCHED TEST] 4. Testing buffer boundary overflow (offset 4080, len 17)...\n");
    uint8_t canary = 0x55;
    test_sdio_dev.data_buffer[4095] = canary;
    args[0] = 1;
    args[1] = 4096 - 16;
    args[2] = 17;
    command_sdio_write_data_buffer_patched(args);
    // Buffer should remain unchanged
    assert(test_sdio_dev.data_buffer[4095] == canary);
    printf("-> PASS: Boundary overflow cleanly rejected.\n");

    printf("[PATCHED TEST] 5. Testing 32-bit Integer Overflow Exploit (offset 0xFFFFFFF0, len 32)...\n");
    // Ensure canary values before data_buffer are preserved
    test_sdio_dev.speed = 0x12345678;
    test_sdio_dev.blocksize = 0x87654321;
    args[0] = 1;
    args[1] = 0xFFFFFFF0U;
    args[2] = 32;
    args[3] = (uint32_t)(uintptr_t)payload;

    command_sdio_write_data_buffer_patched(args);
    assert(test_sdio_dev.speed == 0x12345678);
    assert(test_sdio_dev.blocksize == 0x87654321);
    printf("-> PASS: Integer overflow write rejected, memory protected.\n");

    printf("[PATCHED TEST] 6. Testing 32-bit Integer Overflow Read Exploit (offset 0xFFFFFFF0, len 32)...\n");
    last_sent_len = 0xFF;
    command_sdio_read_data_buffer_patched(args);
    assert(last_sent_len == 0);
    printf("-> PASS: Integer overflow read rejected (len reset to 0).\n");

    printf("ALL TESTS PASSED SUCCESSFULLY!\n");
    return 0;
#endif
}
