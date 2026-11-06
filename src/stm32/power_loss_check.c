#include <string.h> // ffs
#include "board/irq.h" // irq_save
#include "board/misc.h"
#include "board/armcm_boot.h" // armcm_enable_irq
#include "command.h" // DECL_ENUMERATION_RANGE
#include "basecmd.h" // oid_alloc
#include "sched.h" // sched_shutdown
#include "autoconf.h" // CONFIG_CLOCK_FREQ
#include "stepper.h" // get_all_stepper_info

#if CONFIG_MACH_AT32F4x
// currently it only works with the AT32F415 chip from artery.
  #if CONFIG_MACH_AT32F415
    #include "at32f415_crm.h"
    #include "at32f415_tmr.h"
    #define FLASH_SECTOR_SIZE                        1024
    #define RECORD_FLASH_SECTOR_ADDR1                0x0801F800
    #define RECORD_FLASH_SECTOR_ADDR2                0x0801FC00
    #define DETECTION_GPIO                           GPIOB
    #define DETECTION_GPIO_PIN                       GPIO_PINS_8
  #elif CONFIG_MACH_AT32F403A
    #include "at32f403a.h"
    #include "at32f403a_407_crm.h"
    #include "at32f403a_407_tmr.h"
    #define FLASH_SECTOR_SIZE                        2048
    #define RECORD_FLASH_SECTOR_ADDR1                0x080FF000
    #define RECORD_FLASH_SECTOR_ADDR2                0x080FF800
    #define DETECTION_GPIO                           GPIOB
    #define DETECTION_GPIO_PIN                       GPIO_PINS_7
  #endif

#define TRM_OVER_FREQ          10000
#define TRM_PR_DIV_VALUE       (uint16_t)(CONFIG_CLOCK_FREQ / TRM_OVER_FREQ - 1)
#define UNIT16_COUNT(var)      ((size_t)(sizeof(var) / sizeof(uint16_t)))

#define MAX_ALLOW_SAVE_STEPPER_NUM               16            // Number of supported steppers
#define ENV_VALID_FLAG                           (0x12345678)
#define ENV_VALID_FLAG_OFFSET                    (0)
#define ENV_CHECK_SUM_OFFSET                     (4)
#define ENV_SEQ_NUM_OFFSET                       (8)
#define ENV_POWER_LOSS_DATA_OFFSET               (12)

struct power_loss_check_dev {
    struct timer timer;
    uint8_t report_state;
    uint8_t need_save;
    uint8_t print_act;
    uint8_t voltage_type; // Voltage type: 0-Type1, 1-Type2, 0xFF-Uninitialized
    uint32_t print_mark;
    uint32_t report_interval;  // Report interval (microseconds)
    volatile uint32_t high_level_tick;    // High level tick value (0xFFFFFFFF means not read)
    volatile uint32_t low_level_tick;     // Low level tick value (0xFFFFFFFF means not read)
    double duty_cycle_threshold; // Duty cycle threshold (0.0-1.0)
    double power_loss_trigger_time;
    uint32_t debounce_count;      // Debounce counter
    uint32_t debounce_threshold;  // Debounce threshold
    volatile uint8_t power_loss_flag;      // Power loss flag: 0-Normal, 1-Power loss
    uint32_t voltage_type_count;  // Continuous recognition counter
    uint32_t type_confirm_threshold; // Continuous recognition threshold (default 3)
};

struct __attribute__((aligned(2))) power_loss_env {
    uint32_t flag;
    uint16_t step_info_num;
    struct stepper_info step_info_arry[MAX_ALLOW_SAVE_STEPPER_NUM];
};

typedef struct {
    uint32_t addr;
    uint32_t seq_num;  // Sequence number instead of timestamp
    uint8_t valid;
    uint8_t is_init;
} SectorInfo;

SectorInfo sectors[2] = {
    {RECORD_FLASH_SECTOR_ADDR1, 0, 0, 0},
    {RECORD_FLASH_SECTOR_ADDR2, 0, 0, 0}
};

static uint8_t power_loss_saved = 0;
static uint8_t save_sector_id = 0;
static uint32_t save_seq_num = 0;
static uint32_t last_seq_num = 0;
static uint32_t valid_count = 0;
static struct power_loss_check_dev *plc = NULL;
static struct task_wake power_loss_wake;
static struct power_loss_env env;
static struct power_loss_env tmp_env;
uint16_t flash_buf[FLASH_SECTOR_SIZE / 2];

