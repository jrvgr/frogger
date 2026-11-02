/* Frogger loader entry.
 *
 * ipodpatcher -ab appends this binary to Apple's osos image and points the
 * directory's entryOffset at it. Apple's flash boot code loads the whole osos
 * image to DRAM_START (0x28000000) and jumps here, so Apple's own OS is
 * already in RAM below us, untouched.
 *
 * The CPU copies the loader to its link address near the top of DRAM, runs
 * main() (which may patch Apple's OS in place) and jumps to the address main
 * returns. If the COP core also arrives here, it waits on a flag in the copy
 * that was loaded (whose initial value is known) and then follows the CPU.
 */

    .section .init.text, "ax", %progbits
    .arm
    .global _start
_start:
    ldr     r0, =0xc4000000         @ PROCESSOR_ID
    ldr     r0, [r0]
    and     r0, r0, #0xff
    cmp     r0, #0xaa               @ PROC_ID_COP
    beq     cop_wait

    adr     r4, _start              @ r4 = where Apple loaded us (kept across main)

    @ Copy ourselves to the link address.
    mov     r0, r4
    ldr     r1, =_start
    ldr     r2, =_loader_end
1:  cmp     r1, r2
    ldrlo   r3, [r0], #4
    strlo   r3, [r1], #4
    blo     1b

    @ Clear .bss.
    ldr     r1, =_bss_start
    ldr     r2, =_bss_end
    mov     r3, #0
2:  cmp     r1, r2
    strlo   r3, [r1], #4
    blo     2b

    ldr     sp, =_stack_top
    ldr     r0, =main
    mov     lr, pc
    bx      r0                      @ r0 = address to boot

    @ Release the COP through the flag in the loaded copy, then go.
    add     r1, r4, #(cop_entry - _start)
    str     r0, [r1]
    add     r1, r4, #(cop_go - _start)
    mov     r2, #1
    str     r2, [r1]
    bx      r0

cop_wait:
    adr     r1, cop_go
3:  ldr     r2, [r1]
    cmp     r2, #0
    beq     3b
    adr     r1, cop_entry
    ldr     r0, [r1]
    bx      r0

    .align  2
cop_go:     .word 0
cop_entry:  .word 0
    .ltorg
