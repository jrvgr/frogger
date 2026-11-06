/* Getting the disk back after it stops answering.
 *
 * An SD adapter in place of the hard drive can drop out when the supply dips
 * (a music-cache refill at a song change, with big files): it stays BSY and
 * raises no interrupt. Apple's driver then times the command out after 10 s
 * (event 5, 0x1302a0), resets its own IDE controller (0x913d0: 0xcf005034
 * bit 2) and sets obj+0x1e0 so the next command re-inits the drive first
 * (0xc347c: SET FEATURES for the transfer modes, SET MULTIPLE). It never
 * resets the drive, though, so 0xc347c's 300 us BSY check fails, every
 * command after it returns 0x400 at once, and TrackCacheReadTask (0xe9c4c)
 * gives up: no more songs or covers until a restart.
 *
 * disk_reinit (disk_reinit_hook, the first instruction of 0xc347c) adds the
 * drive's soft reset: when the drive still shows BSY or DRQ, set and clear
 * SRST in the device control register and wait for BSY to clear, yielding.
 * 0xc347c then redoes the setup the reset dropped. disk_read_hook (the first
 * instruction of the read, 0xc788c) retries a read that failed with obj+0x1e0
 * set, a bounded number of times, so the failed command comes back too. */

#include <stdint.h>
#include "disk.h"

#define OBJ_STATUS      0x10c       /* obj+0x10c: the status register (0xc00031fc) */
#define OBJ_CTL         0x114       /* obj+0x114: device control (0xc00033f8; 0x942cc writes it with strb) */
#define OBJ_ALT         0x118       /* obj+0x118: alternate status, the same address */

#define ST_BSY          0x80
#define ST_DRQ          0x08
#define CTL_NIEN        0x02
#define CTL_SRST        0x04

#define FW_UDELAY       0x14b0b8    /* 0x14b0b8(us): busy-waits on the us timer */
#define FW_WAIT_READY   0x13fa14    /* 0x13fa14(obj, us): BSY clear? 0 yes, 1 timed out; sleeps 1 ms a step */

#define RESET_WAIT_US   3100000     /* Apple's own wait after a wake (0x97830), safe for a hard drive's spin-up.
                                     * 0x13fa14 counts 1 ms per 0x3460 step, which emupod times at 10 ms, so
                                     * this may really be up to ~31 s; it ends as soon as the drive answers. */

static void udelay(uint32_t us)
{
    ((void (*)(uint32_t))FW_UDELAY)(us);
}

static volatile uint8_t *reg(uint8_t *obj, uint32_t field)
{
    return *(volatile uint8_t **)(obj + field);
}

/* From disk_reinit_hook, before 0xc347c(obj, unit) re-inits the drive. */
void disk_reinit(uint8_t *obj)
{
    volatile uint8_t *ctl = reg(obj, OBJ_CTL);

    if ((*reg(obj, OBJ_ALT) & (ST_BSY | ST_DRQ)) == 0)
        return;                     /* it answers: Apple's re-init is enough */
    *ctl = CTL_SRST | CTL_NIEN;     /* SRST for at least 5 us */
    udelay(20);
    *ctl = CTL_NIEN;
    udelay(2000);                   /* the drive sets BSY within 400 ns of the reset; give it 2 ms */
    ((uint32_t (*)(uint8_t *, uint32_t))FW_WAIT_READY)(obj, RESET_WAIT_US);
    *ctl = 0;                       /* interrupts on again, as Apple's init leaves it */
    (void)*reg(obj, OBJ_STATUS);    /* and nothing pending from the reset */
}

/* Whether the disk is free, for the UI's own writes (hide.c, playlist.c):
 * disk_read_hook counts the reads running and notes when the last one
 * ended. A music-cache refill is reads back to back, and a read the drive
 * never answers runs for its 10 s timeout and the retries above, so the UI
 * waits (instead of blocking on the disk) until none has run for a while.
 * The count is changed with IRQs off, as two tasks (the cache's and Frogger's
 * cover task, art.c) read at once. */
