#include <string.h>
#include "board/irq.h"
#include "board/misc.h"
#include "basecmd.h"
#include "command.h"
#include "sched.h"
#include "sensor_bulk.h"
#include "spicmds.h"

#define SC_AR_DATAX0            0x28
#define SC_AM_READ              0xC0
#define SC_FIFO_SRC             0x2F

#define BYTES_PER_SAMPLE        6

struct sc7a20 {
    struct timer timer;
    uint32_t rest_ticks;
    struct spidev_s *spi;
    uint8_t flags;
    struct sensor_bulk sb;
};

enum {
    SC_PENDING = 1<<0,
};

static struct task_wake sc7a20_wake;

// Event handler that wakes sc7a20_task() periodically
static uint_fast8_t
sc7a20_event(struct timer *timer)
{
    struct sc7a20 *ax = container_of(timer, struct sc7a20, timer);
    ax->flags |= SC_PENDING;
    sched_wake_task(&sc7a20_wake);
    return SF_DONE;
}

void
command_config_sc7a20(uint32_t *args)
{
    struct sc7a20 *ax = oid_alloc(args[0], command_config_sc7a20
                                   , sizeof(*ax));
    ax->timer.func = sc7a20_event;
    ax->spi = spidev_oid_lookup(args[1]);
}
DECL_COMMAND(command_config_sc7a20, "config_sc7a20 oid=%c spi_oid=%c");

// Helper code to reschedule the sc7a20_event() timer
static void
sc7a20_reschedule_timer(struct sc7a20 *ax)
{
    irq_disable();
    ax->timer.waketime = timer_read_time() + ax->rest_ticks;
    sched_add_timer(&ax->timer);
    irq_enable();
}

// Query accelerometer data — check FIFO_SRC first, then read if data available
// static void
// sc7a20_query(struct sc7a20 *ax, uint8_t oid)
// {
//     uint8_t fifo[2] = {SC_FIFO_SRC | SC_AM_READ, 0};
//     spidev_transfer(ax->spi, 1, sizeof(fifo), fifo);
//     uint8_t fifo_count = fifo[1] & 0x1F;
//     uint8_t fifo_ovrn = fifo[1] & 0x40;

//     if (!fifo_count) {
//         // FIFO empty — sleep until next check time
//         if (fifo_ovrn)
//             ax->sb.possible_overflows++;
//         ax->flags &= ~SC_PENDING;
//         sc7a20_reschedule_timer(ax);
//         return;
//     }

//     uint8_t msg[7] = {SC_AR_DATAX0 | SC_AM_READ};
//     spidev_transfer(ax->spi, 1, sizeof(msg), msg);

//     uint8_t *d = &ax->sb.data[ax->sb.data_count];
//     d[0] = msg[1]; // x low bits
//     d[1] = msg[2]; // x high bits
//     d[2] = msg[3]; // y low bits
//     d[3] = msg[4]; // y high bits
//     d[4] = msg[5]; // z low bits
//     d[5] = msg[6]; // z high bits

//     ax->sb.data_count += BYTES_PER_SAMPLE;
//     if (ax->sb.data_count + BYTES_PER_SAMPLE > ARRAY_SIZE(ax->sb.data))
//         sensor_bulk_report(&ax->sb, oid);

//     if (fifo_ovrn)
//         ax->sb.possible_overflows++;

//     if (fifo_count > 1) {
//         // More samples in FIFO — wake again to drain
//         sched_wake_task(&sc7a20_wake);
//     } else {
//         ax->flags &= ~SC_PENDING;
//         sc7a20_reschedule_timer(ax);
//     }
// }


// Query accelerometer data
static void
sc7a20_query(struct sc7a20 *ax, uint8_t oid)
{
    uint8_t *d = &ax->sb.data[ax->sb.data_count];
    uint8_t raw_data[7] = {0};
    uint8_t reg_status[2] = {0};
    static uint16_t cnt = 0;

    reg_status[0] = 0x27 | 0x80;
    spidev_transfer(ax->spi, 1, sizeof(reg_status), reg_status);
    cnt++;
    if ((reg_status[1] & 0x0F) != 0x0F && cnt < 10000) {
        sched_wake_task(&sc7a20_wake);
        return;
    }
    cnt = 0;

    raw_data[0] = SC_AR_DATAX0 | SC_AM_READ;
    spidev_transfer(ax->spi, 1, sizeof(raw_data), raw_data);


    d[0] = raw_data[1]; // x low bits
    d[1] = raw_data[2]; // x high bits
    d[2] = raw_data[3]; // y low bits
    d[3] = raw_data[4]; // y high bits
    d[4] = raw_data[5]; // z low bits
    d[5] = raw_data[6]; // z high bits

    ax->sb.data_count += BYTES_PER_SAMPLE;
    if (ax->sb.data_count + BYTES_PER_SAMPLE > ARRAY_SIZE(ax->sb.data))
        sensor_bulk_report(&ax->sb, oid);

    // Sleep until next check time
    ax->flags &= ~SC_PENDING;
    sc7a20_reschedule_timer(ax);
}

void
command_query_sc7a20(uint32_t *args)
{
    struct sc7a20 *ax = oid_lookup(args[0], command_config_sc7a20);

    sched_del_timer(&ax->timer);
    ax->flags = 0;
    if (!args[1])
        // End measurements
        return;

    // Start new measurements query
    ax->rest_ticks = args[1];
    sensor_bulk_reset(&ax->sb);
    sc7a20_reschedule_timer(ax);
}
DECL_COMMAND(command_query_sc7a20, "query_sc7a20 oid=%c rest_ticks=%u");

void
command_query_sc7a20_status(uint32_t *args)
{
    struct sc7a20 *ax = oid_lookup(args[0], command_config_sc7a20);
    uint8_t msg[2] = { SC_FIFO_SRC | SC_AM_READ, 0x00 };
    uint32_t time1 = timer_read_time();
    spidev_transfer(ax->spi, 1, sizeof(msg), msg);
    uint32_t time2 = timer_read_time();
    sensor_bulk_status(&ax->sb, args[0], time1, time2-time1
                       , (msg[1] & 0x1f) * BYTES_PER_SAMPLE);
}
DECL_COMMAND(command_query_sc7a20_status, "query_sc7a20_status oid=%c");

void
sc7a20_task(void)
{
    if (!sched_check_wake(&sc7a20_wake))
        return;
    uint8_t oid;
    struct sc7a20 *ax;
    foreach_oid(oid, ax, command_config_sc7a20) {
        uint_fast8_t flags = ax->flags;
        if (flags & SC_PENDING)
            sc7a20_query(ax, oid);
    }
}
DECL_TASK(sc7a20_task);
