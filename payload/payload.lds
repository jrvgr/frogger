/* Frogger's resident code: stays in RAM while Apple's OS runs. It lives in
 * the top 1 MiB of DRAM, which the loader takes from the end of Apple's heap
 * (loader/patches.c, HEAP_PATCHES; docs/re-notes.md, "Free RAM"). */
ENTRY(track_hook)

MEMORY
{
    RESIDENT (rwx) : ORIGIN = 0x1f00000, LENGTH = 0x2000000 - 0x1f00000
}

SECTIONS
{
    .text : {
        *(.text*)
        *(.rodata*)
        *(.data*)
        . = ALIGN(4);
    } > RESIDENT
    _payload_end = .;

    .bss (NOLOAD) : {
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _bss_end = .;
    } > RESIDENT

    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) }
}
