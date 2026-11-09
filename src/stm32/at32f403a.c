#include "at32f403a.h"

#include "at32f403a_407.h"
#include "at32f403a_407_clock.h"

#include "sched.h" // DECL_INIT
#include "command.h" // DECL_CONSTANT_STR
#include "board/armcm_boot.h" // armcm_enable_irq
#include "board/armcm_timer.h" // udelay

#include <string.h> // memmove

/**************** define print uart ******************/
#define PRINT_UART                       USART3
#define PRINT_UART_CRM_CLK               CRM_USART3_PERIPH_CLOCK
#define PRINT_UART_TX_PIN                GPIO_PINS_10
#define PRINT_UART_TX_GPIO               GPIOB
#define PRINT_UART_TX_GPIO_CRM_CLK       CRM_GPIOB_PERIPH_CLOCK
// #define PRINT_UART_GPIO_REMAP            USART6_GMUX

#if CONFIG_AT32_ENABLE_DEBUG_USART
  DECL_CONSTANT_STR("RESERVE_PINS_debug_uart_tx_pin", "PB10");
#endif

#if defined (__GNUC__) && !defined (__clang__)
  #define PUTCHAR_PROTOTYPE int __io_putchar(int ch)
#else
  #define PUTCHAR_PROTOTYPE int fputc(int ch, FILE *f)
#endif


/**
  * @brief  retargets the c library printf function to the usart.
  * @param  none
  * @retval none
  */
PUTCHAR_PROTOTYPE
{
  uint32_t timeout = 100000;
  while(usart_flag_get(PRINT_UART, USART_TDBE_FLAG) == RESET && --timeout);
  if (!timeout)
    return ch;
  usart_data_transmit(PRINT_UART, (uint16_t)ch);
  timeout = 100000;
  while(usart_flag_get(PRINT_UART, USART_TDC_FLAG) == RESET && --timeout);
  return ch;
}

void at32f403a_log(char* log)
{
  while (log && *log) {
    uint32_t timeout = 100000;
    while(usart_flag_get(PRINT_UART, USART_TDBE_FLAG) == RESET && --timeout);
    if (!timeout)
      break;
    usart_data_transmit(PRINT_UART, (uint16_t)(*log));
    log++;
  }
}


/**
  * @brief  initialize uart
  * @param  baudrate: uart baudrate
  * @retval none
  */
void uart_debug_print_init(uint32_t baudrate)
{
  gpio_init_type gpio_init_struct;

// #if defined (__GNUC__) && !defined (__clang__)
//   setvbuf(stdout, NULL, _IONBF, 0);
// #endif

  /* enable the uart and gpio clock */
  crm_periph_clock_enable(PRINT_UART_CRM_CLK, TRUE);
  crm_periph_clock_enable(PRINT_UART_TX_GPIO_CRM_CLK, TRUE);

#ifdef PRINT_UART_GPIO_REMAP
  gpio_pin_remap_config(PRINT_UART_GPIO_REMAP, TRUE);
#endif

  gpio_default_para_init(&gpio_init_struct);

  /* configure the uart tx pin */
  gpio_init_struct.gpio_drive_strength = GPIO_DRIVE_STRENGTH_STRONGER;
  gpio_init_struct.gpio_out_type  = GPIO_OUTPUT_PUSH_PULL;
  gpio_init_struct.gpio_mode = GPIO_MODE_MUX;
  gpio_init_struct.gpio_pins = PRINT_UART_TX_PIN;
  gpio_init_struct.gpio_pull = GPIO_PULL_NONE;
  gpio_init(PRINT_UART_TX_GPIO, &gpio_init_struct);

  /* configure uart param */
  usart_init(PRINT_UART, baudrate, USART_DATA_8BITS, USART_STOP_1_BIT);
  usart_transmitter_enable(PRINT_UART, TRUE);
  usart_enable(PRINT_UART, TRUE);
}


/**
  * @brief  usb 48M clock select
  * @param  clk_s:USB_CLK_HICK, USB_CLK_HEXT
  * @retval none
  */
static void usb_clock48m_select(usb_clk48_s clk_s)
{
  if(clk_s == USB_CLK_HICK)
  {
    crm_usb_clock_source_select(CRM_USB_CLOCK_SOURCE_HICK);

    /* enable the acc calibration ready interrupt */
    crm_periph_clock_enable(CRM_ACC_PERIPH_CLOCK, TRUE);

    /* update the c1\c2\c3 value */
    acc_write_c1(7980);
    acc_write_c2(8000);
    acc_write_c3(8020);

    /* open acc calibration */
    acc_calibration_mode_enable(ACC_CAL_HICKTRIM, TRUE);
  }
  else
  {
    switch(SystemCoreClock)
    {
      /* 48MHz */
      case 48000000:
        crm_usb_clock_div_set(CRM_USB_DIV_1);
        break;

      /* 72MHz */
      case 72000000:
        crm_usb_clock_div_set(CRM_USB_DIV_1_5);
        break;

      /* 96MHz */
      case 96000000:
        crm_usb_clock_div_set(CRM_USB_DIV_2);
        break;

      /* 120MHz */
      case 120000000:
        crm_usb_clock_div_set(CRM_USB_DIV_2_5);
        break;

      /* 144MHz */
      case 144000000:
        crm_usb_clock_div_set(CRM_USB_DIV_3);
        break;

      /* 168MHz */
      case 168000000:
        crm_usb_clock_div_set(CRM_USB_DIV_3_5);
        break;

      /* 192MHz */
      case 192000000:
        crm_usb_clock_div_set(CRM_USB_DIV_4);
        break;

      default:
        break;

    }
  }
}

#if CONFIG_STM32_SERIAL_AT_USART5_PB8_PB9 || CONFIG_STM32_USBCANBUS_PA11_PA12_AND_SERIAL_USART5_PB8_PB9
void mcu_uart_gpio_remap(void) {
  gpio_pin_remap_config(UART5_GMUX_0001, TRUE);
}
#endif

void mcu_can2_gpio_remap(void) {
  gpio_pin_remap_config(CAN2_GMUX_0001, TRUE);
}

void mcu_spi4_gpio_remap(void) {
  gpio_pin_remap_config(SPI4_GMUX_0001, TRUE);
}

void at32f403a_clock_setup(void)
{
  system_clock_config();

  /* select usb 48m clcok source */
  usb_clock48m_select(USB_CLK_HICK);

  /* enable usb clock */
  crm_periph_clock_enable(CRM_USB_PERIPH_CLOCK, TRUE);
}