void power_loss_rotate_sector(void);

/**
  * @brief  read data using halfword mode
  * @param  read_addr: the address of reading
  * @param  p_buffer: the buffer of reading data
  * @param  num_read: the number of reading data
  * @retval none
  */
void flash_read(uint32_t read_addr, uint8_t *p_buffer, uint32_t num_read)
{
    uint32_t i;
    for(i = 0; i < num_read; i++)
    {
        ((uint8_t *)p_buffer)[i] = *((uint8_t*)read_addr);
        read_addr += 1;
    }
}

/**
  * @brief  write data using halfword mode without checking
  * @param  write_addr: the address of writing
  * @param  p_buffer: the buffer of writing data
  * @param  num_write: the number of writing data
  * @retval result
  */
error_status flash_write_nocheck(uint32_t write_addr, uint16_t *p_buffer, uint16_t num_write)
{
    uint16_t i;
    flash_status_type status = FLASH_OPERATE_DONE;
    for(i = 0; i < num_write; i++)
    {
        status = flash_halfword_program(write_addr, p_buffer[i]);
        if(status != FLASH_OPERATE_DONE)
            return ERROR;
        write_addr += 2;
    }
    return SUCCESS;
}

  /**
    * @brief  write data using halfword mode with checking
    * @param  write_addr: the address of writing
    * @param  p_buffer: the buffer of writing data
    * @param  num_write: the number of writing data
    * @retval result
    */
error_status flash_write(uint32_t write_addr, uint16_t *p_buffer, uint16_t num_write)
{
    uint32_t offset_addr;
    uint32_t sector_position;
    uint16_t sector_offset;
    uint16_t sector_remain;
    uint16_t i;
    flash_status_type status = FLASH_OPERATE_DONE;
    flash_unlock();
    offset_addr = write_addr - FLASH_BASE;
    sector_position = offset_addr / FLASH_SECTOR_SIZE;
    sector_offset = (offset_addr % FLASH_SECTOR_SIZE) / 2;
    sector_remain = FLASH_SECTOR_SIZE / 2 - sector_offset;
    if(num_write <= sector_remain)
        sector_remain = num_write;
    while(1)
    {
        flash_read(sector_position * FLASH_SECTOR_SIZE + FLASH_BASE, (uint8_t *)flash_buf, FLASH_SECTOR_SIZE);
        for(i = 0; i < sector_remain; i++)
        {
            if(flash_buf[sector_offset + i] != 0xFFFF)
                break;
        }

        if(i < sector_remain)
        {
            /* wait for operation to be completed */
            status = flash_operation_wait_for(ERASE_TIMEOUT);
            if((status == FLASH_PROGRAM_ERROR) || (status == FLASH_EPP_ERROR))
                flash_flag_clear(FLASH_PRGMERR_FLAG | FLASH_EPPERR_FLAG);
            else if(status == FLASH_OPERATE_TIMEOUT)
                goto err_exit;
            status = flash_sector_erase(sector_position * FLASH_SECTOR_SIZE + FLASH_BASE);
            if(status != FLASH_OPERATE_DONE)
                goto err_exit;
            for(i = 0; i < sector_remain; i++)
            {
                flash_buf[i + sector_offset] = p_buffer[i];
            }
            if(flash_write_nocheck(sector_position * FLASH_SECTOR_SIZE + FLASH_BASE, flash_buf, FLASH_SECTOR_SIZE / 2) != SUCCESS)
                goto err_exit;
        }
        else
        {
            if(flash_write_nocheck(write_addr, p_buffer, sector_remain) != SUCCESS)
                goto err_exit;
        }

        if(num_write == sector_remain)
            break;
        else
        {
            sector_position++;
            sector_offset = 0;
            p_buffer += sector_remain;
            write_addr += (sector_remain * 2);
            num_write -= sector_remain;
            if(num_write > (FLASH_SECTOR_SIZE / 2))
            sector_remain = FLASH_SECTOR_SIZE / 2;
            else
            sector_remain = num_write;
        }
    }
    flash_lock();
    return SUCCESS;

err_exit:
    flash_lock();
    return ERROR;
  }

