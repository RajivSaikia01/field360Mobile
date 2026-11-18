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
import argparse, json, os, re, shutil, stat, subprocess, sys, tempfile, time
from pathlib import Path

ENGINE_JS = r''''use strict';
/* Field360 data engine. It runs the app's OWN code (the Excel reader and the loaders inside the HTML file) in Node.js,
   so the data is read exactly as the app reads it when someone chooses the file by hand.
   usage:  node engine.js parse  <app.html> <data.xlsx> <label> <out.json>
           node engine.js verify <app.html> <out.json>                                              */
const fs=require('fs'), vm=require('vm');
const mode=process.argv[2], htmlPath=process.argv[3];
function fail(msg,out,extra){ const o=Object.assign({ok:false,error:String(msg)},extra||{}); if(out) fs.writeFileSync(out,JSON.stringify(o)); else console.log(JSON.stringify(o)); process.exit(0); }
let html; try{ html=fs.readFileSync(htmlPath,'utf8'); }catch(e){ fail('Cannot read '+htmlPath+': '+e.message, process.argv[mode==='parse'?6:(mode==='sheets'?5:4)]); }
const blocks=(html.match(/<script>[\s\S]*?<\/script>/g)||[]).map(function(s){ return s.replace(/^<script>|<\/script>$/g,''); });
const lib=blocks.filter(function(b){ return /SheetJS/.test(b.slice(0,300)); })[0], app=blocks.filter(function(b){ return b.indexOf('function allParseWorkbook')>=0; })[0], pre=blocks.filter(function(b){ return b.indexOf('UI acceptance build')>=0; })[0];
const OUT=process.argv[mode==='parse'?6:(mode==='sheets'?5:4)];
if(!lib||!app) fail('This does not look like a Field360 app file (the Excel reader or the loaders were not found).',OUT);
const TAGKEY={FT:'ftod',LD:'ld',AP:'aop',HR:'hr',PL:'pl',DC:'dc',PS:'pp',FV:'fv',US:'us',BU:'bpu'};
function segTags(w){ w=String(w||''); if(w.indexOf('F360GEO:')!==0) return []; return w.slice(8).split('\n#F360').slice(1).map(function(s){ return TAGKEY[s.slice(0,2)]||s.slice(0,2).toLowerCase(); }); }
function makeEnv(withPreload,nameOverride){
  const els={}, ls={}; let now=false;
  const el=function(id){ return {id:id,classList:{add:function(){},remove:function(){},contains:function(){return false}},style:{},innerHTML:'',textContent:'',className:'',value:'',options:[],setAttribute:function(){},removeAttribute:function(){},getAttribute:function(){return ''},querySelector:function(){return null},querySelectorAll:function(){return []},appendChild:function(){},addEventListener:function(){},scrollTop:0,children:[],click:function(){}}; };
  const win={addEventListener:function(){},innerWidth:390,innerHeight:844,name:nameOverride||'',location:{search:''}};
  const ctx={console:{warn:function(){},log:function(){}},setTimeout:function(f){ if(now) f(); return 0; },clearTimeout:function(){},window:win,location:{reload:function(){},search:''},
    localStorage:{getItem:function(k){ return k in ls?ls[k]:null; },setItem:function(k,v){ ls[k]=v; },removeItem:function(k){ delete ls[k]; }},
    sessionStorage:{getItem:function(){ return null; },setItem:function(){}},
    document:{getElementById:function(id){ return els[id]||(els[id]=el(id)); },querySelectorAll:function(){ return []; },querySelector:function(){ return null; },addEventListener:function(){},removeEventListener:function(){},body:{className:'',classList:{add:function(){}}},documentElement:{style:{setProperty:function(){}}},createElement:function(){ return el('x'); }}};
  vm.createContext(ctx);
  if(withPreload&&pre) vm.runInContext(pre,ctx);
  vm.runInContext(lib,ctx);
  vm.runInContext(app+';this.T={ALL_SH:ALL_SH,geoKey:geoKey,allParseWorkbook:allParseWorkbook,allApply:allApply,X:X,GEO:GEO,FT:FT,LD:LD,BPA:BPA,BPH:BPH,APD:APD,DCD:DCD,PPD:PPD,FVD:FVD,USR:USR,geoStoreGet:geoStoreGet,get NODES(){return NODES},get TODAY(){return TODAY}};',ctx);
  return {ctx:ctx,T:ctx.T,ls:ls,win:win,go:function(){ now=true; }};
}
function iso(d){ return new Date(d*864e5).toISOString().slice(0,10); }
if(mode==='sheets'){          // just the sheet names of the workbook, and which dataset each one is for
  let E; try{ E=makeEnv(false); }catch(e){ fail('The app code in '+htmlPath+' could not be started: '+e.message,OUT); }
  let names; try{ names=E.ctx.XLSX.read(new Uint8Array(fs.readFileSync(process.argv[4])),{type:'array',bookSheets:true}).SheetNames; }catch(e){ fail('This file could not be read as Excel: '+e.message,OUT); }
  const found={}; E.T.ALL_SH.forEach(function(d){ names.forEach(function(s){ if(!found[d[0]]&&d[2].indexOf(E.T.geoKey(s))>=0) found[d[0]]={key:d[0],title:d[1],sheet:s}; }); });
  fs.writeFileSync(OUT,JSON.stringify({ok:true,names:names,found:found}));
} else if(mode==='parse'){
  const xlsx=process.argv[4], label=process.argv[5]||'data.xlsx';
  const ONLY=(process.env.F360_ONLY||'').split(',').filter(Boolean), MERGE=process.env.F360_MERGE==='1';      // ONLY: read just these datasets and keep the rest of what the page holds
  /* One sheet merged into a page that already holds data: read what the page holds as plain text (never load it into the app: that is what uses the memory),
     start the app with the GEOGRAPHY only (the one thing every sheet needs to be linked to branches), and splice the new dataset into the page's data afterwards. */
  let orig='';
  if(MERGE&&pre){ const c2={window:{name:''},localStorage:{getItem:function(){ return null; }},sessionStorage:{getItem:function(){ return null; }}}; vm.createContext(c2); try{ vm.runInContext(pre,c2); }catch(e){} orig=String(c2.window.name||''); }
  const osegs=orig.indexOf('F360GEO:')===0?orig.slice(8).split('\n#F360'):[], otag={};
  for(let i=1;i<osegs.length;i++) otag[osegs[i].slice(0,2)]=osegs[i];
  let slim; if(MERGE){ slim=osegs.length?('F360GEO:'+osegs[0]+(otag.PS?'\n#F360'+otag.PS:'')):''; }
  let E; try{ E=makeEnv(false,slim); }catch(e){ fail('The app code in '+htmlPath+' could not be started: '+e.message,OUT); }
  let og=null; try{ og=osegs.length?JSON.parse(osegs[0]):null; }catch(e){}
  const had={geoFile:(og&&og.file)||'',geoReal:!!(og&&og.rows&&og.rows.length),stored:Object.keys(otag).map(function(t){ return TAGKEY[t]||t.toLowerCase(); })};
  let wb; try{
    const buf=new Uint8Array(fs.readFileSync(xlsx));
    if(!ONLY.length) wb=E.ctx.XLSX.read(buf,{type:'array'});
    else {
      const names=E.ctx.XLSX.read(buf,{type:'array',bookSheets:true}).SheetNames, want=[], miss=[], keys=ONLY.slice();
      if(keys.indexOf('fv')>=0&&keys.indexOf('pp')<0) keys.push('pp');                 // the visit sheet is read against the process list, if the file has one
      keys.forEach(function(k){ const d=E.T.ALL_SH.filter(function(x){ return x[0]===k; })[0]; let sn=null; names.forEach(function(s){ if(!sn&&d[2].indexOf(E.T.geoKey(s))>=0) sn=s; }); if(sn) want.push(sn); else if(ONLY.indexOf(k)>=0) miss.push(d[1]+' (a sheet named '+d[2][0]+')'); });
      if(miss.length) fail('This file has no sheet for '+miss.join(', ')+'. The sheets in it are: '+names.join(', ')+'.',OUT,{had:had});
      const w=E.ctx.XLSX.read(buf,{type:'array',sheets:want}); wb={SheetNames:want,Sheets:w.Sheets};
    }
  }catch(e){ fail('This file could not be read as Excel: '+e.message,OUT); }
  let P; try{ P=E.T.allParseWorkbook(wb,label); }catch(e){ fail('The file could not be checked: '+e.message,OUT); }
  const items=P.items.map(function(it){ const rep=(it.res&&it.res.rep)||{}; return {key:it.key,title:it.title,sheet:it.sheet,rows:it.rows,state:it.state,msg:it.msg||rep.fatal||'',skipped:rep.skipped||0,warnings:rep.warnings||[],asof:rep.asof||''}; });
  const sheets=wb.SheetNames.slice();
  if(items.every(function(i){ return i.state==='absent'; })) fail('None of the expected sheets were found. The sheets in this file are: '+(sheets.join(', ')||'(none)')+'. The app reads sheets named geography, ftod, ld, aop, hr, applications and dc.',OUT,{items:items,sheets:sheets,had:had});
  if(P.fatal) fail(P.fatal,OUT,{items:items,sheets:sheets,had:had});
  const okItems=items.filter(function(i){ return i.state==='ok'; });
  const res={ok:true,items:items,sheets:sheets,applied:false,had:had,only:ONLY};
  if(okItems.length&&!items.some(function(i){ return i.state==='problem'; })){
    E.T.X.allPrev=P; E.go(); E.T.allApply();
    const keys=['f360_geo','f360_ftod','f360_ld','f360_aop','f360_hr','f360_pl','f360_dc','f360_pp','f360_fv','f360_us'], tags={f360_ftod:'FT',f360_ld:'LD',f360_aop:'AP',f360_hr:'HR',f360_pl:'PL',f360_dc:'DC',f360_pp:'PS',f360_fv:'FV',f360_us:'US'};
    let name, stored, g;
    if(MERGE){          // the page's own datasets, untouched, with the new one put in place of the old one
      const w=String(E.win.name||''); if(w.indexOf('F360GEO:')!==0||!osegs.length) fail('The geography could not be saved by the app, so nothing was prepared.',OUT);
      const nseg=w.slice(8).split('\n#F360'), ntag={}; for(let i=1;i<nseg.length;i++) ntag[nseg[i].slice(0,2)]=nseg[i];
      const KEYTAG={ftod:'FT',ld:'LD',aop:'AP',hr:'HR',app:'PL',dc:'DC',pp:'PS',fv:'FV',us:'US'}; ONLY.forEach(function(k){ if(KEYTAG[k]&&ntag[KEYTAG[k]]) otag[KEYTAG[k]]=ntag[KEYTAG[k]]; });
      g=JSON.parse(osegs[0]); delete g.goto;       // start on the normal first screen, not on Data sources
      name='F360GEO:'+JSON.stringify(g); stored=['geo']; ['FT','LD','AP','HR','BU','PL','DC','PS','FV','US'].forEach(function(t){ if(otag[t]){ name+='\n#F360'+otag[t]; stored.push(TAGKEY[t]||t.toLowerCase()); } });
    } else {
      if(!E.ls.f360_geo) fail('The geography could not be saved by the app, so nothing was prepared.',OUT);
      g=JSON.parse(E.ls.f360_geo); delete g.goto; E.ls.f360_geo=JSON.stringify(g);       // start on the normal first screen, not on Data sources
      name='F360GEO:'+E.ls.f360_geo; stored=['geo'];
      keys.slice(1).forEach(function(k){ if(E.ls[k]){ name+='\n#F360'+tags[k]+':'+E.ls[k]; stored.push(k.replace('f360_','')); } });
    }
    res.applied=true; res.name=name; res.stored=stored; res.geoAt=g.at||'';
    let latest=''; items.forEach(function(i){ if(i.asof&&i.asof>latest) latest=i.asof; }); res.asof=latest;
  }
  fs.writeFileSync(OUT,JSON.stringify(res));
} else if(mode==='verify'){
  let E; try{ E=makeEnv(true); }catch(e){ fail('The updated file could not be started: '+e.message,OUT); }
  const T=E.T, g=T.geoStoreGet(), branches=Object.keys(T.NODES).filter(function(k){ return T.NODES[k].level===6; }).length;
  fs.writeFileSync(OUT,JSON.stringify({ok:true,hasPreload:!!pre,real:{geo:!!T.GEO.real,ftod:!!T.FT.real,ld:!!T.LD.real,aop:!!T.BPA.real,hr:!!T.BPH.real,applications:!!T.APD.real,dc:!!T.DCD.real,processes:!!T.PPD.real,visits:!!T.FVD.real,users:!!T.USR.real},today:iso(T.TODAY),branches:branches,file:(g&&g.file)||'',loadedAt:(g&&g.at)||'',startsOnDataSources:!!(g&&g.goto)}));
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


def open_sizes(path):
    """the opened size of every sheet in an .xlsx, heaviest first: [(bytes, name)]"""
    import zipfile
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(str(path))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = []
    for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(ns + "sheet"):
        t = rels.get(sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"))
        if t:
            part = t.lstrip("/") if t.startswith("/") else "xl/" + t
            out.append((z.getinfo(part).file_size, sh.get("name")))
    return sorted(out, reverse=True)


def need_mb(open_bytes):
    return int(open_bytes / 1048576.0 * 25 / 100 + 1) * 100 + 400          # measured: about 25 times the sheet's opened size


def run_engine(node, args, out_path, timeout=1800, memory=None, env=None):
    """Runs the engine on a temporary file and returns the JSON it wrote."""
    tmp = Path(tempfile.mkdtemp(prefix="f360_"))
    try:
        eng = tmp / "engine.js"
        eng.write_text(ENGINE_JS, encoding="utf-8")
        cmd = [node] + (["--max-old-space-size=%d" % memory] if memory else []) + [str(eng)] + [str(a) for a in args] + [str(out_path)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=(dict(os.environ, **env) if env else None))
        except subprocess.TimeoutExpired:
            die("Reading the file took longer than %d minutes. Try a smaller file." % (timeout // 60))
        if not Path(out_path).exists():
            msg = (p.stderr or p.stdout or "").strip()[-600:]
            if p.returncode in (-9, 137, 134) or "heap" in msg.lower() or "memory" in msg.lower():
                size = 0
                try:
                    size = Path(str(args[1] if len(args) > 1 else "")).stat().st_size
                except OSError:
                    pass
                for a_ in args:
                    try:
                        if str(a_).lower().endswith((".xlsx", ".xlsm")):
                            size = Path(str(a_)).stat().st_size
                    except OSError:
                        pass
                mbs = size / 1048576.0
                lines = ["Node.js ran out of memory reading this file."]
                heavy = []
                try:
                    xl = [str(a_) for a_ in args if str(a_).lower().endswith((".xlsx", ".xlsm"))]
                    heavy = open_sizes(xl[0]) if xl else []
                except Exception:
                    heavy = []
                if heavy:
                    top = need_mb(heavy[0][0])
                    lines.append("The heaviest sheets, when opened: " + ", ".join("%s %.0f MB" % (n_, b_ / 1048576.0) for b_, n_ in heavy[:3]) + ".")
                    lines.append("Reading '%s' alone needs about %d MB of memory (about 25 times its opened size)%s." % (heavy[0][1], top, "; you gave Node %d MB" % memory if memory else ""))
                elif mbs:
                    top = int(mbs * 75 / 512 + 1) * 512
                    lines.append("This file is %.0f MB. Reading it needs roughly %d MB of memory%s." % (mbs, top, "; you gave Node %d MB" % memory if memory else ""))
                else:
                    top = 4096
                lines += ["", "What to do, in this order:",
                          "  1. Update ONE SHEET at a time. Each step then needs only that sheet's memory, not the whole file's, and what is already in the pages is kept:",
                          "         python update_data.py <your file> --sheet geography",
                          "         python update_data.py <your file> --sheet ld            (then dc, field_visit, hr, ... one by one)",
                          "         python update_data.py <your file> --sheet all           (every sheet, one at a time, in one go)",
                          "  2. Add memory for Node, below the memory your computer has:  --memory %d" % max(2048, top),
                          "  3. Make the heavy sheet smaller. The app keeps only the last three months of the ld, dc and field_visit sheets, so older rows are wasted:",
                          "         python trim_data.py <your file> --report     (shows each sheet's size and the memory it needs)",
                          "         python trim_data.py <your file>              (writes <your file>-trimmed.xlsx; then run this updater on that file)",
                          "  4. If the heavy sheet is another one, remove columns and blank rows you do not need in Excel and save as .xlsx."]
                die("\n".join(lines))
            die("The engine did not finish (exit code %s). %s" % (p.returncode, msg))
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


class WriteFailed(Exception):
    pass


def write_text_atomic(p, text):
    """Save text to a file. On Windows a file can refuse to be replaced (read-only flag, open in another program, antivirus or sync
    tools), so: clear the read-only flag, retry a few times, and as a last resort write over it in place."""
    p = str(p)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except OSError as e:
        raise WriteFailed("could not create %s next to it (%s)" % (os.path.basename(tmp), e))
    last = None
    for attempt in range(5):
        try:
            os.replace(tmp, p)
            return
        except OSError as e:
            last = e
            try:
                os.chmod(p, stat.S_IREAD | stat.S_IWRITE)          # a read-only file cannot be replaced
            except OSError:
                pass
            time.sleep(0.4 * (attempt + 1))
    try:                                                          # last resort: overwrite the file itself
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.remove(tmp)
        return
    except OSError as e2:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise WriteFailed("%s refused to be changed (%s)" % (os.path.basename(p), e2 if e2 else last))


def save_pages(targets, texts, backup=False, keep_bak_once=False):
    """Write every page. If one cannot be written, put back the ones already written and stop with a clear message."""
    done = []
    try:
        for t in targets:
            if backup and not (keep_bak_once and os.path.exists(str(t) + ".bak")):
                shutil.copyfile(t, str(t) + ".bak")
            before = read_text(t)
            write_text_atomic(t, texts[t])
            done.append((t, before))
    except (WriteFailed, OSError) as e:
        for t, before in done:
            try:
                write_text_atomic(t, before)
            except (WriteFailed, OSError):
                pass
        die("Could not save the page: %s.\n"
            "No page was changed by this save (any page already written was put back).\n\n"
            "On Windows this usually means one of these. Try them in order:\n"
            "  1. The file is marked Read-only. In this folder run:   attrib -R index.html field.html\n"
            "     (or right-click the file > Properties > untick Read-only).\n"
            "  2. Another program has the file open (an editor, a preview or live-server tool, or a browser tab on a local server).\n"
            "     Close it, and stop any  python -m http.server  that is running, then run the update again.\n"
            "  3. Antivirus, OneDrive or Windows 'Controlled folder access' is blocking Python from changing files here.\n"
            "     Pause it, allow python.exe, or copy this whole folder to a simple path such as C:\\f360 and run it there.\n"
            "  4. Delete the leftover  index.html.tmp  and  field.html.tmp  files if they exist.\n"
            "To test write access:  python -c \"open('index.html','a').close(); print('writable')\"" % (e,), 4)


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


SHEET_ALIASES = {"geography": "geo", "geo": "geo", "process_and_subprocess": "pp", "processes": "pp", "process": "pp", "pp": "pp", "users": "us", "user": "us", "us": "us",
                 "ftod": "ftod", "ld": "ld", "aop": "aop", "bpr": "aop", "hr": "hr", "applications": "app", "application": "app", "app": "app", "pl": "app",
                 "dc": "dc", "demand": "dc", "field_visit": "fv", "visits": "fv", "visit": "fv", "fv": "fv"}
STEP_ORDER = ["geo", "pp", "us", "ftod", "ld", "aop", "hr", "app", "dc", "fv"]        # geography first: it links every other sheet to branches
STEP_TITLE = {"geo": "Geography", "pp": "Process and sub-process", "us": "Users", "ftod": "FTOD cases", "ld": "Loan disbursement (LD)", "aop": "BPR targets",
              "hr": "Field staff", "app": "Application pipeline", "dc": "Demand vs Collection", "fv": "Field visits"}


def run_sheet_mode(a, data, targets, node):
    """One sheet at a time: each step reads ONLY that sheet from the Excel file (so memory is the size of that one sheet), merges it into the data
    the pages already hold, and saves. Every step is a separate Node.js process, so memory is given back between steps."""
    wanted = []
    for tok in a.sheet:
        for part in str(tok).replace(";", ",").split(","):
            part = part.strip().lower()
            if not part:
                continue
            if part == "all":
                if "all" not in wanted:
                    wanted.append("all")
                continue
            k = SHEET_ALIASES.get(part)
            if not k:
                die("'%s' is not a sheet the app reads. Use: geography, process_and_subprocess, users, ftod, ld, aop, hr, applications, dc, field_visit, or all." % part, 2)
            if k not in wanted:
                wanted.append(k)
    outdir = Path(tempfile.mkdtemp(prefix="f360o_"))
    originals = {t: read_text(t) for t in targets}
    work = targets[0]
    try:
        if a.check:
            work = outdir / "work.html"
            shutil.copyfile(targets[0], work)
        sh = run_engine(node, ["sheets", targets[0], data], outdir / "sheets.json", memory=a.memory)
        if not sh.get("ok"):
            die(sh.get("error", "The file could not be read.") + "\nNothing was changed.", 2)
        present = [k for k in STEP_ORDER if k in sh["found"]]
        if "all" in wanted:
            keys = present
        else:
            keys = [k for k in STEP_ORDER if k in wanted]
            gone = [STEP_TITLE[k] for k in keys if k not in present]
            if gone:
                die("This file has no sheet for %s. The sheets in it are: %s. Nothing was changed." % (", ".join(gone), ", ".join(sh["names"])), 2)
        if not keys:
            die("None of the sheets the app reads were found. The sheets in this file are: %s. Nothing was changed." % ", ".join(sh["names"]), 2)
        say("One sheet at a time (%d step%s): %s" % (len(keys), "" if len(keys) == 1 else "s", ", ".join("%s ['%s']" % (STEP_TITLE[k], sh["found"][k]["sheet"]) for k in keys)))
        say("Only these sheets are replaced. Anything else already inside the pages stays as it is.")
        if a.check:
            say("Check only: nothing in your files will be changed.")
        say("")
        label = a.label or data.name
        asked = False; last = None; done = []; failed = None; warned = False
        for i, k in enumerate(keys, 1):
            say("Step %d of %d: %s (sheet '%s')..." % (i, len(keys), STEP_TITLE[k], sh["found"][k]["sheet"]))
            t0 = time.time()
            try:
                res = run_engine(node, ["parse", work, data, label], outdir / ("parse_%s.json" % k), memory=a.memory,
                                 env={"F360_ONLY": k, "F360_MERGE": "" if k == "geo" else "1"})
            except SystemExit:
                failed = k
                break
            it = next((x for x in res.get("items", []) if x["key"] == k), None)
            if not res.get("ok") or it is None or it["state"] != "ok" or not res.get("applied"):
                msg = (it or {}).get("msg") or res.get("error") or "The sheet could not be used."
                if k != "geo" and not (res.get("had") or {}).get("geoReal"):
                    msg += " Load the geography first:  python update_data.py %s --sheet geography" % data.name
                say("  PROBLEM: %s" % msg)
                failed = k
                break
            had = res.get("had") or {}
            if k != "geo" and not warned and had.get("geoFile") and had["geoFile"] != label:
                warned = True
                say("  Note: the geography inside the pages came from '%s', not from '%s'. If your branches do not match, run  --sheet geography  first." % (had["geoFile"], label))
            lost = set(had.get("stored", [])) - set(res.get("stored", []))
            if k != "geo" and lost:
                say("  STOPPED: this step would have dropped %s from the pages, so it was not saved." % ", ".join(sorted(lost)))
                failed = k
                break
            say("  loaded: %s rows, %s skipped, %d seconds" % (format(it["rows"], ","), it["skipped"], time.time() - t0))
            for w in it.get("warnings", []):
                say("    - %s" % w)
            if not a.check and not asked:
                say("\nIMPORTANT: this puts the data inside %s. Anyone who can open those files (for example on a public GitHub site) can read it." % " and ".join(t.name for t in targets))
                if not a.yes:
                    try:
                        ans = input("Type yes to continue: ").strip().lower()
                    except EOFError:
                        ans = ""
                    if ans not in ("yes", "y"):
                        say("Cancelled. No file was changed.")
                        return 0
                asked = True
                say("")
            block = make_block(res["name"])
            if a.check:
                write_text_atomic(work, patch_html(read_text(work), block))
            else:
                save_pages(targets, {t: patch_html(read_text(t), block) for t in targets}, a.backup, keep_bak_once=True)
            last = res; done.append(k)
        if failed:
            say("\nStopped at: %s." % STEP_TITLE[failed])
        if done:
            say("%s: %s" % ("Checked" if a.check else "Saved in the pages", ", ".join(STEP_TITLE[k] for k in done)))
        if not done:
            die("Nothing was changed.", 2)
        if a.check:
            say("\nCheck only: no file was changed.")
            return 1 if failed else 0
        say("\nChecking the updated files in a clean simulated browser..." if not a.no_verify else "\nSkipping the final check (--no-verify). Open the updated pages in a browser to be sure they load.")
        flag = {"geo": "geo", "ftod": "ftod", "ld": "ld", "aop": "aop", "hr": "hr", "pl": "applications", "dc": "dc", "pp": "processes", "fv": "visits", "us": "users"}
        want = {flag[s] for s in last["stored"] if s in flag}
        bad = []
        for t in ([] if a.no_verify else targets):
            v = run_engine(node, ["verify", t], outdir / ("verify_%s.json" % t.name), memory=a.memory)
            real = {k2 for k2, x in v.get("real", {}).items() if x} if v.get("ok") else set()
            if not v.get("ok") or not v.get("hasPreload") or not want <= real or v.get("startsOnDataSources"):
                bad.append("%s: %s" % (t.name, v.get("error") or "the data did not load as expected"))
            else:
                say("  %s: OK - %d datasets load on a first visit, %d branches, today is %s" % (t.name, len(real), v["branches"], v["today"]))
        if bad:
            for t in targets:
                write_text_atomic(t, originals[t])
            die("The updated file did not pass the check, so the ORIGINAL files were restored.\n  " + "\n  ".join(bad), 3)
        say("\nUpdated: %s (%.1f MB in total). Datasets now inside the pages: %s" % (", ".join(t.name for t in targets), sum(t.stat().st_size for t in targets) / 1e6, ", ".join(last["stored"])))
        if failed:
            rest = [STEP_TITLE[k] for k in keys[keys.index(failed):]]
            say("Not done yet: %s. Fix the problem above, then run, for example:  python update_data.py %s --sheet %s" % (", ".join(rest), data.name, " ".join(k for k in keys[keys.index(failed):])))
            return 1
        say("Next: upload the updated file(s) to your GitHub repository (replace the old ones).")
        return 0
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


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
    ap.add_argument("--sheet", nargs="+", metavar="SHEET", help="update ONE sheet (or several, one after the other) instead of the whole file, keeping everything else already in the pages. "
                    "Names: geography, process_and_subprocess, users, ftod, ld, aop, hr, applications, dc, field_visit, or all (every sheet, one at a time). Do geography first.")
    ap.add_argument("--no-verify", action="store_true", help="skip the final check that opens the updated pages in a simulated browser (that check loads ALL the data at once; use this only if it runs out of memory)")
    ap.add_argument("--memory", type=int, help="most memory Node may use, in MB (only for very large files; the default is Node's own limit)")
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
    if a.sheet:
        return run_sheet_mode(a, data, targets, node)
    say("Reading the Excel file with the app's own loader. A large file takes a minute or two...")
    t0 = time.time()
    outdir = Path(tempfile.mkdtemp(prefix="f360o_"))
    try:
        res = run_engine(node, ["parse", targets[0], data, a.label or data.name], outdir / "parse.json", memory=a.memory)
        if not res.get("ok"):
            probs = ["%s: %s" % (i["title"], i.get("msg", "")) for i in res.get("items", []) if i.get("state") == "problem"]
            die(res.get("error", "The file could not be read.") + (("\n  " + "\n  ".join(probs)) if probs else "") + "\nNothing was changed.", 2)
        say("Done in %d seconds.\n" % (time.time() - t0))
        say("  %-22s %-24s %-38s %7s %8s" % ("Your sheet", "Used for", "Result", "Rows", "Skipped"))
        problems = []
        for it in res["items"]:
            say("  %-22s %-24s %-38s %7s %8s" % ((it.get("sheet") or "-")[:22], it["title"][:24], STATE_TEXT.get(it["state"], it["state"]), it["rows"] if it["state"] != "absent" else "", it["skipped"] if it["state"] == "ok" else ""))
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
            die("The file has no sheet the app can use (geography, ftod, ld, aop, hr, applications, dc, process_and_subprocess, field_visit, users). Nothing was changed.", 2)
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
        save_pages(targets, newtexts, a.backup)
        say("\nChecking the updated files in a clean simulated browser..." if not a.no_verify else "\nSkipping the final check (--no-verify). Open the updated pages in a browser to be sure they load.")
        flag = {"geo": "geo", "ftod": "ftod", "ld": "ld", "aop": "aop", "hr": "hr", "pl": "applications", "dc": "dc", "pp": "processes", "fv": "visits", "us": "users"}
        want = {flag[s] for s in res["stored"] if s in flag}
        bad = []
        for t in ([] if a.no_verify else targets):
            v = run_engine(node, ["verify", t], outdir / ("verify_%s.json" % t.name), memory=a.memory)
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
