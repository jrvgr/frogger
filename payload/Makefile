CROSS   ?= arm-none-eabi-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
NM      := $(CROSS)nm
SIZE    := $(CROSS)size

BUILD   := ../build/payload
# DEBUG=1: the debug record (debug.c), written to FroggerDebug on the next boot.
DEBUG   ?= 0
CFLAGS  := -mcpu=arm7tdmi -marm -Os -std=c99 -Wall -Wextra -Werror \
           -ffreestanding -fno-builtin -fno-common -ffunction-sections \
           $(if $(filter 1,$(DEBUG)),-DFROGGER_DEBUG)
LDFLAGS := -nostdlib -nostartfiles -T payload.lds -Wl,--gc-sections -Wl,--no-warn-rwx-segments -Wl,-Map=$(BUILD)/payload.map

OBJS := $(BUILD)/hooks.o $(BUILD)/hide.o $(BUILD)/settings.o $(BUILD)/art.o $(BUILD)/nowplaying.o $(BUILD)/artist.o $(BUILD)/queue.o $(BUILD)/holdmenu.o $(BUILD)/playlist.o $(BUILD)/letters.o $(BUILD)/browse.o $(BUILD)/resume.o $(BUILD)/skips.o $(BUILD)/battery.o $(BUILD)/disk.o $(BUILD)/flash.o $(BUILD)/lock.o $(BUILD)/tracks.o \
        $(if $(filter 1,$(DEBUG)),$(BUILD)/debug.o)
UNDEFINED := $(if $(filter 1,$(DEBUG)),crash_hook)

all: $(BUILD)/payload.bin $(BUILD)/payload.sym

$(BUILD):
	mkdir -p $@

# Rebuild everything when the flags change (DEBUG on or off).
$(BUILD)/flags: FORCE | $(BUILD)
	@echo '$(CFLAGS)' | cmp -s - $@ || echo '$(CFLAGS)' > $@

$(BUILD)/%.o: %.c hide.h settings.h nowplaying.h queue.h holdmenu.h playlist.h letters.h debug.h browse.h resume.h skips.h battery.h disk.h lock.h tracks.h $(BUILD)/flags | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%.o: %.S hide.h settings.h nowplaying.h queue.h holdmenu.h playlist.h letters.h debug.h browse.h resume.h skips.h battery.h disk.h lock.h tracks.h $(BUILD)/flags | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/payload.elf: $(OBJS) payload.lds
	$(CC) $(CFLAGS) $(LDFLAGS) -Wl,--undefined=mhod_hook,--undefined=mhyp_hook,--undefined=mhip_hook,--undefined=filter_hook,--undefined=browse_hook,--undefined=setting_set_hook,--undefined=setting_get_hook,--undefined=string_hook,--undefined=play_hook,--undefined=vis_hook,--undefined=vm_hook,--undefined=trans_hook,--undefined=queue_add_hook,--undefined=queue_next_hook,--undefined=keep_hook,--undefined=letter_hook,--undefined=label_hook,--undefined=title_hook,--undefined=tick_hook,--undefined=resume_flags_hook,--undefined=resume_start_hook,--undefined=resume_save_hook,--undefined=counts_hook,--undefined=skip_next_hook,--undefined=skip_pick_hook,--undefined=battery_read,--undefined=battery_state,--undefined=lcd_hook,--undefined=drawn_hook,--undefined=disk_reinit_hook,--undefined=disk_read_hook,--undefined=flash_id_hook,--undefined=flash_hold_hook,--undefined=preload_hook,$(foreach u,$(UNDEFINED),--undefined=$(u),)--undefined=settings_menu,--undefined=np_view,--undefined=hm_code,--undefined=hm_popup,--undefined=hm_main $(OBJS) -o $@ -lgcc
	$(SIZE) $@

$(BUILD)/payload.bin: $(BUILD)/payload.elf
	$(OBJCOPY) -O binary -j .text $< $@

$(BUILD)/payload.sym: $(BUILD)/payload.elf
	$(NM) $< > $@

clean:
	rm -rf $(BUILD)

.PHONY: all clean FORCE
