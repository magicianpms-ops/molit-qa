#!/usr/bin/env python3
"""두 소스(국토부·국민신문고)의 안전·품질 질의회신을 합쳐 self-contained
열람·검색 페이지 qa/browse.html 을 생성한다. 의존성 없음.
"""
import json
import os
import re
from pathlib import Path

from scrape_molit import SAFETY_KW, QUALITY_KW

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "qa" / "browse.html"


def categorize(text: str) -> str:
    """항목을 정확히 하나로 분류(중복 없음): 안전 / 품질 / 건축 일반.

    안전·품질 키워드 적중 수를 비교해 우세한 쪽으로 단일 배정한다.
    둘 다 0이면 '건축 일반'(안전·품질 외 일반 건축 문의).
    ※ 키워드 기반 근사치 — 정밀 분류는 LLM 재분류로 보정 가능.
    """
    s = sum(1 for k in SAFETY_KW if k in text)
    q = sum(1 for k in QUALITY_KW if k in text)
    if s == 0 and q == 0:
        return "건축 일반"
    return "안전" if s >= q else "품질"

SRC = {
    "molit": {"index": ROOT / "qa" / "index.json", "dir": ROOT / "qa" / "molit",
              "name": "국토부", "ans": "## 회신내용", "fname": lambda k: f"{k}.md"},
    "epeople": {"index": ROOT / "qa" / "index_epeople.json", "dir": ROOT / "qa" / "epeople",
                "name": "국민신문고", "ans": "## 답변내용",
                "fname": lambda k: "ep_" + re.sub(r"[^0-9A-Za-z_-]", "_", k) + ".md"},
}


def body_parts(src, key):
    cfg = SRC[src]
    p = cfg["dir"] / cfg["fname"](key)
    if not p.exists():
        return "", ""
    t = p.read_text("utf-8")
    q = re.search(r"## (?:질의내용)\n\n(.*?)\n\n## (?:회신내용|답변내용)", t, re.S)
    a = re.search(r"## (?:회신내용|답변내용)\n\n(.*)$", t, re.S)
    return (q.group(1).strip() if q else ""), (a.group(1).strip() if a else "")


def collect():
    # LLM 분류 캐시 우선(있으면), 없으면 키워드 폴백
    llm_cat = {}
    cache = ROOT / "qa" / "llm_cat.json"
    if cache.exists():
        llm_cat = json.loads(cache.read_text("utf-8"))
    out = []
    for src, cfg in SRC.items():
        if not cfg["index"].exists():
            continue
        idx = json.loads(cfg["index"].read_text("utf-8"))
        for key, m in idx.items():
            q, a = body_parts(src, key)
            cat = llm_cat.get(key) or categorize(f"{m.get('title', '')}\n{q}\n{a}")
            out.append({
                "id": key, "src": src, "src_name": cfg["name"],
                "title": m.get("title", ""), "cat": cat,
                "dept": m.get("dept", "") or m.get("type_nm", ""),
                "posted": m.get("posted", ""), "updated": m.get("updated") or m.get("posted", ""),
                "url": m.get("url", ""), "snapshot": m.get("snapshot", ""),
                "q": q, "a": a,
            })
    return out


