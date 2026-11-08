#!/usr/bin/env python3
"""CI's test and coverage summaries, in Markdown (.github/workflows/ci.yml). Standard library only:
the portable job runs it with a plain Python.

    report.py junit TITLE FILE.xml [--checks]   # passed/failed/skipped; --checks: the emupod table
    report.py coverage COVERAGE.json [JUNIT_DIR] # tools/ coverage and the payload's emupod checks

Output goes to $GITHUB_STEP_SUMMARY (appended) when it's set, else to stdout; -o FILE writes FILE.
"""
import argparse, json, os, re, sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/emupod"))
import runtests  # noqa: E402  FEATURES, UNCHECKED

ICON = {"passed": "✅ passed", "failed": "❌ failed", "skipped": "⏭️ skipped"}


def cases(path):
    """(name, file, result, seconds) for each testcase of a pytest --junitxml file."""
    for tc in ET.parse(path).getroot().iter("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            result = "failed"
        elif tc.find("skipped") is not None:
            result = "skipped"
        else:
            result = "passed"
        yield tc.get("name"), tc.get("file"), result, float(tc.get("time") or 0)


def check_name(name):
    m = re.fullmatch(r"test_check\[(\w+)\]", name or "")
    return m and m.group(1)


def junit(a):
    rows = list(cases(a.file)) if Path(a.file).exists() else []
    n = {r: sum(1 for c in rows if c[2] == r) for r in ICON}
    # The run's own time (with -n the tests overlap, so not their sum).
    secs = max((float(s.get("time") or 0) for s in ET.parse(a.file).getroot().iter("testsuite")),
               default=0) if rows else 0
    out = [f"### {a.title}", ""]
    if not rows:
        out.append(f"No results ({a.file} is missing: the job stopped before its tests).")
    else:
        mark = "❌" if n["failed"] else "✅"
        out.append(f"{mark} **{n['passed']} passed**, {n['failed']} failed, {n['skipped']} skipped, "
                   f"in {secs:.0f} s")
    failed = [c for c in rows if c[2] == "failed"]
    if failed:
        out += ["", "Failed:"] + [f"- `{c[1]}`: `{c[0]}`" for c in failed]
    if a.checks and rows:
        out += ["", "| Check | Feature | Result | Duration |", "| --- | --- | --- | ---: |"]
        for name, _, result, s in sorted(rows, key=lambda c: -c[3]):
            check = check_name(name) or name
            feature = runtests.FEATURES.get(check, ("",))[0]
            out.append(f"| `{check}` | {feature} | {ICON[result]} | {s:.0f} s |")
    return "\n".join(out) + "\n"


def coverage(a):
    cov = json.loads(Path(a.json).read_text())
    t = cov["totals"]
    out = ["## Coverage of the Python tools", "",
           f"**{t['percent_covered']:.0f}%** of `tools/` ({t['covered_lines']} of {t['num_statements']} "
           "statements; `tools/re` and `tools/emupod/probes` left out), from the build and emulator jobs' "
           "pytest runs, emupod checks included.", "",
           "<details><summary>Per file</summary>", "",
           "| File | Statements | Missed | Covered |", "| --- | ---: | ---: | ---: |"]
    for path, f in sorted(cov["files"].items()):
        s = f["summary"]
        rel = os.path.relpath(path, ROOT) if os.path.isabs(path) else path
        out.append(f"| `{rel}` | {s['num_statements']} | {s['missing_lines']} | {s['percent_covered']:.0f}% |")
    out += ["", "</details>", ""]

    # The payload: C in the emulator, which coverage.py can't measure. Which features a check covers.
    results = {}
    if a.junit and Path(a.junit).is_dir():
        for x in Path(a.junit).rglob("*.xml"):
            for name, _, result, s in cases(x):
                if check_name(name):
                    results[check_name(name)] = f"{ICON[result]} ({s:.0f} s)"
    out += ["## The payload's emupod checks", "",
            "The payload is C running in the emulator, out of coverage.py's reach. What each emupod "
            "check covers (`tools/emupod/runtests.py`, `FEATURES`):", "",
            "| Feature | Check | Payload files | Result |", "| --- | --- | --- | --- |"]
    for check, (feature, files) in runtests.FEATURES.items():
        out.append(f"| {feature} | `{check}.py` | {', '.join(f'`{f}`' for f in files) or '—'} | "
                   f"{results.get(check, 'not run')} |")
    if runtests.UNCHECKED:
        out += ["", "**No check yet** (shown in screenshots only): "
                + "; ".join(f"{f} (`{s}`)" for f, s in runtests.UNCHECKED.items()) + "."]
    checked = {f for _, files in runtests.FEATURES.values() for f in files}
    untouched = sorted(p.name for p in (ROOT / "payload").glob("*.c") if p.name not in checked)
    if untouched:
        out += ["", "**Payload files no check goes through:** " + ", ".join(f"`{f}`" for f in untouched) + "."]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", help="write here instead of $GITHUB_STEP_SUMMARY or stdout")
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("junit")
    j.add_argument("title")
    j.add_argument("file")
    j.add_argument("--checks", action="store_true", help="a table of the emupod checks")
    c = sub.add_parser("coverage")
    c.add_argument("json", help="from `coverage json`")
    c.add_argument("junit", nargs="?", help="a folder of --junitxml files, for the checks' results")
    a = ap.parse_args()
    text = junit(a) if a.cmd == "junit" else coverage(a)
    if a.o:
        Path(a.o).write_text(text, encoding="utf-8")
    elif os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
