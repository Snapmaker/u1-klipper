#include "at32f415.h"
#include "at32f415rc.h"
#include "at32f415_clock.h"
#include "command.h" // DECL_CONSTANT_STR

/**************** define print uart ******************/
#define PRINT_UART                       USART3
#define PRINT_UART_CRM_CLK               CRM_USART3_PERIPH_CLOCK
#define PRINT_UART_TX_PIN                GPIO_PINS_10
#define PRINT_UART_TX_GPIO               GPIOB
#define PRINT_UART_TX_GPIO_CRM_CLK       CRM_GPIOB_PERIPH_CLOCK

#if CONFIG_AT32_ENABLE_DEBUG_USART
  DECL_CONSTANT_STR("RESERVE_PINS_debug_uart_tx_pin", "PB10");
#endif

void at32f415_log(char* log)
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

  /* enable the uart and gpio clock */
  crm_periph_clock_enable(PRINT_UART_CRM_CLK, TRUE);
  crm_periph_clock_enable(PRINT_UART_TX_GPIO_CRM_CLK, TRUE);

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



/****************************************************************
 * USB init
 ****************************************************************/
#include "usb_conf.h"

/**
  * @brief  usb 48M clock select
  * @param  clk_s:USB_CLK_HICK, USB_CLK_HEXT
  * @retval none
  */
void usb_clock48m_select(usb_clk48_s clk_s)
{
  switch(system_core_clock)
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

    default:
      break;
  }
}

/****************************************************************
 * customizing External Reference Functions
 ****************************************************************/

void at32f415rc_clock_setup(void)
{
  system_clock_config();
}

void at32f415rc_usbotg_clock_config(void)
{
  /* enable otgfs clock */
  crm_periph_clock_enable(OTG_CLOCK, TRUE);

  /* select usb 48m clcok source */
  usb_clock48m_select(USB_CLK_HEXT);

}
