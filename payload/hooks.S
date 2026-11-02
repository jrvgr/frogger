/* Hooks from Apple's osos into the payload's C (hide.c, settings.c, art.c,
 * nowplaying.c, artist.c, queue.c, holdmenu.c, letters.c, resume.c, skips.c). Each replaces one instruction with
 * a BL here (the table in tools/mkpayload.py), redoes that instruction,
 * and returns. Stack offsets are into the hooked function's frame, plus
 * whatever the hook pushed. */

#include "hide.h"
#include "settings.h"
#include "nowplaying.h"
#include "queue.h"
#include "holdmenu.h"
#include "debug.h"
#include "resume.h"

    .text
    .arm

/* 0xc4b30 in the track loader, right after a track record (r4) is made
 * (was: ldr r0, [sp, #1072]). The mhit header is at sp+0x420 and
 * [sp+0x4bc] is the track's index in the mhlt. */
    .global track_hook
track_hook:
    push    {r4, lr}
    mov     r0, r4
    ldr     r1, [sp, #8 + 0x4bc]
    bl      np_track_loaded         @ where the records are, for covers (art.c)
    mov     r0, r4
    ldr     r1, [sp, #8 + 0x4bc]
    ldr     r2, [sp, #8 + 0x420 + 0x10]
    bl      hide_loaded             @ and their positions and ids (hide.c, FroggerHidden)
    ldr     r0, [sp, #8 + 0x4bc]
    cmp     r0, #0
    bleq    hide_reset              @ first track: a fresh database
    ldr     r0, [sp, #8 + 0x420 + HIDE_MHIT_OFFSET]
    ldr     r1, =HIDE_MAGIC
    cmp     r0, r1
    moveq   r0, r4
    bleq    hide_mark
    pop     {r4, lr}
    ldr     r0, [sp, #1072]
    bx      lr

/* 0xc4e64 in the track loader, before its mhod type switch (was: ldr r0,
 * [sp, #1044]). [sp+0x414] is the mhod's type, r4 the track record. The
 * type album_artist_mhod() returns goes back there too, since the string
 * reader gets it from the same word. */
    .global mhod_hook
mhod_hook:
    push    {r1-r4, r12, lr}
    ldr     r0, [sp, #24 + 1044]
    mov     r1, r4
    bl      album_artist_mhod       @ artist.c
    str     r0, [sp, #24 + 1044]
    pop     {r1-r4, r12, lr}
    bx      lr

/* 0xc431c in the playlist loader, as each mhyp starts (was: mov r7, #1).
 * [sp+0xc0] is mhyp+0x14, the master-playlist flag. */
    .global mhyp_hook
mhyp_hook:
    ldr     r7, =hide_state
    ldrb    r12, [sp, #0xc0]
    strb    r12, [r7, #0]           @ is_master
    mov     r7, #1
    bx      lr

/* 0xc4768, after an mhip's track joined the playlist (was:
 * ldrb r1, [sp, #48]). [sp+0xa8] is the playlist object; the master's is
 * what the browse loop walks for Artists/Albums/Songs. */
    .global mhip_hook
mhip_hook:
    ldr     r1, =hide_state
    ldrb    r12, [r1, #0]
    cmp     r12, #0
    ldrne   r12, [sp, #0xa8]
    strne   r12, [r1, #4]           @ master
    ldrb    r1, [sp, #48]
    bx      lr

/* 0xf205c in the browse loop, once a playlist item matched the query
 * (was: ldr r0, [sp, #88]). r7 is the item list, [sp+0x7c] the index and
 * r8 the track. Returning to 0xf211c drops the item from the list. */
    .global filter_hook
filter_hook:
    push    {r4, lr}
    ldr     r0, [sp, #8 + 0x7c]
    add     r0, r7, r0, lsl #2
    ldr     r0, [r0, #12]           @ item
    ldr     r0, [r0]                @ its playlist
    mov     r1, r8
    bl      hide_entry
    cmp     r0, #0
    pop     {r4, lr}
    ldr     r0, [sp, #88]
    addne   lr, lr, #(0xf211c - 0xf2060)
    bx      lr

/* 0x58444 in 0x58440(library, item), which every library list (Artists,
 * Albums, Songs, Genres, Composers, Shuffle Songs) asks about each master
 * playlist item (was: mov r5, r0). The function has just pushed
 * {r4-r9, lr}; returning 0 from it drops the item. r1 is the item: word 0
 * its playlist, +0x20 the track record. Songs (returns to 0x7c4fc) and
 * Shuffle Songs (0x512e8) keep hidden songs: only the lists by artist,
 * album, genre and composer leave them out. So does the add from a list's
 * row (0xc0b30 -> 0x4fb50, returns to 0x4fbb0): it counts the browse list's
 * items up to the row with this same predicate, and must count the rows
 * 0x7c460 shows, or every hidden song above the row moves it one down. */
    .global browse_hook
browse_hook:
    push    {r0, r1, r2, lr}
    ldr     r0, [sp, #16 + 24]      @ 0x58440's return address
    ldr     r2, =0x7c4fc
    cmp     r0, r2
    ldrne   r2, =0x512e8
    cmpne   r0, r2
    ldrne   r2, =0x4fbb0
    cmpne   r0, r2
    beq     1f
    ldr     r0, [sp]                @ the library
    bl      settings_sync           @ Show Hidden from its prefs
    ldr     r1, [sp, #4]            @ the item again
    ldr     r0, [r1]
    ldr     r1, [r1, #0x20]
    bl      hide_entry
    cmp     r0, #0
    pop     {r0, r1, r2, lr}
    movne   r0, #0
    popne   {r4, r5, r6, r7, r8, r9, pc}
    mov     r5, r0
    bx      lr
1:  pop     {r0, r1, r2, lr}
    mov     r5, r0
    bx      lr

/* Frogger's Settings items (settings.c). Values are the string ids the row
 * shows; FOURCC_* are the selectors Apple's settings object uses. */
#define FOURCC_PRID 0x70724944  /* 'prID': the value's string id */
#define FOURCC_STR  0x53747220  /* 'Str ' */

/* 0xdafc8 in the settings setter 0xdafc4(obj, 'prID', item, msg*), right
 * after its push {r3-r11, lr} (was: mov r4, r0). For our items, settle
 * it here and return 1 the way its own cases do (0xdbce0). */
    .global setting_set_hook
setting_set_hook:
    push    {r0, r1, r2, r3, r12, lr}
    mov     r12, r0                 @ the settings object
    mov     r0, r2
    mov     r1, r3
    mov     r2, r12
    bl      setting_set
    cmp     r0, #0
    pop     {r0, r1, r2, r3, r12, lr}
    movne   r0, #1
    popne   {r3, r4, r5, r6, r7, r8, r9, sl, fp, pc}
    mov     r4, r0
    bx      lr

/* 0x7db6c in the settings getter 0x7db68(obj, type, item, out*), right after
 * its push {r0-r11, lr} (was: mov r5, r0). For our items, answer like the
 * Clicker case (0x7e480): 'prID' -> the value at obj+0x48 and *out = &it,
 * 'Str ' -> *out = 0x80890(0x7722c(), 'Str ', value), anything else -> 0.
 * Then return 1 the way 0x7ea64 does. r4-r11 are free: the getter's own
 * epilogue restores them. */
    .global setting_get_hook
setting_get_hook:
    push    {r0, r1, r2, r3, r12, lr}
    mov     r1, r0                  @ the settings object
    mov     r0, r2
    bl      setting_value
    str     r0, [sp, #16]           @ comes back as r12
    pop     {r0, r1, r2, r3, r12, lr}
    cmp     r12, #0
    moveq   r5, r0
    bxeq    lr
    mov     r4, r3                  @ out
    mov     r5, r12                 @ value
    ldr     r12, =FOURCC_PRID
    cmp     r1, r12
    beq     2f
    ldr     r12, =FOURCC_STR
    cmp     r1, r12
    movne   r0, #0
    bne     3f
    ldr     r12, =0x7722c
    mov     lr, pc
    mov     pc, r12
    ldr     r1, =FOURCC_STR
    mov     r2, r5
    ldr     r12, =0x80890
    mov     lr, pc
    mov     pc, r12
    b       3f
2:  strh    r5, [r0, #0x48]
    add     r0, r0, #0x48
3:  str     r0, [r4]
    mov     r0, #1
    add     sp, sp, #4              @ the saved r0
    pop     {r1, r2, r3, r4, r5, r6, r7, r8, r9, sl, fp, pc}

/* 0x875c8 in the bundle lookup 0x875c4(bundle, fourcc, id, size*), right
 * after its push {r4, r5, lr} (was: ldr lr, [r0, #12]). Resources Frogger
 * adds come from the payload (frogger_resource in art.c): return the data
 * and its size. */
    .global string_hook
string_hook:
    push    {r0, r1, r2, r3, r12, lr}
    mov     r0, r1
    mov     r1, r2
    mov     r2, r3
    bl      frogger_resource
    cmp     r0, #0
    beq     4f
    add     sp, sp, #4              @ the saved r0
    pop     {r1, r2, r3, r12, lr}
    pop     {r4, r5, pc}            @ return from 0x875c4 with our data
4:  pop     {r0, r1, r2, r3, r12, lr}
    mov     r5, lr
    ldr     lr, [r0, #12]
    bx      r5

/* 0xb916c, the call that loads a track as the song now playing (was:
 * bl 0xbca48, with the track record in r0). 0xbca48 also runs from 0x94a5c
 * to preload the next song, which doesn't come through here. Tell art.c
 * (which only notes the track: the cover loads on the UI's side), then go
 * on into 0xbca48 with lr still pointing after the call. */
    .global play_hook
play_hook:
    push    {r0, r1, r2, r3, r12, lr}
    bl      np_playing
    pop     {r0, r1, r2, r3, r12, lr}
    ldr     pc, =0xbca48

/* 0xb4578, the first instruction of every element's SetVisible(obj, on) (was:
 * ldr r3, [r0, #32]). Now Playing's art element tells nowplaying.c that the
 * screen opens or closes, and a nonzero return skips the change. That function is a leaf that returns through lr,
 * so this hook is entered with B, not BL (BRANCH_HOOKS in tools/mkpayload.py),
 * and goes back to 0xb457c itself. */
    .global vis_hook
vis_hook:
    push    {r0, r1, r2, r12, lr}
    bl      np_visibility
    mov     r3, r0
    pop     {r0, r1, r2, r12, lr}
    cmp     r3, #0
    bxne    lr                      @ skipped: back to the caller, as 0xb4578 would
    ldr     r3, [r0, #32]
    ldr     pc, =0xb457c

/* 0xe3aac in 0xe3a9c(stack, from, to, kind, duration), which starts a screen
 * stack's slide from one view to another (was: ldr r6, [sp, #84], the
 * duration in ms; r4 is the stack). When np_transition says so, the slide
 * lasts 1 ms: it ends on its first tick. Entered with B like vis_hook; back
 * at 0xe3ab0. */
    .global trans_hook
trans_hook:
    push    {r0, r1, r2, r3, r12, lr}
    mov     r0, r4
    bl      np_transition
    cmp     r0, #0
    pop     {r0, r1, r2, r3, r12, lr}
    ldreq   r6, [sp, #84]
    movne   r6, #1
    ldr     pc, =0xe3ab0

/* 0xd2db4, the first instruction of lcd_update_rect(display, rect), which
 * copies a rectangle of the framebuffer to the LCD (was: push {r4-r10, lr}).
 * While a page switch slides (nowplaying.c) the LCD is held: the call only
 * notes it came. lcd_flush is the way past, for the slide's own frames.
 * Entered with B like vis_hook; back at 0xd2db8. */
    .global lcd_hook
lcd_hook:
    ldr     r12, =np_lcd_hold
    ldrb    r12, [r12]
    cmp     r12, #0
    bne     1f
    .global lcd_flush
lcd_flush:
    push    {r4, r5, r6, r7, r8, r9, sl, lr}
    ldr     pc, =0xd2db8
1:  ldr     r12, =np_lcd_held
    mov     r2, #1
    strb    r2, [r12]
    bx      lr

/* 0x68e60 in 0x68dfc, an end-update, where its drain of dirty rectangles
 * (each drawn, then copied to the LCD) ends, or where it goes when it isn't
 * the last (was: ldr r0, [r4, #32]). np_drawn slides a page switch's two
 * pages across. Entered with B like vis_hook; back at 0x68e64. */
    .global drawn_hook
drawn_hook:
    push    {r0, r1, r2, r3, r12, lr}
    bl      np_drawn
    pop     {r0, r1, r2, r3, r12, lr}
    ldr     r0, [r4, #32]
    ldr     pc, =0x68e64

/* 0x9bab0 in the bytecode interpreter, just before each opcode is fetched (was:
 * ldr r0, [r4, #32], the VM's pc; r4 is the VM). A few pcs matter: the hold
 * handlers' range and fn 50/14/28 to holdmenu.c, Now Playing's Select and Menu
 * handlers and the three ways back to normal to nowplaying.c, holding Select in
 * Playlists to queue.c (in the hold range). So the check is inline and
 * everything else goes straight back. frogger_vm may hand back another pc,
 * which then goes into the VM too. Entered with B like vis_hook, so the
 * interpreter's lr is never touched; back at 0x9bab4. */
    .global vm_hook
vm_hook:
    ldr     r0, [r4, #32]
    push    {r1}
    ldr     r1, =HM_LO
    cmp     r0, r1
    ldrhs   r1, =HM_HI
    cmphs   r1, r0                  @ in [HM_LO, HM_HI]: hs both times
    bhs     0f
    ldr     r1, =NP_FN_SELECT
    cmp     r0, r1
    ldrne   r1, =NP_FN_RATED
    cmpne   r0, r1
    ldrne   r1, =NP_FN_TIMEOUT
    cmpne   r0, r1
    ldrne   r1, =NP_FN_SCRUBBED
    cmpne   r0, r1
    ldrne   r1, =NP_FN_MENU
    cmpne   r0, r1
    ldrne   r1, =HM_FN_SELECT
    cmpne   r0, r1
    ldrne   r1, =HM_FN_SELECTED
    cmpne   r0, r1
    ldrne   r1, =HM_FN_BACK
    cmpne   r0, r1
    ldrne   r1, =HM_FN_CANCEL
    cmpne   r0, r1
    ldrne   r1, =HM_POPUP_UP
    cmpne   r0, r1
    ldrne   r1, =HM_FN_NP_SELECT
    cmpne   r0, r1
    ldrne   r1, =HM_SCREEN_FWD
    cmpne   r0, r1
    ldrne   r1, =HM_SCREEN_BACK
    cmpne   r0, r1
    ldrne   r1, =HM_FN_VIS_FRAME
    cmpne   r0, r1
    ldrne   r1, =HM_QS_HOLD
    cmpne   r0, r1
    ldrne   r1, =HM_QS_FRAME
    cmpne   r0, r1
    ldrne   r1, =HM_MM_SHOW
    cmpne   r0, r1
    beq     0f
    ldr     r1, =HM_SNIPPET         @ our own bytecode: holdmenu.c picks the way through it
    sub     r1, r0, r1
    cmp     r1, #(HM_SNIPPET_END - HM_SNIPPET)     @ unsigned: below the snippet wraps high
    blo     0f
    ldr     r1, =np_art_dirty       @ or a new cover waits to be drawn (art.c)
    ldrb    r1, [r1]
    cmp     r1, #0
    pop     {r1}
    ldreq   pc, =0x9bab4
    b       1f
0:  pop     {r1}
1:  push    {r1, r2, r3, r12, lr}
    mov     r1, r4
    bl      frogger_vm              @ holdmenu.c
    str     r0, [r4, #32]
    pop     {r1, r2, r3, r12, lr}
    ldr     pc, =0x9bab4

/* 0xc0c68 in 0xc0b30(library, row), which adds a browse list's row (a song,
 * or all of an album's, artist's, playlist's songs) to On-The-Go, on its
 * way out after a successful add (was: ldr r0, [r4]). r4 is the library,
 * r9 the playlist's count before the add. */
    .global queue_add_hook
queue_add_hook:
    push    {r0, r1, r2, r3, r12, lr}
    mov     r0, r4
    mov     r1, r9
    bl      queue_added             @ queue.c
    pop     {r0, r1, r2, r3, r12, lr}
    ldr     r0, [r4]
    bx      lr

/* 0x9106c in the wheel's handler 0x90fe4, where it looks at the step it'll
 * move the list by (was: cmp r4, #0; r4 is the step, r5 the list widget).
 * letter_step may make it the distance to another letter (letters.c); the
 * compare is redone for the code after it. */
    .global letter_hook
letter_hook:
    push    {r0, r1, r2, r3, r12, lr}
    mov     r0, r5
    mov     r1, r4
    bl      letter_step
    mov     r4, r0
    pop     {r0, r1, r2, r3, r12, lr}
    cmp     r4, #0
    bx      lr

/* 0x7998c, the first instruction of the UI object's getter 0x7998c(ui, fourcc,
 * property, row, out*), which list rows ask for their label (was: push {r4-r9,
 * lr}). Notes the property of 'Str ' asks for letters.c. Entered with B like
 * vis_hook; back at 0x79990. */
    .global label_hook
label_hook:
    push    {r12}
    ldr     r12, =0x53747220        @ 'Str '
    cmp     r1, r12
    ldreq   r12, =letter_prop
    streq   r2, [r12]
    pop     {r12}
    push    {r4, r5, r6, r7, r8, sb, lr}
    ldr     pc, =0x79990

/* 0x1fabc, the first instruction of 0x1fabc(obj, element, string, flags), the
 * native side of 0x08de.60, which sets an element's text (was: push {r3, lr}).
 * Notes the screen title's string (element 0x25e7) for letters.c, unless
 * letters.c is setting it. Entered with B like vis_hook; back at 0x1fac0. */
    .global title_hook
title_hook:
    push    {r0, r12}
    ldr     r12, =0x25e7
    cmp     r1, r12
    bne     1f
    ldr     r12, =letter_setting
    ldrb    r0, [r12]
    cmp     r0, #0
    ldreq   r12, =letter_title
    streq   r2, [r12]
1:  pop     {r0, r12}
    push    {r3, lr}
    ldr     pc, =0x1fac0

/* 0xe9664, the first instruction of a function the UI's dispatcher (0x88ee4)
 * calls about every quarter second, on the UI thread (was: push {r4, r5,
 * lr}). letter_tick puts the list's title back once the wheel is still.
 * Entered with B like vis_hook; back at 0xe9668. */
    .global tick_hook
tick_hook:
    push    {r0, r1, r2, r3, r12, lr}
    bl      letter_tick             @ letters.c
    bl      hide_tick               @ hide.c: FroggerHidden, once a database has loaded
    bl      skips_tick              @ skips.c: FroggerSkips, the same
    bl      np_tick                 @ nowplaying.c: a held LCD let go
#ifdef FROGGER_DEBUG
    bl      debug_tick              @ debug.c: the last boot's record, once
#endif
    pop     {r0, r1, r2, r3, r12, lr}
    push    {r4, r5, lr}
    ldr     pc, =0xe9668

/* 0x5e8cc, the first instruction of 0x5e8cc(lib), which deletes the list Now
 * Playing played from (lib+0x44) as something else starts (was: push {r4,
 * lr}). queue_keep spares the queue. Entered with B like vis_hook; back at
 * 0x5e8d0. */
    .global keep_hook
keep_hook:
    push    {r0, r1, r2, r3, r12, lr}
    bl      skips_keep              @ skips.c: the song playing, for the pick
    pop     {r0, r1, r2, r3, r12, lr}
    push    {r0, r1, r2, r3, r12, lr}
    bl      queue_keep              @ queue.c
    pop     {r0, r1, r2, r3, r12, lr}
    push    {r4, lr}
    ldr     pc, =0x5e8d0

/* 0xb7b00, the first instruction of 0xb7b00(player, list, key, flags), which
 * finds the item to play after the one with `key` (was: push {r4-r11, lr}).
 * When queue_next has an On-The-Go item (or says there's none), return that
 * instead. Entered with B like vis_hook; back at 0xb7b04. */
    .global queue_next_hook
queue_next_hook:
    push    {r0, r1, r2, r3, r12, lr}
    bl      queue_next
    cmp     r0, #0
    beq     0f
    cmp     r0, #QUEUE_NO_NEXT      @ none: 0xb7b00 returns 0
    moveq   r0, #0
    add     sp, sp, #4              @ the saved r0
    pop     {r1, r2, r3, r12, pc}   @ return the item to 0xb7b00's caller
0:  pop     {r0, r1, r2, r3, r12, lr}
/* Apple's 0xb7b00 itself, for queue.c: the replaced push, then the rest. */
    .global queue_next_orig
queue_next_orig:
    push    {r4, r5, r6, r7, r8, r9, sl, fp, lr}
    ldr     pc, =0xb7b04

#ifdef FROGGER_DEBUG
/* 0x41e5c, the first instruction of 0x41e5c(frame, kind), which Apple's
 * undefined-instruction, prefetch-abort and data-abort vectors call with
 * r0-r12 and lr pushed (frame) and kind 1, 3 or 4 (was: mov r2,
 * #0xc4000000). Hands crash_note the frame, this mode's spsr and the crashed
 * mode's sp and lr (read by switching to that mode with interrupts off; user
 * mode's through system mode), then goes on into Apple's handler. Entered
 * with B like vis_hook; back at 0x41e60. */
    .global crash_hook
crash_hook:
    push    {r0, r1, r2, r3, r4, r5, r6, r7, r12, lr}
    mrs     r2, spsr
    mrs     r4, cpsr
    and     r3, r2, #0x1f
    cmp     r3, #0x10
    moveq   r3, #0x1f
    orr     r3, r3, #0xc0
    msr     cpsr_c, r3
    mov     r5, sp
    mov     r6, lr
    msr     cpsr_c, r4
    mov     r3, r5
    push    {r6}
    bl      crash_note              @ debug.c
    add     sp, sp, #4
    pop     {r0, r1, r2, r3, r4, r5, r6, r7, r12, lr}
    mov     r2, #0xc4000000
    ldr     pc, =0x41e60
#endif

    .ltorg

/* Resume for long tracks (resume.c): Apple's audiobook bookmark, for long
 * tracks too. */

/* 0xb9354 in 0xb8ed8, which loads a track (was: ldr r0, [sp, #560], the
 * flags 0xb7efc gave, about to be stored at [player+0x2380]; r6 is the track
 * record). resume_flags may add 0x40, the bookmark flag. */
    .global resume_flags_hook
resume_flags_hook:
    push    {r1, r2, r3, r12, lr}
    ldr     r0, [sp, #20 + 560]
    mov     r1, r6
    bl      resume_flags
    pop     {r1, r2, r3, r12, lr}
    bx      lr

/* 0xb9550 in 0xb8ed8: a bookmarked track starts at its bookmark (was: str r0,
 * [r4, #356], the start into [player+0x2164]; r5 is the player). The cmp after
 * it reads r0 again. */
    .global resume_start_hook
resume_start_hook:
    push    {r1, r2, r3, r12, lr}
    mov     r1, r5
    bl      resume_start
    pop     {r1, r2, r3, r12, lr}
    str     r0, [r4, #356]
    bx      lr

/* 0xb903c in 0xb8ed8: the track being left keeps its position as its bookmark
 * (was: str r0, [r6, #96]; r6 is that track's record). */
    .global resume_save_hook
resume_save_hook:
    push    {r1, r2, r3, r12, lr}
    mov     r1, r6
    bl      resume_save
    pop     {r1, r2, r3, r12, lr}
    str     r0, [r6, #96]
    bx      lr

/* 0xf4d6c, the first instruction of 0xf4d6c(lib), which writes the Play Counts
 * file, bookmarks included (was: push {r4-r11, lr}). Entered with B like
 * vis_hook; back at 0xf4d70. */
    .global counts_hook
counts_hook:
    push    {r0, r1, r2, r3, r12, lr}
    bl      resume_flush
    bl      skips_save              @ skips.c: FroggerSkips, at the same moments
    pop     {r0, r1, r2, r3, r12, lr}
    push    {r4, r5, r6, r7, r8, r9, sl, fp, lr}
    ldr     pc, =0xf4d70

    .ltorg

/* Skip counts (skips.c). */

/* 0xb81d4, the first instruction of Next, 0xb81d4(player, flags) (was: push
 * {r4-r10, lr}). skips_next counts the song being left unless flags say it
 * ended. Entered with B like vis_hook; back at 0xb81d8. */
    .global skip_next_hook
skip_next_hook:
    push    {r0, r1, r2, r3, r12, lr}
    bl      skips_next
    pop     {r0, r1, r2, r3, r12, lr}
    push    {r4, r5, r6, r7, r8, r9, sl, lr}
    ldr     pc, =0xb81d8

/* 0xb8eb4, the first instruction of 0xb8eb4(player, item), which loads the
 * item a pick plays (was: push {r3, r4, r5, lr}). skips_pick gets the caller's
 * return address too. Entered with B; back at 0xb8eb8. */
    .global skip_pick_hook
skip_pick_hook:
    push    {r0, r1, r2, r3, r12, lr}
    mov     r2, lr
    bl      skips_pick
    pop     {r0, r1, r2, r3, r12, lr}
    push    {r3, r4, r5, lr}
    ldr     pc, =0xb8eb8

    .ltorg
