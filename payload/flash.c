/* Flash Storage: let a flash mod's disk sleep sooner.
 *
 * Apple's disk arbiter (the task at 0x13bc94, mailbox 19) keeps the disk
 * spinning while any of its 19 clients holds it. A client says it's done with
 * 0x57820(client, ms): "keep it up for ms more" (stored as ms / 10 + 1
 * ticks). When the last client's time runs out the arbiter posts sub-op 2 to
 * the disk-power task, which sends STANDBY IMMEDIATE (0x134c58). The times are
 * a hard drive's: 10 s after a music-cache refill (TrackCacheReadTask, client
 * 6), 15 s after the database load (client 1), 3 s, 2 s and 1 s for others.
 * A spin-up costs a hard drive power and a second or two, so holding it a
 * while is cheaper than a wake. A flash card behind an IDE bridge (iFlash and
 * the like) has nothing to spin: with this on, every hold is cut to
 * FLASH_HOLD_MS (flash_hold, from flash_hold_hook at 0x57820), so the bridge
 * gets its STANDBY that much sooner.
 *
 * Whether that saves anything depends on the bridge: one that powers the card
 * down on STANDBY saves the card's idle current for the time cut; one that
 * ignores STANDBY saves nothing, and costs nothing either (the next command
 * just runs). Apple's waits after a wake and at boot (0x97830, 0x9439c) end as
 * soon as the drive drops BSY, so they cost a fast card nothing and are left
 * alone, as is disk.c's reset wait.
 *
 * The switch has three values: Off (Apple's times, the default), Auto and
 * On. Auto acts only when the drive's IDENTIFY data says flash: word 217
 * (nominal rotation rate) 1, a CompactFlash signature in word 0 (0x848a), or
 * a model string of a flash adapter or card. A bridge answers IDENTIFY for
 * the card and may report none of these, so Auto can miss a flash mod (use
 * On), but a drive reporting a rotation rate is always left alone. flash_id
 * (flash_id_hook at 0x9dbac, where the driver's IDENTIFY has just finished)
 * keeps the words it needs. */

#include <stdint.h>
#include "settings.h"

#define OBJ_ID_BUF      0x17c       /* ata+0x17c: the transfer pointer (0xdec68 stores the IDENTIFY buffer; past its
                                     * 512 bytes once the data is in) */
#define OBJ_RESULT      0x190       /* ata+0x190: the command's error, 0 = done */

#define FLASH_HOLD_MS   1000        /* every client's hold, at most (Apple's go up to 15 s) */

/* What the drive said, for Auto (and for a look from emupod or a debug
 * record): IDENTIFY words 0 and 217 and the model (words 27-46, ASCII). */
uint16_t flash_id_w0, flash_id_rpm;
char flash_id_model[41];
uint8_t flash_id_seen;

static int has(const char *s, const char *word)
{
    for (; *s; s++) {
        const char *a = s, *b = word;

        while (*b && (*a == *b || (*a >= 'a' && *a <= 'z' && *a - 32 == *b)))
            a++, b++;
        if (!*b)
            return 1;
    }
    return 0;
}

/* Upper-case words found in the models of flash adapters and cards (an
 * iFlash bridge, SanDisk and Transcend CF, SD bridges). No hard drive the 3G
 * shipped with (Toshiba MK..GAL/GAH) has any of them. */
static const char *const flash_models[] = { "FLASH", "SDCF", "SSD", "SD CARD", "SDHC", "SDXC", "CF CARD", 0 };

int flash_detected(void)
{
    const char *const *m;

    if (!flash_id_seen)
        return 0;
    if (flash_id_rpm > 1 && flash_id_rpm != 0xffff)
        return 0;                   /* says it rotates: a hard drive */
    if (flash_id_rpm == 1 || flash_id_w0 == 0x848a)
        return 1;
    for (m = flash_models; *m; m++)
        if (has(flash_id_model, *m))
            return 1;
    /* Transcend's cards: "TS" and a size (TS8GCF133, TS32GCF...) */
    return flash_id_model[0] == 'T' && flash_id_model[1] == 'S' && flash_id_model[2] >= '0' && flash_id_model[2] <= '9';
}

/* From flash_id_hook, as the driver's IDENTIFY ends (ata: the ATA object). */
void flash_id(uint8_t *ata)
{
    const uint16_t *w = *(const uint16_t **)(ata + OBJ_ID_BUF);
    unsigned i, n = 0;

    if (*(volatile uint32_t *)(ata + OBJ_RESULT) || (uint32_t)w < 512)
        return;
    w -= 256;                       /* the 256 words just read */
    flash_id_w0 = w[0];
    flash_id_rpm = w[217];
    for (i = 27; i < 47; i++) {
        flash_id_model[n++] = (char)(w[i] >> 8);
        flash_id_model[n++] = (char)w[i];
    }
    while (n && (flash_id_model[n - 1] == ' ' || !flash_id_model[n - 1]))
        n--;
    flash_id_model[n] = 0;
    flash_id_seen = 1;
}

/* Whether the shorter holds apply now. */
int flash_active(void)
{
    unsigned mode = frogger_flash_mode();

    return mode == FLASH_ON || (mode == FLASH_AUTO && flash_detected());
}

/* From flash_hold_hook, the first instruction of 0x57820(client, ms): the ms
 * to pass on. */
uint32_t flash_hold(uint32_t client, uint32_t ms)
{
    (void)client;
    if (ms > FLASH_HOLD_MS && flash_active())
        return FLASH_HOLD_MS;
    return ms;
}
