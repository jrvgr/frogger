"""Read popuptrace.json: per step, the bytecode it ran (by function) and, under each send, the
native functions entered before the next instruction (call order, with r0-r3 and lr).

    popupsends.py STEP [--all]     # STEP: hold, clear_open, clear_cancel, save_open, save_confirm
Without --all, sends that enter nothing native are left out."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import json, struct, sys
from ipod3g import W
ROOT = W.rsplit("/build/", 1)[0]
img = open(ROOT + "/build/fw/osos.img", "rb").read()
CODE, TABLE, NFN = 0x192948, 0x192034, 580
offs = struct.unpack_from("<%dI" % (NFN + 1), img, TABLE)
VM = 0x9bab8


def fn_of(bc):
    for i in range(NFN):
        if offs[i] <= bc < offs[i + 1]:
            return i, struct.unpack_from("<H", img, CODE + offs[i])[0]
    return None, None


step, everything = sys.argv[1], "--all" in sys.argv
log = json.load(open(W + "/popuptrace.json"))[step]
cur_fn, pending, natives = None, None, []


def flush():
    if pending and (natives or everything):
        print("   %5x  %s" % pending)
        for n in natives:
            print("            -> %x(r0=%x r1=%x r2=%x r3=%x) lr=%x" % n)


for t, pc, r0, r1, r2, r3, lr, vmpc in log:
    if pc != VM:
        if pending:
            natives.append((pc, r0, r1, r2, r3, lr))
        continue
    flush(); pending, natives = None, []
    bc = vmpc - CODE
    if not 0 <= bc < offs[NFN] - 0:
        continue
    i, fid = fn_of(bc)
    if i != cur_fn:
        cur_fn = i; print("fn %s (id %#x)" % (i, fid or 0))
    op = img[vmpc]
    if op == 0x3a:
        pending = (bc, img[vmpc:vmpc + 3].hex(" "))
flush()
