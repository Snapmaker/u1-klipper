// Test harness for BUG-NULL-02: Null pointer dereference in sdiocmds.c
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>

struct sdio_hw {
    uint32_t cr;
};

struct sdio_config {
    struct sdio_hw *sdio;
};

struct sdiodev_s {
    struct sdio_config sdio_config;
    uint32_t blocksize;
    uint32_t speed;
    uint8_t data_buffer[4096];
};

static struct sdiodev_s test_sdio_dev;
static uint8_t last_error = 0;
static uint32_t last_transferred = 0;

struct sdiodev_s *sdiodev_oid_lookup(uint8_t oid)
{
    if (oid == 0) {
        return NULL; // Invalid OID test
    }
    return &test_sdio_dev;
}

void sdio_set_speed(struct sdio_config config, uint32_t speed)
{
    // Dereferences config.sdio to set hardware speed register
    config.sdio->cr = speed;
}

uint8_t sdio_send_command(struct sdio_config config, uint8_t cmd,
                          uint32_t arg, uint8_t wait,
                          uint8_t *resp, uint8_t *resp_len)
{
    // Dereferences config.sdio
    return (uint8_t)(config.sdio->cr & 0xFF);
}

uint8_t sdio_prepare_data_transfer(struct sdio_config config, uint8_t read,
                                   uint8_t blocks, uint32_t blocksize,
                                   uint32_t timeout)
{
    // Dereferences config.sdio
    return (uint8_t)(config.sdio->cr & 0xFF);
}

void sendf(const char *fmt, ...)
{
    (void)fmt;
}

#ifdef TEST_UNPATCHED
void command_sdio_set_speed_unpatched(uint32_t *args)
{
    struct sdiodev_s *sdio = sdiodev_oid_lookup(args[0]);
    sdio->speed = args[1];
    sdio_set_speed(sdio->sdio_config, sdio->speed);
}
#endif

// Patched functions with NULL checks
void command_sdio_set_speed_patched(uint32_t *args)
{
    struct sdiodev_s *sdio = sdiodev_oid_lookup(args[0]);
    if (!sdio || !sdio->sdio_config.sdio) {
        return;
    }
    sdio->speed = args[1];
    sdio_set_speed(sdio->sdio_config, sdio->speed);
}

void command_sdio_send_command_patched(uint32_t *args)
{
    uint8_t oid = args[0];
    uint8_t cmd = args[1];
    uint32_t argument = args[2];
    uint8_t wait = args[3];
    struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
    if (!sdio || !sdio->sdio_config.sdio) {
        last_error = 1;
        return;
    }
    uint8_t response[16];
    uint8_t response_len = 0;
    last_error = sdio_send_command(sdio->sdio_config, cmd, argument, wait,
                                   response, &response_len);
}

void command_sdio_read_data_patched(uint32_t *args)
{
    uint8_t oid = args[0];
    struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
    if (!sdio || !sdio->sdio_config.sdio) {
        last_error = 1;
        last_transferred = 0;
        return;
    }
}

int main(int argc, char **argv)
{
    printf("Starting BUG-NULL-02 SDIO null pointer dereference tests...\n");

    // Initialize test device without calling sdio_set_bus (sdio_config.sdio remains NULL)
    memset(&test_sdio_dev, 0, sizeof(test_sdio_dev));
    test_sdio_dev.blocksize = 512;
    test_sdio_dev.speed = 400000;
    test_sdio_dev.sdio_config.sdio = NULL;

    uint32_t args[4];

#ifdef TEST_UNPATCHED
    printf("[UNPATCHED TEST] Invoking sdio_set_speed before sdio_set_bus...\n");
    args[0] = 1;
    args[1] = 25000000;
    command_sdio_set_speed_unpatched(args);
    return 0;
#else
    printf("[PATCHED TEST] 1. Testing sdio_set_speed before sdio_set_bus (NULL hw pointer)...\n");
    args[0] = 1;
    args[1] = 25000000;
    command_sdio_set_speed_patched(args);
    printf("-> PASS: Ignored call on uninitialized bus without crash.\n");

    printf("[PATCHED TEST] 2. Testing sdio_send_command on uninitialized bus...\n");
    last_error = 0;
    command_sdio_send_command_patched(args);
    assert(last_error == 1);
    printf("-> PASS: Correctly returned error code without crash.\n");

    printf("[PATCHED TEST] 3. Testing invalid OID (lookup returns NULL)...\n");
    args[0] = 0; // lookup returns NULL
    command_sdio_set_speed_patched(args);
    command_sdio_send_command_patched(args);
    printf("-> PASS: Invalid OID handled safely.\n");

    printf("[PATCHED TEST] 4. Testing after successful bus initialization...\n");
    struct sdio_hw mock_hw = {0};
    test_sdio_dev.sdio_config.sdio = &mock_hw;
    args[0] = 1;
    args[1] = 25000000;
    command_sdio_set_speed_patched(args);
    assert(mock_hw.cr == 25000000);
    printf("-> PASS: Initialized bus operates normally.\n");

    printf("ALL BUG-NULL-02 TESTS PASSED SUCCESSFULLY!\n");
    return 0;
#endif
}

