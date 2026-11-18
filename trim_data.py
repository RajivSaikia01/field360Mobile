#!/usr/bin/env python3
"""
Field360 workbook trimmer
=========================
Makes a SMALLER copy of your data workbook, so update_data.py does not run out of memory.

Why it helps: the app only keeps the LAST THREE MONTHS of the ld, dc and field_visit sheets and throws older rows away
after reading them. If your workbook holds a year of daily rows, most of the file is read and then discarded.
This tool removes those old rows first (it keeps one extra month to be safe), so the app shows exactly the same figures.

    python trim_data.py data/my-data.xlsx              (shows the sheets, writes data/my-data-trimmed.xlsx)
    python trim_data.py data/my-data.xlsx --report     (only shows how big each sheet is, writes nothing)
    python trim_data.py data/my-data.xlsx -o small.xlsx
    python trim_data.py data/my-data.xlsx --keep-months 6

Then:  python update_data.py data/my-data-trimmed.xlsx

It needs only Python 3.8+ (nothing to install), reads the file as a stream (small memory, but a 100 MB file still takes
a few minutes), never changes your original, and leaves every other sheet exactly as it is. A row whose date it cannot
read is KEPT, so nothing is lost by mistake.
"""
import argparse, html, os, re, sys, zipfile
from datetime import date, timedelta
import xml.etree.ElementTree as ET
import xml.parsers.expat
from collections import Counter

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

# the sheets the app trims itself (last three months), with the names and date columns it accepts
TARGETS = {
    "ld": (["ld", "disbursement", "loan_disbursement"], ["as_of"]),
    "dc": (["dc", "demand_collection", "demand_vs_collection", "collection"],
           ["date", "collection_date", "demand_date", "business_date", "as_on_date", "as_on", "txn_date", "as_of"]),
    "field_visit": (["field_visit", "field_visits", "fieldvisit", "visits"], ["visit_date", "date", "visited_on"]),
}
BIG = 1800000000          # only a sheet larger than this needs the zip64 format (and Excel-reading libraries such as the app's do not all support it)
MONS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
ROW_RE = re.compile(rb"<row\b[^>]*?(?:/>|>.*?</row>)", re.S)
ROWR_RE = re.compile(rb'(<row\b[^>]*?\br=")(\d+)(")')
CELLR_RE = re.compile(rb'(<c\b[^>]*?\br=")([A-Z]+)(\d+)(")')
DIM_RE = re.compile(rb'(<dimension\b[^>]*?ref="[A-Z]+\d+:[A-Z]+)(\d+)(")')
CELL_RE = re.compile(rb"<c\b([^>]*?)(?:/>|>(.*?)</c>)", re.S)
ATTR_RE = re.compile(rb'\b([a-zA-Z:]+)="([^"]*)"')