void flash_sector_erase_ex(uint32_t sector_address) {
    flash_unlock();
    flash_sector_erase(sector_address);
    flash_lock();
}

uint16_t cal_checksum(const void* data, uint32_t len) {
    const uint8_t* addr = (const uint8_t*)data;
    uint32_t sum = 0;

    while (len > 1) {
        sum += (addr[0] << 8) | addr[1];
        addr += 2;
        len -= 2;
    }

    if (len == 1) {
        sum += (uint16_t)(*(const uint8_t*)addr) << 8;
    }

    sum = (sum >> 16) + (sum & 0xFFFF);
    sum += (sum >> 16);

    return (uint16_t)~sum;
}

uint8_t is_all_value(const uint8_t* data, uint8_t value, size_t len) {
    const uint8_t* end = data + len;
    while (data < end) {
        if (*data++ != value)
            return 0xFF;
    }
    return 0;
}

void power_loss_rotate_sector(void)
{
    if (plc) {
        uint32_t checksum = 0;
        uint16_t step_num = 0;
        memset((uint8_t*)flash_buf, 0, FLASH_SECTOR_SIZE);
        // *((uint8_t*)flash_buf + ENV_SEQ_NUM_OFFFSET) = save_seq_num;
        memcpy((uint8_t*)flash_buf + ENV_SEQ_NUM_OFFSET, &save_seq_num, sizeof(uint32_t));
        step_num = get_all_stepper_info(env.step_info_arry, MAX_ALLOW_SAVE_STEPPER_NUM, 1);
        env.flag = plc->print_mark;
        env.step_info_num = step_num;
        memcpy(((uint8_t*)flash_buf)+ENV_POWER_LOSS_DATA_OFFSET, &env, sizeof(env));
        checksum = cal_checksum(((uint8_t*)flash_buf)+ENV_SEQ_NUM_OFFSET, sizeof(env)+4);
        flash_write(sectors[save_sector_id].addr + ENV_CHECK_SUM_OFFSET, (uint16_t*)&checksum, UNIT16_COUNT(checksum));
        flash_write(sectors[save_sector_id].addr + ENV_SEQ_NUM_OFFSET, (uint16_t*)&save_seq_num, UNIT16_COUNT(save_seq_num));
        flash_write(sectors[save_sector_id].addr + ENV_POWER_LOSS_DATA_OFFSET, (uint16_t*)&env, UNIT16_COUNT(env));
    }
}