#define FW_CLOCK_US     0x87de0     /* 0x87de0(&us) */
#define OBJ_REINIT      0x1e0       /* obj+0x1e0: re-init pending (0x913d0 sets it) */

static uint8_t *disk_obj;
static volatile uint32_t disk_reads, disk_last, disk_busy_since;

static uint32_t irq_off(void)
{
    uint32_t s, t;

    __asm__ volatile("mrs %0, cpsr\n\torr %1, %0, #0x80\n\tmsr cpsr_c, %1" : "=r"(s), "=r"(t) : : "memory");
    return s;
}

static void irq_restore(uint32_t s)
{
    __asm__ volatile("msr cpsr_c, %0" : : "r"(s) : "memory");
}

static uint32_t now_us(void)
{
    uint32_t us;

    ((void (*)(uint32_t *))FW_CLOCK_US)(&us);
    return us;
}

/* From disk_read_hook, as a read starts (obj: the ATA object) and ends. */
void disk_read_begin(uint8_t *obj)
{
    uint32_t t = now_us(), s = irq_off();

    disk_obj = obj;
    if (disk_reads++ == 0)
        disk_busy_since = t;
    irq_restore(s);
}

void disk_read_end(void)
{
    uint32_t t = now_us(), s = irq_off();

    disk_last = t;
    if (disk_reads)
        disk_reads--;
    irq_restore(s);
}

/* 1 if no read is running or has for `us`, no re-init is pending and the
 * drive doesn't show BSY or DRQ. */
int disk_idle(uint32_t us)
{
    uint8_t *obj = disk_obj;

    if (disk_reads || now_us() - disk_last < us)
        return 0;
    if (!obj)
        return 1;                   /* no read yet: nothing to wait for */
    return !*(volatile uint32_t *)(obj + OBJ_REINIT) && !(*reg(obj, OBJ_ALT) & (ST_BSY | ST_DRQ));
}

/* 1 if a read has been running for `us` with none ending meanwhile (the
 * drive stopped answering: disk_read_hook is waiting out the 10 s timeout or
 * retrying), or a re-init is pending. A read that just queued behind the
 * stuck one doesn't count as progress. */
int disk_stalled(uint32_t us)
{
    uint8_t *obj = disk_obj;
    uint32_t t = now_us(), since;

    if (obj && *(volatile uint32_t *)(obj + OBJ_REINIT))
        return 1;
    if (!disk_reads)
        return 0;
    since = (int32_t)(disk_last - disk_busy_since) > 0 ? disk_last : disk_busy_since;
    return t - since >= us;
}

/* The next-song preload, on the UI thread (preload_hook, the bl 0x9f288 at
 * 0x94984 in the playback tick 0x94918, which the UI dispatcher runs). Once
 * 0x9f288 lets it, the tick loads the next song through 0xbca48, and that
 * takes the volume's lock (fw_volume, 0xb1d50, at 0x66c74). A
 * reader whose command the drive never answered holds that lock for the
 * whole timeout and recovery (an FS worker task, the 0x14a810 loop, or the
 * cover task), so the UI would wait with it: no wheel, no Menu, for 10 s and
 * more (stock 2.3 does). While the disk is stalled the tick skips the preload
 * as when 0x9f288 says no (to 0x94b38): [player+0xb4c] stays set, and a later
 * tick, once the disk answers, preloads. */
#define FW_PRELOAD_BUSY 0x9f288     /* 0x9f288(lib): nonzero, not now */
#define PRELOAD_STALL_US 250000     /* a read takes ms; a sleeping hard drive's spin-up, a second or two */

uint32_t preload_hook(void *lib)
{
    uint32_t busy = ((uint32_t (*)(void *))FW_PRELOAD_BUSY)(lib);

    return busy ? busy : (uint32_t)disk_stalled(PRELOAD_STALL_US);
}
