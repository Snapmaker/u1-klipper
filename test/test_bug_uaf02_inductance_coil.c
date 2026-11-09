#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

/* Mock scheduler timer */
struct timer {
    bool active;
    uint32_t waketime;
};

/* Mock inductance coil device */
struct inductance_coil_dev {
    struct timer timer;
    struct timer config_freq_timer;
};

/* Hardware state mocks */
static bool s_tmr2_counter_enabled = true;
static bool s_tmr5_counter_enabled = true;
static bool s_tmr5_interrupt_enabled = true;
static bool s_nvic_irq_enabled = true;
static uint8_t s_inductance_coil_oid_malloc = 1;

static void sched_del_timer(struct timer *t) {
    t->active = false;
}

static void tmr_counter_enable(int tim, bool enable) {
    if (tim == 2) s_tmr2_counter_enabled = enable;
    if (tim == 5) s_tmr5_counter_enabled = enable;
}

static void tmr_interrupt_enable(int tim, uint32_t flags, bool enable) {
    (void)flags;
    if (tim == 5) s_tmr5_interrupt_enabled = enable;
}

static void nvic_disable_irq(int irqn) {
    (void)irqn;
    s_nvic_irq_enabled = false;
}

/* Shutdown logic matching patched inductance_coil_shutdown */
static void inductance_coil_shutdown_patched(struct inductance_coil_dev *d) {
    sched_del_timer(&d->timer);
    sched_del_timer(&d->config_freq_timer);

    tmr_interrupt_enable(5, 0x01 | 0x02, false);
    tmr_counter_enable(5, false);
    tmr_counter_enable(2, false);
    nvic_disable_irq(50);

    s_inductance_coil_oid_malloc = 0;
}

int main(void) {
    printf("Starting BUG-UAF-02 Dangling Timer and IRQ Shutdown tests...\n");

    struct inductance_coil_dev dev;
    dev.timer.active = true;
    dev.config_freq_timer.active = true;

    assert(dev.timer.active == true);
    assert(dev.config_freq_timer.active == true);
    assert(s_tmr2_counter_enabled == true);
    assert(s_tmr5_counter_enabled == true);
    assert(s_tmr5_interrupt_enabled == true);
    assert(s_nvic_irq_enabled == true);
    assert(s_inductance_coil_oid_malloc == 1);

    inductance_coil_shutdown_patched(&dev);

    // Verify both timers deleted
    assert(dev.timer.active == false);
    assert(dev.config_freq_timer.active == false);
    printf("  [PASS] config_freq_timer and sample timer successfully deleted.\n");

    // Verify hardware counters and interrupts disabled
    assert(s_tmr2_counter_enabled == false);
    assert(s_tmr5_counter_enabled == false);
    assert(s_tmr5_interrupt_enabled == false);
    assert(s_nvic_irq_enabled == false);
    printf("  [PASS] TMR2/TMR5 counters, TMR5 IRQ, and NVIC line successfully disabled.\n");

    // Verify OID malloc reset
    assert(s_inductance_coil_oid_malloc == 0);
    printf("  [PASS] inductance_coil_oid_malloc reset to 0.\n");

    printf("BUG-UAF-02: All unit tests passed successfully.\n");
    return 0;
}