void load_save_flash_info(void)
{
    uint32_t checksum = 0;
    uint32_t read_check_sum = 0;
    uint32_t seq = 0;
    uint32_t env_valid_flag = ENV_VALID_FLAG;

    for (int i = 0; i < 2; i++) {
        memset((uint8_t*)flash_buf, 0, FLASH_SECTOR_SIZE);
        flash_read(sectors[i].addr, (uint8_t*)flash_buf, FLASH_SECTOR_SIZE);
        if (*((uint32_t*)flash_buf) == ENV_VALID_FLAG) {
            if (is_all_value(((uint8_t*)flash_buf)+ENV_CHECK_SUM_OFFSET, 0xFF, sizeof(struct power_loss_env)+8) == 0) {
                sectors[i].is_init = 1;
            }
            else {
                read_check_sum = *(((uint32_t*)flash_buf) + 1);
                checksum = cal_checksum(((uint8_t*)flash_buf)+ENV_SEQ_NUM_OFFSET, sizeof(struct power_loss_env)+4);
                seq = *(((uint32_t*)flash_buf) + 2);
                if (read_check_sum == checksum) {
                    if (seq != 0xFFFFFFFF && seq != 0x0) {
                        sectors[i].valid = 1;
                        sectors[i].seq_num = seq;
                        valid_count++;
                    }
                }
            }
        }
    }

    if (valid_count == 2) {
        // Special index handling
        if ((sectors[0].seq_num == 1 && sectors[1].seq_num == 0xFFFFFFFE) || ((sectors[0].seq_num == 0xFFFFFFFE && sectors[1].seq_num == 1))) {
            save_sector_id = (sectors[0].seq_num == 1) ? 1 : 0;
            last_seq_num = 1;
        }
        else {
            save_sector_id = (sectors[0].seq_num < sectors[1].seq_num) ? 0 : 1;
            last_seq_num = (sectors[0].seq_num < sectors[1].seq_num) ? (sectors[1].seq_num) : (sectors[0].seq_num);
        }
        save_seq_num = last_seq_num + 1;
        if (save_seq_num == 0xFFFFFFFF || save_seq_num == 0)
            save_seq_num = 1;
        if (!sectors[save_sector_id].is_init) {
            flash_sector_erase_ex(sectors[save_sector_id].addr);
            flash_write(sectors[save_sector_id].addr, (uint16_t*)&env_valid_flag, UNIT16_COUNT(env_valid_flag));
        }
    }
    else if (valid_count == 1) {
        save_sector_id = sectors[0].valid ? 1 : 0;
        last_seq_num = sectors[!save_sector_id].seq_num;
        save_seq_num = last_seq_num + 1;
        if (save_seq_num == 0xFFFFFFFF || save_seq_num == 0)
            save_seq_num = 1;
        if (!sectors[save_sector_id].is_init) {
            flash_sector_erase_ex(sectors[save_sector_id].addr);
            flash_write(sectors[save_sector_id].addr, (uint16_t*)&env_valid_flag, UNIT16_COUNT(env_valid_flag));
        }
    }
    else {
        for (int i = 0; i < 2; i++) {
            if (!sectors[i].is_init) {
                flash_sector_erase_ex(sectors[i].addr);
                flash_write(sectors[i].addr, (uint16_t*)&env_valid_flag, UNIT16_COUNT(env_valid_flag));
            }
        }
        save_sector_id = 0;
        save_seq_num = 1;
    }
    memset((uint8_t*)(&env), 0, sizeof(env));
    if (valid_count) {
        uint8_t last_valid_sector = save_sector_id ? 0: 1;
        flash_read(sectors[last_valid_sector].addr+ENV_POWER_LOSS_DATA_OFFSET, (uint8_t*)(&env), sizeof(env));
    }
}

void
trigger_power_loss_gpio_set(void)
{
    #if CONFIG_MACH_AT32F403A
        GPIOC->scr = GPIO_PINS_8;
        GPIOC->scr = GPIO_PINS_9;
        GPIOD->clr = GPIO_PINS_4;
        GPIOD->clr = GPIO_PINS_5;
        GPIOD->clr = GPIO_PINS_6;
        GPIOD->clr = GPIO_PINS_7;
        GPIOE->clr = GPIO_PINS_15;
    #else
        GPIOB->clr = GPIO_PINS_3;
        GPIOB->scr = GPIO_PINS_0;
        GPIOB->scr = GPIO_PINS_7;
    #endif
}

