"""Drive stock 2.3 (iPod 3G) in the scratch emupod: buttons, wheel, screenshots.

    from ipod3g import Pod
    p = Pod()                 # boots to the first-run Language menu (~9 s emulated)
    p.press("select")         # English -> main menu
    p.scroll(+3)              # down three items
    p.shot("menu.png")

All inputs are GPIOA pins, active low except Hold:
  bit 0 right/next, 1 select, 2 play/pause, 3 left/previous, 4 menu,
  bit 5 Hold (stock 2.3 reads HIGH as Hold on and then drops every key),
  bits 7:6 the wheel, a quadrature pair (bit 7 is the high bit).
"""
import os, sys
from pathlib import Path

os.environ.setdefault("EMUPOD_ENTRY", "0x28000000")
os.environ.setdefault("EMUPOD_IDE_IRQ", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "third_party/emupod"))
from emupod import emu

W = str(ROOT / "build/emupod-work")        # test cards, screenshots, scratch output
OSOS = str(ROOT / "build/fw/osos.img")
BUTTONS = {"right": 0x01, "next": 0x01, "select": 0x02, "play": 0x04,
           "left": 0x08, "prev": 0x08, "menu": 0x10}
HOLD = 0x20
WHEEL_LO, WHEEL_HI = 0x40, 0x80
GRAY = [0, 1, 3, 2]          # wheel states (hi<<1 | lo) in order; walking backwards scrolls down


class Pod:
    def __init__(self, osos=OSOS, disk=W + "/music-card.img", boot_us=9_000_000, persist=False):
        """persist=True writes the firmware's disk writes back into `disk` (use a copy)."""
        self.e = emu.open(emu.Config(osos=osos, disk=disk, disk_persist=persist))
        self.m = self.e._m
        self.hold(False)
        self.e.run_for(boot_us)
        self._wheel = GRAY.index(self._wheel_state())

    def run(self, us):
        self.e.run_for(us)

    def _set(self, mask, level):
        if bool(self.m.pin(0, mask)) != bool(level):
            self.m.set_pin(0, mask, bool(level))
            self.m.edge(0, mask)

    def hold(self, on):
        self._set(HOLD, on)

    def press(self, name, hold_us=150_000, after_us=1_000_000):
        mask = BUTTONS[name]
        self._set(mask, False)
        self.e.run_for(hold_us)
        self._set(mask, True)
        self.e.run_for(after_us)

    def _wheel_state(self):
        return (2 if self.m.pin(0, WHEEL_HI) else 0) | (1 if self.m.pin(0, WHEEL_LO) else 0)

    def wheel(self, steps, gap_us=4_000, after_us=800_000):
        """Raw quadrature steps: negative scrolls down (clockwise), positive up."""
        d = 1 if steps > 0 else -1
        for _ in range(abs(steps)):
            self._wheel = (self._wheel + d) % 4
            s = GRAY[self._wheel]
            self._set(WHEEL_HI, s & 2)
            self._set(WHEEL_LO, s & 1)
            self.e.run_for(gap_us)
        self.e.run_for(after_us)

    def scroll(self, items, max_steps=16, gap_us=30_000):
        """Move the highlight by menu items (positive is down): step the wheel until the screen
        changes, once per item. 2.3 moves one item per 4-6 steps, more for the first."""
        d = -1 if items > 0 else 1
        for _ in range(abs(items)):
            before = self.settle()
            for _ in range(max_steps):
                self.wheel(d, gap_us=0, after_us=gap_us)
                if self.screen() != before:
                    break
            else:
                return False          # end of the list, or not a list
        self.e.run_for(300_000)
        return True

    def screen(self):
        """The 160 x 128 levels now. (emupod's make_screen() starts blank and only fills in when
        there were new writes since the last update, so a shot after an idle stretch comes out empty.)"""
        self.m.lcd_update()
        return bytes(self.m.lcd_px())

    def settle(self, step_us=200_000, tries=25):
        """Run until the screen stops changing; returns it."""
        s = self.screen()
        for _ in range(tries):
            self.e.run_for(step_us)
            t = self.screen()
            if t == s:
                break
            s = t
        return s

    def shot(self, name, scale=2):
        from emupod.recording import png
        path = name if os.path.isabs(name) else os.path.join(W, name)
        open(path, "wb").write(png(self.screen(), scale))
        return path