TEMPLATE = r"""<title>국토부 건축 안전·품질 질의회신</title>
<style>
:root{--bg:#f4f6f9;--surface:#ffffff;--surface-2:#eef1f6;--line:#dde3ec;
--ink:#1a2230;--ink-2:#54607a;--ink-3:#8b95a9;--accent:#2f5d8a;--accent-soft:#e5eef6;
--safe:#a1650a;--safe-bg:#f8efdd;--safe-line:#e8d3a6;--qual:#0d6f60;--qual-bg:#dcefe9;--qual-line:#a7d6cb;
--radius:11px;--shadow:0 1px 2px rgba(20,30,50,.05),0 6px 18px rgba(20,30,50,.06);}
@media(prefers-color-scheme:dark){:root{--bg:#0e131c;--surface:#161d29;--surface-2:#1d2634;--line:#28323f;
--ink:#e7ecf4;--ink-2:#9aa6bd;--ink-3:#6b7789;--accent:#6ba4dc;--accent-soft:#1b2c3e;
--safe:#e0a54a;--safe-bg:#33280f;--safe-line:#5a481f;--qual:#5cc3ad;--qual-bg:#12302a;--qual-line:#215047;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 22px rgba(0,0,0,.35);}}
:root[data-theme="dark"]{--bg:#0e131c;--surface:#161d29;--surface-2:#1d2634;--line:#28323f;
--ink:#e7ecf4;--ink-2:#9aa6bd;--ink-3:#6b7789;--accent:#6ba4dc;--accent-soft:#1b2c3e;
--safe:#e0a54a;--safe-bg:#33280f;--safe-line:#5a481f;--qual:#5cc3ad;--qual-bg:#12302a;--qual-line:#215047;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 22px rgba(0,0,0,.35);}
:root[data-theme="light"]{--bg:#f4f6f9;--surface:#fff;--surface-2:#eef1f6;--line:#dde3ec;
--ink:#1a2230;--ink-2:#54607a;--ink-3:#8b95a9;--accent:#2f5d8a;--accent-soft:#e5eef6;
--safe:#a1650a;--safe-bg:#f8efdd;--safe-line:#e8d3a6;--qual:#0d6f60;--qual-bg:#dcefe9;--qual-line:#a7d6cb;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:"Pretendard","Apple SD Gothic Neo",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:920px;margin:0 auto;padding:32px 20px 80px}
.tnum{font-variant-numeric:tabular-nums}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:600}
h1{font-size:26px;line-height:1.25;margin:6px 0 4px;text-wrap:balance;letter-spacing:-.01em}
.sub{color:var(--ink-2);font-size:14px;margin:0}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0 8px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px;box-shadow:var(--shadow);
cursor:pointer;font-family:inherit;text-align:left;width:100%;color:inherit;transition:border-color .12s,box-shadow .12s,transform .05s}
.stat:hover{border-color:var(--accent)}
.stat:active{transform:translateY(1px)}
.stat:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.stat[aria-pressed="true"]{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft),var(--shadow)}
.stat .n{font-size:22px;font-weight:700;letter-spacing:-.02em}
.stat .l{display:flex;align-items:center;gap:5px}
.stat[aria-pressed="true"] .l::after{content:"●";font-size:8px;color:var(--accent)}
.stat.s .n{color:var(--safe)}.stat.q .n{color:var(--qual)}.stat.e .n{color:var(--ink-2)}
.stat .l{font-size:11.5px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.06em}
.controls{position:sticky;top:0;z-index:5;background:var(--bg);padding:12px 0 10px;margin-top:6px;border-bottom:1px solid var(--line)}
.searchbar{display:flex;gap:8px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 13px;box-shadow:var(--shadow)}
.searchbar:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.searchbar svg{flex:none;color:var(--ink-3)}
#q{border:0;outline:0;background:transparent;color:var(--ink);font-size:15px;width:100%;font-family:inherit}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;align-items:center}
.chip{border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:999px;padding:5px 12px;font-size:13px;cursor:pointer;font-family:inherit;transition:.12s}
.chip:hover{border-color:var(--accent);color:var(--ink)}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.chip.kw[aria-pressed="true"]{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}
.sep{width:1px;height:20px;background:var(--line);margin:0 4px}
.count{font-size:13px;color:var(--ink-2);margin:16px 2px 10px}.count b{color:var(--ink)}
ul.list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px}
.item{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
.item>button.head{width:100%;text-align:left;background:none;border:0;cursor:pointer;padding:14px 16px;display:flex;flex-direction:column;gap:7px;font-family:inherit;color:inherit}
.item>button.head:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.title{font-size:15.5px;font-weight:600;line-height:1.4;color:var(--ink);text-wrap:balance}
.meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12.5px;color:var(--ink-3)}
.tag{font-size:11.5px;font-weight:600;padding:2px 9px;border-radius:999px}
.tag.안전{color:var(--safe);background:var(--safe-bg);border:1px solid var(--safe-line)}
.tag.품질{color:var(--qual);background:var(--qual-bg);border:1px solid var(--qual-line)}
.tag.etc{color:var(--ink-2);background:var(--surface-2);border:1px solid var(--line)}
.src{font-size:11px;font-weight:600;padding:2px 8px;border-radius:5px;border:1px solid var(--line);color:var(--ink-2);background:var(--surface-2)}
.src.epeople{color:var(--accent);border-color:var(--accent-soft)}
.dept{color:var(--ink-2)}.dot{color:var(--ink-3)}
.body{display:none;padding:0 16px 16px;border-top:1px solid var(--line)}
.item.open .body{display:block}.item.open .head{padding-bottom:11px}
.qa{margin-top:14px}
.qa h4{font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;margin:0 0 5px;color:var(--ink-3);font-weight:700}
.qa .txt{font-size:14px;color:var(--ink);white-space:pre-wrap;word-break:break-word;background:var(--surface-2);border:1px solid var(--line);border-radius:9px;padding:11px 13px}
.qa.ans .txt{border-left:3px solid var(--accent)}
.foot{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:13px;font-size:12.5px;color:var(--ink-3)}
.foot a{color:var(--accent);text-decoration:none;font-weight:600}.foot a:hover{text-decoration:underline}
.kwlist{display:flex;gap:5px;flex-wrap:wrap}
.kwlist span{font-size:11px;color:var(--ink-3);background:var(--surface-2);border:1px solid var(--line);padding:1px 7px;border-radius:5px}
mark{background:var(--safe-bg);color:var(--safe);padding:0 1px;border-radius:2px}
.empty{text-align:center;color:var(--ink-3);padding:50px 0;font-size:14px}
.themed{position:fixed;top:14px;right:14px;background:var(--surface);border:1px solid var(--line);border-radius:8px;width:34px;height:34px;cursor:pointer;color:var(--ink-2);display:grid;place-items:center;z-index:9}
@media(max-width:560px){.stats{grid-template-columns:repeat(2,1fr)}h1{font-size:22px}}
</style>
<button class="themed" id="themeBtn" title="테마 전환" aria-label="테마 전환">◐</button>
<div class="wrap">
<header>
<div class="eyebrow">국토부 민원마당 · 국민신문고 · 건축 질의회신</div>
<h1>질의회신 아카이브</h1>
<p class="sub">국토부·국민신문고의 <b>건축</b> 질의회신 아카이브. 아래 분류를 눌러 봅니다 — <b>건축 일반</b>은 안전·품질에 해당하지 않는 그 외 건축 문의입니다.</p>
<div class="stats" id="tiles">
<button class="stat" data-view="all" aria-pressed="true"><div class="n tnum" id="st-arch">0</div><div class="l">전체</div></button>
<button class="stat s" data-view="safe" aria-pressed="false"><div class="n tnum" id="st-safe">0</div><div class="l">안전</div></button>
<button class="stat q" data-view="qual" aria-pressed="false"><div class="n tnum" id="st-qual">0</div><div class="l">품질</div></button>
<button class="stat e" data-view="etc" aria-pressed="false"><div class="n tnum" id="st-etc">0</div><div class="l">건축 일반</div></button>
</div>
</header>
<div class="controls">
<label class="searchbar">
<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
<input id="q" type="search" placeholder="제목·질의·회신 검색 (예: 방화구획, 감리원 배치, 내진)" autocomplete="off">
</label>
</div>
<div class="count" id="count"></div>
<ul class="list" id="list"></ul>
<div class="empty" id="empty" hidden>검색 결과가 없습니다.</div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s);
$('#st-arch').textContent=DATA.length.toLocaleString();
$('#st-safe').textContent=DATA.filter(d=>d.cat==='안전').length.toLocaleString();
$('#st-qual').textContent=DATA.filter(d=>d.cat==='품질').length.toLocaleString();
$('#st-etc').textContent=DATA.filter(d=>d.cat==='건축 일반').length.toLocaleString();
let state={q:'',view:'all'};
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function hi(t,q){t=esc(t);if(!q)return t;try{return t.replace(new RegExp('('+q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'),'<mark>$1</mark>');}catch(e){return t;}}
function render(){
const q=state.q.trim().toLowerCase();
const catMap={all:null,safe:'안전',qual:'품질',etc:'건축 일반'};
let rows=DATA.filter(d=>{
const want=catMap[state.view];
if(want&&d.cat!==want)return false;
if(q){if(!(d.title+' '+d.q+' '+d.a+' '+d.dept).toLowerCase().includes(q))return false;}
return true;});
rows.sort((a,b)=>(b.updated||b.posted||'').localeCompare(a.updated||a.posted||''));
const vname={all:'전체',safe:'안전',qual:'품질',etc:'건축 일반'}[state.view];
$('#count').innerHTML='<b class="tnum">'+rows.length.toLocaleString()+'</b>건 · '+vname+(q?' · 검색 "'+esc(q)+'"':'');
const list=$('#list');list.innerHTML='';$('#empty').hidden=rows.length>0;
const frag=document.createDocumentFragment();
const catCls={'안전':'안전','품질':'품질','건축 일반':'etc'};
rows.forEach(d=>{
const li=document.createElement('li');li.className='item';
const catPill='<span class="tag '+catCls[d.cat]+'">'+d.cat+'</span>';
const date=d.updated||d.posted||'';
const link=d.url?'<a href="'+d.url+'" target="_blank" rel="noopener">원문 ↗</a>':'';
li.innerHTML='<button class="head"><span class="title">'+hi(d.title,state.q)+'</span>'+
'<span class="meta"><span class="src '+d.src+'">'+d.src_name+'</span>'+catPill+
'<span class="dept">'+esc(d.dept||'')+'</span>'+(date?'<span class="dot">·</span><span class="tnum">'+date+'</span>':'')+'</span></button>'+
'<div class="body"><div class="qa"><h4>질의내용</h4><div class="txt">'+hi(d.q||'(없음)',state.q)+'</div></div>'+
'<div class="qa ans"><h4>'+(d.src==='epeople'?'답변내용':'회신내용')+'</h4><div class="txt">'+hi(d.a||'(없음)',state.q)+'</div></div>'+
'<div class="foot">'+link+'<span>'+esc(d.id)+'</span></div></div>';
li.querySelector('.head').addEventListener('click',()=>li.classList.toggle('open'));
frag.appendChild(li);});
list.appendChild(frag);}
$('#q').addEventListener('input',e=>{state.q=e.target.value;render();});
$('#tiles').addEventListener('click',e=>{const b=e.target.closest('.stat');if(!b)return;
state.view=b.dataset.view;document.querySelectorAll('#tiles .stat').forEach(x=>x.setAttribute('aria-pressed',x===b?'true':'false'));render();});
const rootEl=document.documentElement;
$('#themeBtn').addEventListener('click',()=>{const cur=rootEl.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');rootEl.setAttribute('data-theme',cur==='dark'?'light':'dark');});
render();
</script>"""


EMBED = ROOT / "qa" / "browse.embed.html"  # 아티팩트 게시용(스켈레톤이 head 제공)


def main():
    data = collect()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    inner = TEMPLATE.replace("__DATA__", payload)

    # 로컬 file:// 용 — 완전한 표준 문서(charset 포함)로 감싼다.
    head = ('<!doctype html>\n<html lang="ko">\n<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n')
    full = head + inner.replace(
        '<button class="themed"', '</head>\n<body>\n<button class="themed"', 1) + "\n</body>\n</html>\n"
    OUT.write_text(full, "utf-8")
    # 아티팩트 게시용 — head 없는 원본(스켈레톤이 감쌈)
    EMBED.write_text(inner, "utf-8")

    from collections import Counter
    c = Counter(d["cat"] for d in data)
    print("browse.html(로컬 표준문서) + browse.embed.html(아티팩트용) 생성")
    print(f"  전체 {len(data)}건 · 안전 {c['안전']} / 품질 {c['품질']} / 건축 일반 {c['건축 일반']} "
          f"· {os.path.getsize(OUT)//1024}KB")


if __name__ == "__main__":
    main()