void
#if CONFIG_MACH_AT32F403A
TIM4_IRQHandler(void)
{
    uint32_t ists = TMR4->ists;
    if (plc) {
        if (plc->debounce_count >= plc->debounce_threshold) {
            if (ists & TMR_C2_FLAG) {
                const uint32_t current_tick = TMR4->cval;
                const uint8_t current_level = gpio_input_data_bit_read(DETECTION_GPIO, DETECTION_GPIO_PIN);
                if (current_level) {
                    plc->low_level_tick = current_tick;
                    if (plc->high_level_tick != 0xFFFFFFFF) {
                        uint32_t period = plc->high_level_tick + plc->low_level_tick;
                        uint32_t threshold_tick = (uint32_t)(period * plc->duty_cycle_threshold);
                        uint8_t new_type = (plc->high_level_tick > threshold_tick) ? 1 : 0;

                        if (plc->voltage_type == new_type) {
                            plc->voltage_type_count++;
                        } else {
                            plc->voltage_type_count = 0;
                            plc->voltage_type = new_type;
                        }

                        if (plc->voltage_type_count >= plc->type_confirm_threshold) {
                            plc->voltage_type = new_type;
                        }
                    }
                } else {
                    plc->high_level_tick = current_tick;
                }
            }

            if (ists & TMR_OVF_FLAG) {
                if (plc->power_loss_flag != 1 && plc->print_act && !power_loss_saved) {
                    GPIOA->scr = GPIO_PINS_15;
                    plc->need_save = 1;
                    plc->power_loss_flag = 1;
                    sched_wake_task(&power_loss_wake);
                }
            }

            if (plc->power_loss_flag == 1) {
                trigger_power_loss_gpio_set();
            }
        }
        else {
            plc->debounce_count++;
            plc->power_loss_flag = 0;
        }
    }

    if (ists & (TMR_C2_FLAG | TMR_OVF_FLAG)) {
        TMR4->ists = ~(ists & (TMR_C2_FLAG | TMR_OVF_FLAG));
        TMR4->cval = 0;
    }
}
#else
TIM4_IRQHandler(void)
{
    uint32_t ists = TMR4->ists;
    if (plc) {
        if (plc->debounce_count >= plc->debounce_threshold) {
            if (ists & TMR_OVF_FLAG) {
                const uint8_t current_level = gpio_input_data_bit_read(DETECTION_GPIO, DETECTION_GPIO_PIN);
                if (current_level) {
                    plc->voltage_type_count++;
                    if (plc->voltage_type_count >= plc->type_confirm_threshold) {
                        if (plc->power_loss_flag != 1 && plc->print_act && !power_loss_saved) {
                            plc->need_save = 1;
                            plc->power_loss_flag = 1;
                            sched_wake_task(&power_loss_wake);
                        }
                    }
                } else {
                    plc->voltage_type_count = 0;
                }
            }

            if (plc->power_loss_flag == 1) {
                trigger_power_loss_gpio_set();
            }
        }
        else {
            plc->debounce_count++;
            plc->power_loss_flag = 0;
            plc->voltage_type_count = 0;
        }
    }
    TMR4->ists = ~TMR_OVF_FLAG;
    TMR4->cval = 0;
}
#endif

static uint_fast8_t
power_loss_report_event(struct timer *t)
{
    struct power_loss_check_dev *p = container_of(t, struct power_loss_check_dev, timer);
    p->report_state = 1;
    sched_wake_task(&power_loss_wake);
    p->timer.waketime += p->report_interval;
    return SF_RESCHEDULE;
}

void
power_loss_check_init(void)
{
    if (!plc) {
        output("power_loss_check_dev: Missing config");
        return;
    }
    crm_periph_clock_enable(CRM_TMR4_PERIPH_CLOCK, TRUE);
    crm_periph_clock_enable(CRM_GPIOB_PERIPH_CLOCK, TRUE);
    crm_periph_clock_enable(CRM_GPIOA_PERIPH_CLOCK, TRUE);

    // gpio init
    gpio_init_type gpio_init_struct = {0};
    gpio_init_struct.gpio_pins = DETECTION_GPIO_PIN;
    gpio_init_struct.gpio_mode = GPIO_MODE_INPUT;
    gpio_init_struct.gpio_out_type = GPIO_OUTPUT_PUSH_PULL;
    gpio_init_struct.gpio_pull = GPIO_PULL_DOWN;
    gpio_init_struct.gpio_drive_strength = GPIO_DRIVE_STRENGTH_STRONGER;
    gpio_init(DETECTION_GPIO, &gpio_init_struct);

    #if CONFIG_MACH_AT32F403A
        gpio_init_struct.gpio_drive_strength = GPIO_DRIVE_STRENGTH_STRONGER;
        gpio_init_struct.gpio_out_type = GPIO_OUTPUT_PUSH_PULL;
        gpio_init_struct.gpio_mode = GPIO_MODE_OUTPUT;
        gpio_init_struct.gpio_pins = GPIO_PINS_15;
        gpio_init_struct.gpio_pull = GPIO_PULL_NONE;
        gpio_init(GPIOA, &gpio_init_struct);
        GPIOA->clr = GPIO_PINS_15;
    #endif

    // tmr init
    tmr_counter_enable(TMR4, FALSE);
    tmr_interrupt_enable(TMR4, TMR_OVF_INT | TMR_C2_INT, FALSE);
    TMR4->ists &= 0;
    /* tmr4 counter mode configuration */
    double calc_ticks = (double)TRM_OVER_FREQ * plc->power_loss_trigger_time - 1.0;
    if (calc_ticks < 0.0 || calc_ticks > 65535.0) {
        shutdown("Invalid power loss trigger time");
    }
    uint16_t pr_val = (uint16_t)calc_ticks;
    tmr_base_init(TMR4, pr_val, TRM_PR_DIV_VALUE);
    tmr_counter_value_set(TMR4, 0);
    tmr_cnt_dir_set(TMR4, TMR_COUNT_UP);

    #if CONFIG_MACH_AT32F403A
        tmr_input_config_type tmr_input_config_struct;
        tmr_input_config_struct.input_channel_select = TMR_SELECT_CHANNEL_2;
        tmr_input_config_struct.input_mapped_select = TMR_CC_CHANNEL_MAPPED_DIRECT;
        tmr_input_config_struct.input_polarity_select = TMR_INPUT_BOTH_EDGE;
        tmr_input_channel_init(TMR4, &tmr_input_config_struct, TMR_CHANNEL_INPUT_DIV_1);
        tmr_interrupt_enable(TMR4, TMR_C2_INT, TRUE);
    #endif

    tmr_overflow_request_source_set(TMR4, TRUE);
    tmr_interrupt_enable(TMR4, TMR_OVF_INT, TRUE);
    armcm_enable_irq(TIM4_IRQHandler, TMR4_GLOBAL_IRQn, 1);

    // tmr enable counter
    tmr_counter_enable(TMR4, TRUE);
}

