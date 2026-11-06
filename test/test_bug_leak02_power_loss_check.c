#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#define SUCCESS 0
#define ERROR 1

static bool s_flash_locked = true;
static int s_fail_on_step = 0; // 1: timeout, 2: erase, 3: write

static void flash_unlock_mock(void) {
    s_flash_locked = false;
}

static void flash_lock_mock(void) {
    s_flash_locked = true;
}

static int flash_write_patched_mock(void) {
    flash_unlock_mock();

    if (s_fail_on_step == 1) {
        // Simulated timeout
        goto err_exit;
    }
    if (s_fail_on_step == 2) {
        // Simulated erase error
        goto err_exit;
    }
    if (s_fail_on_step == 3) {
        // Simulated write error
        goto err_exit;
    }

    flash_lock_mock();
    return SUCCESS;

err_exit:
    flash_lock_mock();
    return ERROR;
}

static int flash_write_unpatched_mock(void) {
    flash_unlock_mock();

    if (s_fail_on_step == 1) return ERROR; // Bug: flash_lock omitted
    if (s_fail_on_step == 2) return ERROR; // Bug: flash_lock omitted
    if (s_fail_on_step == 3) return ERROR; // Bug: flash_lock omitted

    flash_lock_mock();
    return SUCCESS;
}

int main(void) {
    printf("Starting BUG-LEAK-02 Flash Lock Leak tests...\n");

    // Test 1: Successful write
    s_fail_on_step = 0;
    int res = flash_write_patched_mock();
    assert(res == SUCCESS);
    assert(s_flash_locked == true);
    printf("  [PASS] Successful write relocks flash correctly.\n");

    // Test 2: Unpatched bug demonstrates lock leak
    s_fail_on_step = 1;
    res = flash_write_unpatched_mock();
    assert(res == ERROR);
    assert(s_flash_locked == false); // Leak confirmed!
    printf("  [PASS] Confirmed unpatched code leaks unlocked flash on error.\n");

    // Test 3: Patched code on timeout error
    s_fail_on_step = 1;
    res = flash_write_patched_mock();
    assert(res == ERROR);
    assert(s_flash_locked == true);
    printf("  [PASS] Patched code relocks flash on timeout error.\n");

    // Test 4: Patched code on erase error
    s_fail_on_step = 2;
    res = flash_write_patched_mock();
    assert(res == ERROR);
    assert(s_flash_locked == true);
    printf("  [PASS] Patched code relocks flash on erase error.\n");

    // Test 5: Patched code on write error
    s_fail_on_step = 3;
    res = flash_write_patched_mock();
    assert(res == ERROR);
    assert(s_flash_locked == true);
    printf("  [PASS] Patched code relocks flash on write error.\n");

    printf("BUG-LEAK-02: All unit tests passed successfully.\n");
    return 0;
}

