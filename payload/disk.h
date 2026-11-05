#ifndef FROGGER_DISK_H
#define FROGGER_DISK_H

#include <stdint.h>

/* disk.c: whether the disk is free for a write from the UI (no read running,
 * none for `us`, the drive not busy or waiting to be re-inited). */
int disk_idle(uint32_t us);
#define DISK_IDLE_US    500000      /* a refill's reads come back to back */

#endif