def key(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def mb(n):
    return "%.1f MB" % (n / 1048576.0)


def need_mb(open_bytes):
    """memory Node needs to read a sheet of this size: about 25 times its size when opened (measured), rounded up"""
    return int(open_bytes / 1048576.0 * 25 / 100 + 1) * 100 + 400


def col_of(ref):
    m = re.match(rb"([A-Z]+)", ref)
    return m.group(1) if m else b""


def read_workbook(z):
    """sheet name -> part name, and the date system"""
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {}
    for r in rels.findall("{%s}Relationship" % NS_PKG):
        t = r.get("Target")
        t = t.lstrip("/") if t.startswith("/") else "xl/" + t
        target[r.get("Id")] = t
    sheets = []
    for s in wb.iter("{%s}sheet" % NS_MAIN):
        rid = s.get("{%s}id" % NS_REL)
        if rid in target:
            sheets.append((s.get("name"), target[rid]))
    pr = wb.find("{%s}workbookPr" % NS_MAIN)
    d1904 = bool(pr is not None and (pr.get("date1904") or "").lower() in ("1", "true"))
    return sheets, d1904


def row_iter(z, part, chunk=1 << 22):
    """yield (kind, bytes): ('head', text before the first row), ('row', one row), ('tail', text after the last row)"""
    buf = b""
    started = False
    with z.open(part) as f:
        while True:
            data = f.read(chunk)
            buf += data
            if not started:
                i = buf.find(b"<sheetData")
                if i < 0:
                    if not data:
                        yield ("head", buf); return
                    continue
                j = buf.find(b">", i)
                if j < 0:
                    continue
                if buf[j - 1:j + 1] == b"/>":          # an empty sheet
                    yield ("head", buf[:j + 1]); yield ("tail", buf[j + 1:]); return
                yield ("head", buf[:j + 1]); buf = buf[j + 1:]; started = True
            last = 0
            for m in ROW_RE.finditer(buf):
                yield ("row", m.group(0)); last = m.end()
            buf = buf[last:]
            k = buf.find(b"</sheetData>")
            if k >= 0:
                yield ("tail", buf[k:]); return
            if not data:
                yield ("tail", buf); return


def cells(row):
    for m in CELL_RE.finditer(row):
        at = dict(ATTR_RE.findall(m.group(1)))
        yield at.get(b"r", b""), at.get(b"t", b""), m.group(2) or b""


def cell_text(t, inner):
    """('s', index) for a shared string, ('v', text) otherwise"""
    if t == b"s":
        m = re.search(rb"<v>(\d+)</v>", inner)
        return ("s", int(m.group(1))) if m else ("v", "")
    if t == b"inlineStr":
        return ("v", html.unescape(b"".join(re.findall(rb"<t[^>]*>(.*?)</t>", inner, re.S)).decode("utf-8", "replace")))
    m = re.search(rb"<v>(.*?)</v>", inner, re.S)
    v = html.unescape(m.group(1).decode("utf-8", "replace")) if m else ""
    return ("n" if t in (b"", b"n") else "v", v)


def load_shared(z, wanted):
    """only the shared strings we need, by index (streamed: nothing else is kept)"""
    out = {}
    if not wanted or "xl/sharedStrings.xml" not in z.namelist():
        return out
    st = {"i": -1, "t": False, "rph": 0, "buf": []}
    SI, T, RPH = "{%s}si" % NS_MAIN, "{%s}t" % NS_MAIN, "{%s}rPh" % NS_MAIN

    def start(tag, attrs):
        if tag == SI:
            st["i"] += 1; st["buf"] = []
        elif tag == RPH:
            st["rph"] += 1
        elif tag == T:
            st["t"] = True

    def end(tag):
        if tag == SI:
            if st["i"] in wanted:
                out[st["i"]] = "".join(st["buf"])
        elif tag == RPH:
            st["rph"] -= 1
        elif tag == T:
            st["t"] = False

    def data(x):
        if st["t"] and not st["rph"] and st["i"] in wanted:
            st["buf"].append(x)
    p = xml.parsers.expat.ParserCreate(namespace_separator="}")
    # expat gives "uri}local"; rebuild the "{uri}local" form used above
    p.StartElementHandler = lambda tag, attrs: start("{" + tag if "}" in tag else tag, attrs)
    p.EndElementHandler = lambda tag: end("{" + tag if "}" in tag else tag)
    p.CharacterDataHandler = data
    with z.open("xl/sharedStrings.xml") as f:
        p.ParseFile(f)
    return out


def check_xml(z, part):
    """is this part well formed? (streamed, so a big sheet costs no memory)"""
    p = xml.parsers.expat.ParserCreate()
    with z.open(part) as f:
        p.ParseFile(f)


def parse_day(kind, v, d1904, fmt):
    """a date from a cell, the way the app reads it. Returns a date or None"""
    try:
        if kind == "n" or re.fullmatch(r"\d{5}(\.\d+)?", str(v).strip()):
            x = float(v)
            if 30000 < x < 80000:
                return date(1899, 12, 30) + timedelta(days=int(x) + (1462 if d1904 else 0))
            return None
        s = str(v).strip()
        if not s or s.lower() in ("nan", "null", "none", "na", "n/a", "-"):
            return None
        m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"(\d{1,2})[-/. ]([A-Za-z]{3,9})[-/. ,]+(\d{2,4})", s)
        if m:
            mo = MONS.get(m.group(2)[:3].lower())
            if mo is None:
                return None
            y = int(m.group(3)); y = y + 2000 if y < 100 else y
            return date(y, mo + 1, int(m.group(1)))
        m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
        if m:
            a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3)); y = y + 2000 if y < 100 else y
            return date(y, a, b) if fmt == "mdy" else date(y, b, a)
    except (ValueError, OverflowError):
        return None
    return None


def header_of(z, part):
    """the header cells of the first row: [(column letters, ('s', idx) | ('v', text))]"""
    for kind, data in row_iter(z, part):
        if kind == "row":
            return [(col_of(ref), cell_text(t, inner)) for ref, t, inner in cells(data)]
    return []


def count_rows(z, part):
    n = 0; tail = b""
    with z.open(part) as f:
        while True:
            b = f.read(1 << 22)
            if not b:
                break
            b = tail + b
            n += len(re.findall(rb"<row[ >/]", b[:-4])); tail = b[-4:]
    n += len(re.findall(rb"<row[ >/]", tail))
    return n


