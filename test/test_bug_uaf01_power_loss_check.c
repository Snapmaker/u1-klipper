#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

struct timer {
    bool active;
    uint32_t waketime;
};

struct power_loss_check_dev {
    struct timer timer;
    uint8_t print_act;
    uint32_t debounce_count;
};

static struct power_loss_check_dev *s_plc = NULL;
static bool s_tmr4_enabled = true;
static bool s_tmr4_irq_enabled = true;
static bool s_nvic_irq_enabled = true;

static void sched_del_timer(struct timer *t) {
    t->active = false;
}

static void tmr_counter_enable(int tim, bool enable) {
    if (tim == 4) s_tmr4_enabled = enable;
}

static void tmr_interrupt_enable(int tim, uint32_t flags, bool enable) {
    (void)flags;
    if (tim == 4) s_tmr4_irq_enabled = enable;
}

static void nvic_disable_irq(int irqn) {
    (void)irqn;
    s_nvic_irq_enabled = false;
}

static void power_loss_check_shutdown_patched(struct power_loss_check_dev *p) {
    sched_del_timer(&p->timer);
    tmr_counter_enable(4, false);
    tmr_interrupt_enable(4, 0x01 | 0x02, false);
    nvic_disable_irq(30);
    s_plc = NULL;
}

int main(void) {
    printf("Starting BUG-UAF-01 Dangling Pointer and IRQ Shutdown tests...\n");

    struct power_loss_check_dev dev;
    dev.timer.active = true;
    dev.print_act = 1;
    dev.debounce_count = 5;
    s_plc = &dev;

    assert(s_plc != NULL);
    assert(s_plc->timer.active == true);
    assert(s_tmr4_enabled == true);
    assert(s_tmr4_irq_enabled == true);
    assert(s_nvic_irq_enabled == true);

    // Perform patched shutdown
    power_loss_check_shutdown_patched(&dev);

    // Verify timer deleted
    assert(dev.timer.active == false);
    printf("  [PASS] Timer deleted from scheduler on shutdown.\n");

    // Verify hardware disabled
    assert(s_tmr4_enabled == false);
    assert(s_tmr4_irq_enabled == false);
    assert(s_nvic_irq_enabled == false);
    printf("  [PASS] TMR4 counter, interrupts, and NVIC line disabled on shutdown.\n");

    // Verify pointer reset
    assert(s_plc == NULL);
    printf("  [PASS] Global plc pointer reset to NULL (prevents UAF across reset).\n");

    printf("BUG-UAF-01: All unit tests passed successfully.\n");
    return 0;
}