void
command_config_power_loss_check_dev(uint32_t *args)
{
    uint8_t existing_oid;
    struct power_loss_check_dev *existing_dev;
    foreach_oid(existing_oid, existing_dev, command_config_power_loss_check_dev) {
        output("power_loss_check_dev: Already configured");
        return;
    }
    plc = oid_alloc(args[0], command_config_power_loss_check_dev, sizeof(*plc));
    plc->timer.waketime = args[1];
    plc->power_loss_trigger_time = (double)args[2] / 1000000;
    plc->report_interval = args[3];
    plc->duty_cycle_threshold = (double)args[4] / 1000000;
    plc->debounce_threshold = args[5];
    plc->report_state = 0;
    plc->need_save = 0;
    plc->high_level_tick = 0xFFFFFFFF;
    plc->low_level_tick = 0xFFFFFFFF;
    plc->voltage_type = 0xFF;
    plc->timer.func = power_loss_report_event;
    plc->debounce_count = 0;
    plc->power_loss_flag = 0;
    plc->type_confirm_threshold = args[6] ? args[6] : 3;
    plc->print_act = 0;
    plc->print_mark = 0xFFFFFFFF;
    power_loss_check_init();
    if (plc->report_interval)
      sched_add_timer(&plc->timer);
}
DECL_COMMAND(command_config_power_loss_check_dev,
             "config_power_loss_check oid=%c clock=%u power_loss_trigger_time=%u report_interval=%u duty_threshold=%u"
             " debounce_threshold=%u type_confirm_threshold=%u");

void
command_query_power_loss_status(uint32_t *args)
{
    uint32_t high_level = plc ? plc->high_level_tick : 0xFFFFFFFF;
    uint32_t low_level = plc ? plc->low_level_tick : 0xFFFFFFFF;
    uint8_t voltage_type = plc ? plc->voltage_type : 0xFF;
    uint8_t power_loss_flag = plc ? plc->power_loss_flag : 0;
    uint8_t initialized = plc ? 1 : 0;

    sendf("power_loss_status oid=%c high_level=%u low_level=%u voltage_type=%u power_loss_flag=%u initialized=%u",
          args[0], high_level, low_level, voltage_type, power_loss_flag, initialized);
}
DECL_COMMAND(command_query_power_loss_status, "query_power_loss_status oid=%c");

void
command_update_report_interval(uint32_t *args)
{
    if (!plc) {
        output("power_loss_check_dev: Not configured");
        return;
    }

    irq_disable();
    sched_del_timer(&plc->timer);
    plc->report_interval = args[1];
    if (plc->report_interval) {
        plc->timer.waketime = timer_read_time() + plc->report_interval;
        sched_add_timer(&plc->timer);
    }
    irq_enable();
}
DECL_COMMAND(command_update_report_interval,
             "update_report_interval oid=%c report_interval=%u");

