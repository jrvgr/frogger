/* The loader runs from the second-to-top 1 MiB of the 3G's 32 MiB DRAM, well
 * above Apple's osos image at 0x28000000 and below the payload it installs in
 * the top 1 MiB (payload/payload.lds). Apple's heap covers this after boot. */
ENTRY(_start)

MEMORY
{
    LOADER (rwx) : ORIGIN = 0x29e00000, LENGTH = 0x100000
}

SECTIONS
{
    .text : {
        *(.init.text)
        *(.text*)
        *(.rodata*)
    } > LOADER

    .data : {
        *(.data*)
        . = ALIGN(4);
    } > LOADER
    _loader_end = .;

    .bss (NOLOAD) : {
        _bss_start = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _bss_end = .;
    } > LOADER

    _stack_top = ORIGIN(LOADER) + LENGTH(LOADER);

    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) }
}
