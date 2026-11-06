// Unit test for BUG-DEAD-01: Hardware polling loop timeouts in SDIO driver
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>

#define SDIO_OK 0
#define SDIO_DATA_TIMEOUT 7
#define SDIO_NO_DATA_MEMORY 10

#define SDIO_STA_RXOVERR  (1U << 5)
#define SDIO_STA_DCRCFAIL (1U << 1)
#define SDIO_STA_DTIMEOUT (1U << 3)
#define SDIO_STA_DATAEND  (1U << 8)
#define SDIO_STA_RXDAVL   (1U << 21)
#define SDIO_STA_TXUNDERR (1U << 4)
#define SDIO_STA_TXFIFOF  (1U << 14)
#define SDIO_STATIC_FLAGS 0x000005FFU

typedef struct {
    volatile uint32_t STA;
    volatile uint32_t ICR;
    volatile uint32_t FIFO;
} MockSDIO;

static uint8_t mock_sdio_read_data(MockSDIO *sdio, uint8_t *data,
                                   uint32_t numblocks, uint32_t blocksize)
{
    uint32_t data_remaining = numblocks * blocksize;
    uint8_t *buf = data;

    if (data == NULL) {
        return SDIO_NO_DATA_MEMORY;
    }

    uint32_t count = 1000;
    while ((sdio->STA & (SDIO_STA_RXOVERR | SDIO_STA_DCRCFAIL |
        SDIO_STA_DTIMEOUT | SDIO_STA_DATAEND)) == 0) {
        if (count-- == 0) {
            sdio->ICR = SDIO_STATIC_FLAGS;
            return SDIO_DATA_TIMEOUT;
        }
        if ((sdio->STA & SDIO_STA_RXDAVL) != 0) {
            uint32_t tmp = sdio->FIFO;
            for (uint8_t i = 0; (i < 4) && (data_remaining > 0); i++) {
                *buf = (uint8_t)(tmp & 0xFF);
                buf++;
                data_remaining--;
                tmp >>= 8U;
            }
        }
    }

    uint32_t sta = sdio->STA;
    sdio->ICR = SDIO_STATIC_FLAGS;

    if (sta & SDIO_STA_DTIMEOUT) {
        return SDIO_DATA_TIMEOUT;
    }

    return SDIO_OK;
}

static uint8_t mock_sdio_write_data(MockSDIO *sdio, uint8_t *data,
                                    uint32_t numblocks, uint32_t blocksize)
{
    uint32_t data_remaining = numblocks * blocksize;
    uint8_t *buf = data;

    if (data == NULL) {
        return SDIO_NO_DATA_MEMORY;
    }

    uint32_t count = 1000;
    while ((sdio->STA & (SDIO_STA_TXUNDERR | SDIO_STA_DCRCFAIL |
        SDIO_STA_DTIMEOUT | SDIO_STA_DATAEND)) == 0) {
        if (count-- == 0) {
            sdio->ICR = SDIO_STATIC_FLAGS;
            return SDIO_DATA_TIMEOUT;
        }
        if ((sdio->STA & SDIO_STA_TXFIFOF) == 0) {
            uint32_t tmp = 0;
            for (uint8_t i = 0; (i < 4) && (data_remaining > 0); i++) {
                tmp |= ((uint32_t)(*buf) << (i << 3));
                buf++;
                data_remaining--;
            }
            sdio->FIFO = tmp;
        }
    }

    uint32_t sta = sdio->STA;
    sdio->ICR = SDIO_STATIC_FLAGS;

    if (sta & SDIO_STA_DTIMEOUT) {
        return SDIO_DATA_TIMEOUT;
    }

    return SDIO_OK;
}

int main(void)
{
    MockSDIO sdio;
    memset(&sdio, 0, sizeof(sdio));
    uint8_t buffer[512];
    memset(buffer, 0xAA, sizeof(buffer));

    // Test 1: sdio_read_data with hanging hardware flags (STA remains 0)
    sdio.STA = 0;
    uint8_t res = mock_sdio_read_data(&sdio, buffer, 1, 512);
    assert(res == SDIO_DATA_TIMEOUT);
    assert(sdio.ICR == SDIO_STATIC_FLAGS);
    printf("Test 1 (read timeout): PASSED\n");

    // Test 2: sdio_write_data with hanging hardware flags (STA remains 0)
    sdio.STA = 0;
    sdio.ICR = 0;
    res = mock_sdio_write_data(&sdio, buffer, 1, 512);
    assert(res == SDIO_DATA_TIMEOUT);
    assert(sdio.ICR == SDIO_STATIC_FLAGS);
    printf("Test 2 (write timeout): PASSED\n");

    // Test 3: Normal completion (STA asserts DATAEND)
    sdio.STA = SDIO_STA_DATAEND;
    sdio.ICR = 0;
    res = mock_sdio_read_data(&sdio, buffer, 1, 512);
    assert(res == SDIO_OK);
    printf("Test 3 (normal read): PASSED\n");

    printf("ALL DEAD-01 SDIO UNIT TESTS PASSED!\n");
    return 0;
}