void
command_enable_power_loss(uint32_t *args)
{
    if (!plc) {
        output("power_loss_check_dev: Not configured");
        return;
    }

    irq_disable();
    plc->print_act = !!args[1];
    if (plc->print_act)
        plc->print_mark = args[2];
    else
        plc->print_mark = 0xFFFFFFFF;
    config_stepper_print_act(!!args[1], args[3]);
    irq_enable();
}
DECL_COMMAND(command_enable_power_loss,
            "enable_power_loss oid=%c enable=%u print_flag=%u move_line=%u");

void
command_query_power_loss_flash_valid(uint32_t *args)
{
    sendf("power_loss_flash_valid oid=%c last_seq=%u valid_sector_count=%u env_flag=%u save_stepper_num=%u",
        args[0], last_seq_num, valid_count, env.flag, env.step_info_num);
}
DECL_COMMAND(command_query_power_loss_flash_valid, "query_power_loss_flash_valid oid=%c");

void
command_query_power_loss_stepper_info(uint32_t *args)
{
    uint16_t step_info_num = env.step_info_num;
    uint16_t i = 0;
    if (args[1] == 0xFF) {
        for (i = 0; i < step_info_num && i < MAX_ALLOW_SAVE_STEPPER_NUM; i++) {
            sendf("power_loss_stepper_info oid=%c type=%u index=%u line=%u position=%u",
                args[0], env.step_info_arry[i].type, env.step_info_arry[i].index,
                env.step_info_arry[i].line, env.step_info_arry[i].position);
        }
    }
    else {
        step_info_num = get_all_stepper_info(tmp_env.step_info_arry, MAX_ALLOW_SAVE_STEPPER_NUM, 0);
        for (i = 0; i < step_info_num && i < MAX_ALLOW_SAVE_STEPPER_NUM; i++) {
            sendf("power_loss_stepper_info oid=%c type=%u index=%u line=%u position=%u",
                args[0], tmp_env.step_info_arry[i].type, tmp_env.step_info_arry[i].index,
                tmp_env.step_info_arry[i].line, tmp_env.step_info_arry[i].position);
        }
    }
    sendf("power_loss_stepper_info_result oid=%c result=%u", args[0], 1);
}
DECL_COMMAND(command_query_power_loss_stepper_info, "query_power_loss_stepper_info oid=%c type=%u index=%u");

void
power_loss_check_dev_task(void)
{
    if (plc && plc->power_loss_flag == 1)
        trigger_power_loss_gpio_set();

    if (!sched_check_wake(&power_loss_wake))
        return;

    uint8_t oid;
    struct power_loss_check_dev *p;
    foreach_oid(oid, p, command_config_power_loss_check_dev) {
        if (plc->need_save && !power_loss_saved) {
            power_loss_saved = 1;
            power_loss_rotate_sector();
            output("Power loss info saved");
            plc->need_save = 0;
        }

        irq_disable();
        if (!p->report_state) {
            irq_enable();
            continue;
        }
        p->report_state = 0;
        irq_enable();
        uint8_t initialized = plc ? 1 : 0;
        sendf("report_power_loss_status oid=%c high_level=%u low_level=%u voltage_type=%u power_loss_flag=%u initialized=%u",
              oid, plc->high_level_tick, plc->low_level_tick, plc->voltage_type, plc->power_loss_flag, initialized);
    }
}
DECL_TASK(power_loss_check_dev_task);

void power_loss_check_task_init(void)
{
    load_save_flash_info();
}
DECL_INIT(power_loss_check_task_init);

void
power_loss_check_shutdown(void)
{
    uint8_t oid;
    struct power_loss_check_dev *p;
    foreach_oid(oid, p, command_config_power_loss_check_dev) {
        sched_del_timer(&p->timer);
        if (!power_loss_saved && p->print_act) {
            power_loss_saved = 1;
            power_loss_rotate_sector();
            output("Power loss info saved during shutdown");
        }
    }
#if CONFIG_MACH_AT32F4x
    tmr_counter_enable(TMR4, FALSE);
    tmr_interrupt_enable(TMR4, TMR_OVF_INT | TMR_C2_INT, FALSE);
    NVIC_DisableIRQ(TMR4_GLOBAL_IRQn);
#endif
    plc = NULL;
}
DECL_SHUTDOWN(power_loss_check_shutdown);
#endif
