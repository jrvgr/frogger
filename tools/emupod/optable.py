import struct, json
from ipod3g import Pod, W
p = Pod(boot_us=3_000_000)
raw = p.m.mem_read(0x373ab0, 4 * 256)
ops = {}
for op in range(256):
    b0, b1, h = struct.unpack_from("<BBH", raw, 4 * op)
    if b0 or b1 or h:
        ops[op] = (b0, b1, h)
        print("%02x: b0=%02x (lo %d, hi %d) b1=%02x h=%04x kind=%d" % (op, b0, ((b0 & 15) ^ 8) - 8, ((b0 >> 4) ^ 8) - 8, b1, h, h & 15))
json.dump({op: v for op, v in ops.items()}, open(W + "/optable.json", "w"))
