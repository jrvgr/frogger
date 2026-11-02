"""Start Tone A from Songs and screenshot the Now Playing screen over time; audio stats."""
from ipod3g import Pod
p = Pod(); p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
p.press("select", after_us=100_000)
for i, t in enumerate([1, 3, 6]):
    p.run(1_000_000 if i == 0 else 2_000_000 if i == 1 else 3_000_000)
    s = p.m.stats()
    print("t=%.1fs fiqs=%d underruns=%d audio_on=%s ata_reads=%d" % (s["now_us"] / 1e6, s["audio_fiqs"], p.m.underruns(), p.m.audio_on(), s["ata_reads"]))
    p.shot("np_%d.png" % i, 2)
