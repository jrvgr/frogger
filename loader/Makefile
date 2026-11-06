CROSS   ?= arm-none-eabi-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
SIZE    := $(CROSS)size

BUILD   := ../build/loader
# Patches to leave out, by name: make DISABLE="darkmode hideplaylists"
DISABLE ?=
# DEBUG=1: the payload's debug record (payload/debug.c)
DEBUG   ?= 0
CFLAGS  := -mcpu=arm7tdmi -marm -Os -std=c99 -Wall -Wextra -Werror \
           -ffreestanding -fno-builtin -fno-common -ffunction-sections \
           $(foreach p,$(DISABLE),-DFROGGER_DISABLE_$(p))
INCLUDE := -I$(BUILD) -I../payload
LDFLAGS := -nostdlib -nostartfiles -T loader.lds -Wl,--gc-sections -Wl,--no-warn-rwx-segments -Wl,-Map=$(BUILD)/frogger-loader.map

OBJS := $(BUILD)/crt0.o $(BUILD)/main.o $(BUILD)/patches.o $(BUILD)/settings.o $(BUILD)/nowplaying.o

all: $(BUILD)/frogger-loader.bin

$(BUILD):
	mkdir -p $@

$(BUILD)/%.o: %.c pp5002.h patches.h | $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDE) -c $< -o $@

$(BUILD)/patches.o $(BUILD)/settings.o $(BUILD)/nowplaying.o: $(BUILD)/payload.h ../payload/settings.h ../payload/nowplaying.h

# The resident payload and its hooks (payload/, tools/mkpayload.py).
$(BUILD)/payload.h: FORCE | $(BUILD)
	$(MAKE) -C ../payload DEBUG=$(DEBUG)
	python3 ../tools/mkpayload.py --build ../build

$(BUILD)/%.o: %.S | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/frogger-loader.elf: $(OBJS) loader.lds
	$(CC) $(CFLAGS) $(LDFLAGS) $(OBJS) -o $@ -lgcc
	$(SIZE) $@

# Apple's boot loads the loader right after osos (0x346368); it must end below
# the debug record (payload/debug.h), which has to survive a reset.
$(BUILD)/frogger-loader.bin: $(BUILD)/frogger-loader.elf
	$(OBJCOPY) -O binary $< $@
	@test $$((0x346368 + $$(wc -c < $@))) -le $$((0x358000)) || { echo "loader overlaps the debug record (payload/debug.h)"; rm $@; exit 1; }

clean:
	rm -rf $(BUILD)

.PHONY: all clean FORCE
