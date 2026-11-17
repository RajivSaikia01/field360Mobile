#!/usr/bin/env python3
"""
Field360 data updater
=====================
Puts the data from ONE Excel file (the Field360 data workbook) inside the app's HTML files,
so the app opens already showing that data, for example on a GitHub Pages site.

    python update_data.py                      (uses the only .xlsx in the "data" folder or next to this script)
    python update_data.py data/field360-data.xlsx
    python update_data.py my.xlsx --check      (only checks the file, changes nothing)
    python update_data.py my.xlsx --html index.html field.html
    python update_data.py my.xlsx --yes        (do not ask for confirmation)
    python update_data.py my.xlsx --backup     (keep a .bak copy of each updated file)

What it needs:  Python 3.8+ (nothing to install) and Node.js (https://nodejs.org, the LTS version).
How it works:   the app's OWN loader (inside the HTML file) reads the Excel file, so the data is read exactly as
                the app reads it when you choose the file by hand. The result replaces the data in the HTML files.
                Every sheet in the Excel file replaces what was there: a sheet that is empty or missing is not
                carried over from the old data (the app then shows its built-in sample figures for it).
Privacy:        the data becomes part of the HTML files. Anyone who can open those files can read it.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ENGINE_JS = r''''use strict';
/* Field360 data engine. It runs the app's OWN code (the Excel reader and the loaders inside the HTML file) in Node.js,
   so the data is read exactly as the app reads it when someone chooses the file by hand.
   usage:  node engine.js parse  <app.html> <data.xlsx> <label> <out.json>
           node engine.js verify <app.html> <out.json>                                              */
const fs=require('fs'), vm=require('vm');
const mode=process.argv[2], htmlPath=process.argv[3];
function fail(msg,out,extra){ const o=Object.assign({ok:false,error:String(msg)},extra||{}); if(out) fs.writeFileSync(out,JSON.stringify(o)); else console.log(JSON.stringify(o)); process.exit(0); }
let html; try{ html=fs.readFileSync(htmlPath,'utf8'); }catch(e){ fail('Cannot read '+htmlPath+': '+e.message, process.argv[mode==='parse'?6:4]); }
const blocks=(html.match(/<script>[\s\S]*?<\/script>/g)||[]).map(function(s){ return s.replace(/^<script>|<\/script>$/g,''); });
const lib=blocks.filter(function(b){ return /SheetJS/.test(b.slice(0,300)); })[0], app=blocks.filter(function(b){ return b.indexOf('function allParseWorkbook')>=0; })[0], pre=blocks.filter(function(b){ return b.indexOf('UI acceptance build')>=0; })[0];
const OUT=process.argv[mode==='parse'?6:4];
if(!lib||!app) fail('This does not look like a Field360 app file (the Excel reader or the loaders were not found).',OUT);
function makeEnv(withPreload){
  const els={}, ls={}; let now=false;
  const el=function(id){ return {id:id,classList:{add:function(){},remove:function(){},contains:function(){return false}},style:{},innerHTML:'',textContent:'',className:'',value:'',options:[],setAttribute:function(){},removeAttribute:function(){},getAttribute:function(){return ''},querySelector:function(){return null},querySelectorAll:function(){return []},appendChild:function(){},addEventListener:function(){},scrollTop:0,children:[],click:function(){}}; };
  const win={addEventListener:function(){},innerWidth:390,innerHeight:844,name:'',location:{search:''}};
  const ctx={console:{warn:function(){},log:function(){}},setTimeout:function(f){ if(now) f(); return 0; },clearTimeout:function(){},window:win,location:{reload:function(){},search:''},
    localStorage:{getItem:function(k){ return k in ls?ls[k]:null; },setItem:function(k,v){ ls[k]=v; },removeItem:function(k){ delete ls[k]; }},
    sessionStorage:{getItem:function(){ return null; },setItem:function(){}},
    document:{getElementById:function(id){ return els[id]||(els[id]=el(id)); },querySelectorAll:function(){ return []; },querySelector:function(){ return null; },addEventListener:function(){},removeEventListener:function(){},body:{className:'',classList:{add:function(){}}},documentElement:{style:{setProperty:function(){}}},createElement:function(){ return el('x'); }}};
  vm.createContext(ctx);
  if(withPreload&&pre) vm.runInContext(pre,ctx);
  vm.runInContext(lib,ctx);
  vm.runInContext(app+';this.T={allParseWorkbook:allParseWorkbook,allApply:allApply,X:X,GEO:GEO,FT:FT,LD:LD,BPA:BPA,BPH:BPH,APD:APD,DCD:DCD,geoStoreGet:geoStoreGet,get NODES(){return NODES},get TODAY(){return TODAY}};',ctx);
  return {ctx:ctx,T:ctx.T,ls:ls,win:win,go:function(){ now=true; }};
}
function iso(d){ return new Date(d*864e5).toISOString().slice(0,10); }
if(mode==='parse'){
  const xlsx=process.argv[4], label=process.argv[5]||'data.xlsx';
  let E; try{ E=makeEnv(false); }catch(e){ fail('The app code in '+htmlPath+' could not be started: '+e.message,OUT); }
  let wb; try{ wb=E.ctx.XLSX.read(new Uint8Array(fs.readFileSync(xlsx)),{type:'array'}); }catch(e){ fail('This file could not be read as Excel: '+e.message,OUT); }
  let P; try{ P=E.T.allParseWorkbook(wb,label); }catch(e){ fail('The file could not be checked: '+e.message,OUT); }
  const items=P.items.map(function(it){ const rep=(it.res&&it.res.rep)||{}; return {key:it.key,title:it.title,sheet:it.sheet,rows:it.rows,state:it.state,msg:it.msg||rep.fatal||'',skipped:rep.skipped||0,warnings:rep.warnings||[],asof:rep.asof||''}; });
  const sheets=wb.SheetNames.slice();
  if(items.every(function(i){ return i.state==='absent'; })) fail('None of the expected sheets were found. The sheets in this file are: '+(sheets.join(', ')||'(none)')+'. The app reads sheets named geography, ftod, ld, aop, hr, applications and dc.',OUT,{items:items,sheets:sheets});
  if(P.fatal) fail(P.fatal,OUT,{items:items,sheets:sheets});
  const okItems=items.filter(function(i){ return i.state==='ok'; });
  const res={ok:true,items:items,sheets:sheets,applied:false};
  if(okItems.length&&!items.some(function(i){ return i.state==='problem'; })){
    E.T.X.allPrev=P; E.go(); E.T.allApply();
    const keys=['f360_geo','f360_ftod','f360_ld','f360_aop','f360_hr','f360_pl','f360_dc'], tags={f360_ftod:'FT',f360_ld:'LD',f360_aop:'AP',f360_hr:'HR',f360_pl:'PL',f360_dc:'DC'};
    if(!E.ls.f360_geo) fail('The geography could not be saved by the app, so nothing was prepared.',OUT);
    const g=JSON.parse(E.ls.f360_geo); delete g.goto; E.ls.f360_geo=JSON.stringify(g);       // start on the normal first screen, not on Data sources
    let name='F360GEO:'+E.ls.f360_geo; const stored=['geo'];
    keys.slice(1).forEach(function(k){ if(E.ls[k]){ name+='\n#F360'+tags[k]+':'+E.ls[k]; stored.push(k.replace('f360_','')); } });
    res.applied=true; res.name=name; res.stored=stored; res.geoAt=g.at||'';
    let latest=''; items.forEach(function(i){ if(i.asof&&i.asof>latest) latest=i.asof; }); res.asof=latest;
  }
  fs.writeFileSync(OUT,JSON.stringify(res));
} else if(mode==='verify'){
  let E; try{ E=makeEnv(true); }catch(e){ fail('The updated file could not be started: '+e.message,OUT); }
  const T=E.T, g=T.geoStoreGet(), branches=Object.keys(T.NODES).filter(function(k){ return T.NODES[k].level===6; }).length;
  fs.writeFileSync(OUT,JSON.stringify({ok:true,hasPreload:!!pre,real:{geo:!!T.GEO.real,ftod:!!T.FT.real,ld:!!T.LD.real,aop:!!T.BPA.real,hr:!!T.BPH.real,applications:!!T.APD.real,dc:!!T.DCD.real},today:iso(T.TODAY),branches:branches,file:(g&&g.file)||'',loadedAt:(g&&g.at)||'',startsOnDataSources:!!(g&&g.goto)}));
} else fail('unknown mode '+mode);
'''

HERE = Path(__file__).resolve().parent
MARK = "UI acceptance build"


def say(msg=""):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(str(msg).encode("ascii", "replace").decode("ascii"))
    sys.stdout.flush()


def die(msg, code=1):
    say("")
    say("STOPPED: " + msg)
    sys.exit(code)


def find_node(explicit=None):
    cands = [explicit] if explicit else [shutil.which("node"), shutil.which("node.exe")]
    for c in cands:
        if not c:
            continue
        try:
            out = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=30)
            if out.returncode == 0:
                return c, out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    die("Node.js was not found. Install it (free, one minute): https://nodejs.org  -> choose the LTS version, "
        "then open a NEW terminal window and run this again. (Or give its location with --node PATH.)")


def run_engine(node, args, out_path, timeout=1800):
    """Runs the engine on a temporary file and returns the JSON it wrote."""
    tmp = Path(tempfile.mkdtemp(prefix="f360_"))
    try:
        eng = tmp / "engine.js"
        eng.write_text(ENGINE_JS, encoding="utf-8")
        cmd = [node, "--max-old-space-size=4096", str(eng)] + [str(a) for a in args] + [str(out_path)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            die("Reading the file took longer than %d minutes. Try a smaller file." % (timeout // 60))
        if not Path(out_path).exists():
            die("The engine did not finish. " + (p.stderr or p.stdout or "").strip()[-600:])
        res = json.loads(Path(out_path).read_text(encoding="utf-8"))
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _esc(c):
    o = ord(c)
    if c in '"\\<' or o < 0x20 or o == 0x7F or o in (0x2028, 0x2029) or 0xD800 <= o <= 0xDFFF:
        return "\\u%04x" % o
    return c


def make_block(name):
    lit = '"' + "".join(_esc(c) for c in name) + '"'
    return ('<script>/* %s: the test data is already loaded. It is used only when this browser has no data of its own. */\n'
            '(function(){ try{ var ls="",np=""; try{ ls=localStorage.getItem("f360_geo")||""; }catch(e){} '
            'try{ np=sessionStorage.getItem("f360_np")||""; }catch(e){} '
            'if(!ls&&!np&&String(window.name||"").indexOf("F360GEO:")!==0){ window.name=%s; } }catch(e){} })();</script>\n') % (MARK, lit)


BLOCK_RE = re.compile(r"<script>/\* " + re.escape(MARK) + r"[\s\S]*?</script>\n?")


def patch_html(text, block):
    """Returns the HTML with the data block replaced (or added). Raises ValueError if it is not a Field360 app file."""
    if "function allParseWorkbook" not in text:
        raise ValueError("it does not look like a Field360 app file")
    if "\r\n" in text:
        block = block.replace("\n", "\r\n")                     # keep the file's own (Windows) line endings
    if BLOCK_RE.search(text):
        text = BLOCK_RE.sub(lambda m: block, text, count=1)
    else:
        i = text.index("<script>")
        text = text[:i] + block + text[i:]
    flag = 'function geoStoreClear(){'
    if flag in text and "f360_np" not in text.split(flag, 1)[1][:200]:
        text = text.replace(flag, flag + ' try{ sessionStorage.setItem("f360_np","1"); }catch(e){}', 1)   # "Go back to the sample" must not reload this data
    return text


def read_text(p):
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text_atomic(p, text):
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, p)


def pick_datafile(arg):
    if arg:
        p = Path(arg)
        if not p.is_file():
            die("The data file was not found: %s" % arg)
        return p
    found = []
    for folder in (HERE / "data", HERE):
        if folder.is_dir():
            found += [x for x in sorted(folder.glob("*.xlsx")) if "template" not in x.name.lower() and not x.name.startswith("~$")]
        if found:
            break
    if len(found) == 1:
        return found[0]
    if not found:
        die("No data file given. Run:  python update_data.py path/to/your-data.xlsx")
    die("More than one .xlsx file was found (%s). Say which one:  python update_data.py FILE.xlsx" % ", ".join(x.name for x in found))


STATE_TEXT = {"ok": "loaded", "empty": "empty - sample figures stay", "absent": "not in the file - sample figures stay", "problem": "PROBLEM"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Put the data from the Field360 Excel file inside the app's HTML files.")
    ap.add_argument("datafile", nargs="?", help="the Field360 data workbook (.xlsx)")
    ap.add_argument("--html", nargs="+", help="the app files to update (default: index.html and field.html next to this script)")
    ap.add_argument("--check", action="store_true", help="only check the Excel file; change nothing")
    ap.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--backup", action="store_true", help="keep a .bak copy of every file that is updated")
    ap.add_argument("--label", help="the file name shown on the app's Data sources screen (default: the Excel file name)")
    ap.add_argument("--node", help="path to node (only if it is not found automatically)")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    data = pick_datafile(a.datafile)
    with open(data, "rb") as f:
        if f.read(2) != b"PK":
            die("%s is not an Excel .xlsx file (it must be saved as .xlsx)." % data.name)
    targets = [Path(x) for x in a.html] if a.html else [HERE / n for n in ("index.html", "field.html") if (HERE / n).is_file()]
    if not targets:
        die("No app file to update. Put index.html (and field.html) next to this script, or use --html FILE.")
    for t in targets:
        if not t.is_file():
            die("App file not found: %s" % t)
        if "function allParseWorkbook" not in read_text(t):
            die("%s does not look like a Field360 app file." % t.name)

    node, ver = find_node(a.node)
    say("Field360 data updater")
    say("  Data file : %s (%.1f MB)" % (data, data.stat().st_size / 1e6))
    say("  Updating  : %s" % ", ".join(t.name for t in targets))
    say("  Node.js   : %s" % ver)
    say("")
    say("Reading the Excel file with the app's own loader. A large file takes a minute or two...")
    t0 = time.time()
    outdir = Path(tempfile.mkdtemp(prefix="f360o_"))
    try:
        res = run_engine(node, ["parse", targets[0], data, a.label or data.name], outdir / "parse.json")
        if not res.get("ok"):
            probs = ["%s: %s" % (i["title"], i.get("msg", "")) for i in res.get("items", []) if i.get("state") == "problem"]
            die(res.get("error", "The file could not be read.") + (("\n  " + "\n  ".join(probs)) if probs else "") + "\nNothing was changed.", 2)
        say("Done in %d seconds.\n" % (time.time() - t0))
        say("  %-14s %-24s %-38s %7s %8s" % ("Your sheet", "Used for", "Result", "Rows", "Skipped"))
        problems = []
        for it in res["items"]:
            say("  %-14s %-24s %-38s %7s %8s" % ((it.get("sheet") or "-")[:14], it["title"][:24], STATE_TEXT.get(it["state"], it["state"]), it["rows"] if it["state"] != "absent" else "", it["skipped"] if it["state"] == "ok" else ""))
            if it["state"] == "problem":
                problems.append("%s: %s" % (it["title"], it.get("msg", "")))
        notes = [(it["title"], w) for it in res["items"] for w in it.get("warnings", [])]
        if notes:
            say("\nNotes from the loader (these do not stop the update):")
            for t, w in notes:
                say("  - %s: %s" % (t, w))
        if problems:
            die("These sheets have a problem, so nothing was changed:\n  " + "\n  ".join(problems), 2)
        if not res.get("applied"):
            die("The file has no sheet the app can use (geography, ftod, ld, aop, hr, applications, dc). Nothing was changed.", 2)
        if not any(i["key"] == "geo" and i["state"] == "ok" for i in res["items"]):
            die("The file has no usable geography sheet. Every other sheet is linked to branches through it. Nothing was changed.", 2)
        say("\n  Data as of: %s" % (res.get("asof") or "(not stated in the file)"))
        say("  Datasets that will be inside the app: %s" % ", ".join(res["stored"]))
        if a.check:
            say("\nCheck only: no file was changed. The file is ready to use.")
            return 0
        say("\nIMPORTANT: this puts the data inside %s." % " and ".join(t.name for t in targets))
        say("Anyone who can open those files (for example on a public GitHub site) can read the data.")
        if not a.yes:
            try:
                ans = input("Type yes to continue: ").strip().lower()
            except EOFError:
                ans = ""
            if ans not in ("yes", "y"):
                say("Cancelled. No file was changed.")
                return 0
        block = make_block(res["name"])
        originals = {}
        for t in targets:
            originals[t] = read_text(t)
        newtexts = {}
        for t in targets:
            try:
                newtexts[t] = patch_html(originals[t], block)
            except ValueError as e:
                die("%s: %s" % (t.name, e))
        for t in targets:
            if a.backup:
                shutil.copyfile(t, str(t) + ".bak")
            write_text_atomic(t, newtexts[t])
        say("\nChecking the updated files in a clean simulated browser...")
        want = {"geo", "ftod", "ld", "aop", "hr", "applications", "dc"} & {("applications" if s == "pl" else s) for s in res["stored"]}
        bad = []
        for t in targets:
            v = run_engine(node, ["verify", t], outdir / ("verify_%s.json" % t.name))
            real = {k for k, x in v.get("real", {}).items() if x} if v.get("ok") else set()
            if not v.get("ok") or not v.get("hasPreload") or not want <= real or v.get("startsOnDataSources"):
                bad.append("%s: %s" % (t.name, v.get("error") or "the data did not load as expected"))
            else:
                say("  %s: OK - %d datasets load on a first visit, %d branches, today is %s" % (t.name, len(real), v["branches"], v["today"]))
        if bad:
            for t in targets:
                write_text_atomic(t, originals[t])
            die("The updated file did not pass the check, so the ORIGINAL files were restored.\n  " + "\n  ".join(bad), 3)
        total = sum(t.stat().st_size for t in targets)
        say("\nUpdated: %s (%.1f MB in total)." % (", ".join(t.name for t in targets), total / 1e6))
        if max(t.stat().st_size for t in targets) > 50e6:
            say("WARNING: a file is over 50 MB. GitHub warns above 50 MB and refuses files above 100 MB.")
        say("Next: upload the updated file(s) to your GitHub repository (replace the old ones).")
        return 0
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