def renumber(row, n):
    """give a kept row its new row number, so the new sheet has no gaps"""
    if ROWR_RE.search(row):
        row = ROWR_RE.sub(lambda m: m.group(1) + b"%d" % n + m.group(3), row, count=1)
    else:
        row = row.replace(b"<row", b'<row r="%d"' % n, 1)
    return CELLR_RE.sub(lambda m: m.group(1) + m.group(2) + b"%d" % n + m.group(4), row)


def date_token(row, col):
    for ref, t, inner in cells(row):
        if col_of(ref) == col:
            return cell_text(t, inner)
    return None


def main():
    ap = argparse.ArgumentParser(description="Make a smaller copy of the Field360 workbook (old rows of ld, dc and field_visit removed).")
    ap.add_argument("xlsx", help="the data workbook (.xlsx)")
    ap.add_argument("-o", "--output", help="where to write the smaller copy (default: <name>-trimmed.xlsx next to it)")
    ap.add_argument("--keep-months", type=int, default=4, help="months of rows to keep, counted back from the latest date (default 4; the app uses 3)")
    ap.add_argument("--report", action="store_true", help="only list the sheets and their sizes; write nothing")
    ap.add_argument("--force", action="store_true", help="overwrite the output file if it exists")
    a = ap.parse_args()
    if a.keep_months < 3:
        print("--keep-months must be at least 3, because the app uses the last three months."); return 2
    src = a.xlsx
    if not os.path.isfile(src):
        print("File not found: %s" % src); return 2
    out = a.output or os.path.splitext(src)[0] + "-trimmed.xlsx"
    if os.path.abspath(out) == os.path.abspath(src):
        print("The output must be a different file from the original."); return 2
    try:
        z = zipfile.ZipFile(src)
        sheets, d1904 = read_workbook(z)
    except Exception as e:
        print("This does not look like an .xlsx file (%s). Save it from Excel as 'Excel Workbook (*.xlsx)' and try again." % e); return 2
    print("Field360 workbook trimmer\n  File: %s (%s)\n" % (src, mb(os.path.getsize(src))))
    print("  %-26s %12s %12s %16s" % ("Sheet", "Size (open)", "Rows", "Memory to read"))
    plan = {}
    for name, part in sheets:
        k = key(name); tgt = None
        for tname, (names, dcols) in TARGETS.items():
            if k in names:
                tgt = (tname, dcols)
        rows = count_rows(z, part)
        print("  %-26s %12s %12s %16s%s" % (name[:26], mb(z.getinfo(part).file_size), format(max(rows - 1, 0), ","), "~%s MB" % format(need_mb(z.getinfo(part).file_size), ","), "   <- can be trimmed" if tgt else ""))
        if tgt:
            plan[part] = {"name": name, "dcols": tgt[1], "rows": max(rows - 1, 0)}
    big = sorted(((z.getinfo(p).file_size, n) for n, p in sheets), reverse=True)
    print("\n  Heaviest: " + ", ".join("%s %s" % (n, mb(b)) for b, n in big[:3]))
    top = need_mb(big[0][0]) if big else 0
    print("  Reading the heaviest sheet (%s) needs about %s MB of memory. Updating one sheet at a time, use  --memory %d  or more." % (big[0][1], format(top, ","), top))
    print("  Whole file at once needs a little more, as the sheets are read together.")
    if a.report:
        print("\n(report only: nothing was written)"); return 0
    if not plan:
        print("\nNo ld, dc or field_visit sheet was found, so there is nothing this tool can trim.\nThe heavy sheet is listed above: remove columns or rows you do not need from it in Excel."); return 0
    # the date column of each sheet
    hdrs = {part: header_of(z, part) for part in plan}
    need = set(c[1] for h in hdrs.values() for _col, c in h if c[0] == "s")
    sstr = load_shared(z, need)
    for part, pl in plan.items():
        names = {}
        for colb, c in hdrs[part]:
            names[key(sstr.get(c[1], "") if c[0] == "s" else c[1])] = colb
        found = next((d for d in pl["dcols"] if d in names), None)
        pl["col"] = names.get(found) if found else None; pl["colname"] = found
    # pass 1 per sheet: which dates occur (a few thousand different ones at most)
    res = {}
    for part, pl in plan.items():
        if not pl["col"]:
            print("\n  %s: no date column found (looked for %s), so it is left as it is." % (pl["name"], ", ".join(pl["dcols"][:3]))); continue
        hist = Counter(); first = True
        for kind, data in row_iter(z, part):
            if kind != "row":
                continue
            if first:
                first = False; continue
            hist[date_token(data, pl["col"])] += 1
        sstr.update(load_shared(z, set(t[1] for t in hist if t and t[0] == "s") - set(sstr)))
        def as_cell(t):
            k, v = t
            return ("v", sstr.get(v, "")) if k == "s" else (k, v)
        dmy = mdy = slash = False
        for t in hist:
            if t is None:
                continue
            k, v = as_cell(t)
            m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", str(v).strip()) if k == "v" else None
            if m:
                slash = True; dmy = dmy or int(m.group(1)) > 12; mdy = mdy or int(m.group(2)) > 12
        fmt = "mdy" if (mdy and not dmy) else "dmy"
        day = {}; bad = total = 0; mx = mn = None
        for t, n in hist.items():
            total += n
            d = parse_day(*as_cell(t), d1904, fmt) if t is not None else None
            day[t] = d
            if d is None:
                bad += n; continue
            mx = d if (mx is None or d > mx) else mx; mn = d if (mn is None or d < mn) else mn
        if mx is None or bad > total * 0.5:
            print("\n  %s: more than half of the dates in '%s' could not be read, so it is left as it is." % (pl["name"], pl["colname"])); continue
        mq = mx.year * 12 + mx.month - 1; lo = mq - (a.keep_months - 1)
        keep = set(t for t, d in day.items() if d is None or (d.year * 12 + d.month - 1) >= lo)
        res[part] = {"keep": keep, "total": total, "bad": bad, "kept": 1 + sum(n for t, n in hist.items() if t in keep)}
        print("\n  %s: dates from %s to %s (column '%s'%s), %s rows. Keeping the last %d months, from %s." % (
            pl["name"], mn, mx, pl["colname"], ((", read " + ("month" if fmt == "mdy" else "day") + " first") if slash else ""), format(total, ","), a.keep_months, date(lo // 12, lo % 12 + 1, 1)))
        if bad:
            print("    %s rows have a date the tool cannot read. They are kept, so the app can report them." % format(bad, ","))
        if mx > date.today() + timedelta(days=400):
            print("  WARNING: the latest date in %s is far in the future (%s). Check for a mistyped date before trusting this." % (pl["name"], mx))
    if not res:
        print("\nNothing to trim."); return 0
    if os.path.exists(out) and not a.force:
        print("\n%s already exists. Use --force to overwrite it, or -o to choose another name." % out); return 2
    # pass 2: write the new workbook
    print("\n  Writing %s ..." % out)
    kept_total = {}
    tmp = out + ".part"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zo:
            for zi in z.infolist():
                if zi.filename not in res:
                    with z.open(zi) as fi, zo.open(zi.filename, "w", force_zip64=zi.file_size > BIG) as fo:
                        while True:
                            b = fi.read(1 << 22)
                            if not b:
                                break
                            fo.write(b)
                    continue
                pl = plan[zi.filename]; keep = res[zi.filename]["keep"]; kept = 0; first = True; newn = 1
                with zo.open(zi.filename, "w", force_zip64=zi.file_size > BIG) as fo:
                    for kind, data in row_iter(z, zi.filename):
                        if kind == "head":
                            fo.write(DIM_RE.sub(lambda m: m.group(1) + b"%d" % res[zi.filename]["kept"] + m.group(3), data, count=1)); continue
                        if kind != "row":
                            fo.write(data); continue
                        if first:
                            first = False; fo.write(renumber(data, 1)); continue
                        if date_token(data, pl["col"]) in keep:
                            newn += 1; fo.write(renumber(data, newn)); kept += 1
                kept_total[pl["name"]] = (res[zi.filename]["total"], kept)
        with zipfile.ZipFile(tmp) as zc:
            bad_member = zc.testzip()
            if bad_member:
                raise RuntimeError("the new file is damaged at " + bad_member)
            for part in res:
                check_xml(zc, part)
        os.replace(tmp, out)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        print("\nSTOPPED: %s. Your original file was not changed and no new file was kept." % e); return 1
    print("\n  Rows kept:")
    for n, (t, k) in kept_total.items():
        print("    %-14s %s of %s  (%s removed)" % (n, format(k, ","), format(t, ","), format(t - k, ",")))
    print("\nDone: %s  ->  %s  (%s)\nNow run:  python update_data.py %s" % (mb(os.path.getsize(src)), mb(os.path.getsize(out)), out, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
