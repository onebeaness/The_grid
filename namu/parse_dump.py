#!/usr/bin/env python3
"""나무위키 덤프 파싱 파이프라인. 문서당 JSON 한 줄.

파서: theseed-bot + namu_text.respace()
표와 각주는 평문에서 제외하고 별도 필드로 낸다. 임베딩 노이즈이기 때문.
절 스키마는 section_id, depth, number, title, text, n_chars, quality.

출력이 크다. 원문 평균 7500자 * 571375건이면 원문만 약 12.9GB.
기본은 gzip JSONL로 쓴다.
"""
import argparse, gzip, hashlib, json, os, re, sys, time, traceback
import multiprocessing as mp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import namu_text as NT

SNAPSHOT = "2021-03-01"
SNAPSHOT_CARD_LABEL = "2022-03-01"

_NM = None
def _nm():
    global _NM
    if _NM is None:
        from theseed_bot import namumark
        _NM = namumark
    return _NM

def doc_id(title):
    return "nw-" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:16]

RX_REDIRECT = re.compile(r"^\s*#\s*(?:redirect|넘겨주기)\s+(.+?)\s*$", re.I | re.M)

# 평문에서 뺄 노드
def _skip_classes(nm):
    out = []
    for n in ("FootnoteText", "Table", "TableCell", "Comment"):
        c = getattr(nm, n, None)
        if c: out.append(c)
    return tuple(out)

def _text_of(x, nm, skip, top=False):
    """줄 단위 MarkedText 리스트를 개행으로 잇는다. 붙은 단어의 근본 원인."""
    if isinstance(x, list):
        parts = [_text_of(i, nm, skip) for i in x]
        return ("\n" if top else "").join(p for p in parts if p)
    if isinstance(x, skip): return ""
    if isinstance(x, nm.LinkedText):
        try:
            if x.is_category or x.is_file: return ""
        except Exception: pass
        try: return x.get_string() or ""
        except Exception: return ""
    c = getattr(x, "content", None)
    if c is None or isinstance(c, str):
        try: return x.get_string() or ""
        except Exception: return c if isinstance(c, str) else ""
    return _text_of(c, nm, skip)

def _collect(x, nm, cls, out):
    if isinstance(x, list):
        for i in x: _collect(i, nm, cls, out)
        return
    if isinstance(x, cls): out.append(x)
    c = getattr(x, "content", None)
    if c is not None and not isinstance(c, str): _collect(c, nm, cls, out)

LEFTOVER_RX = re.compile(r"\[\[|\]\]|\{\{\{|\}\}\}|\|\||\[\*|'''|</?[a-zA-Z][^>]*>")
LETTER_RX = re.compile(r"[가-힣A-Za-z]")

def quality(text):
    """절 품질. 길이, 산문 비율, 문법 잔재로 계산."""
    n = len(text)
    if n == 0: return 0.0
    lf = min(1.0, n / 300.0)
    prose = len(LETTER_RX.findall(text)) / n
    lo = len(LEFTOVER_RX.findall(text))
    pen = max(0.0, 1.0 - lo / max(1.0, n / 1000.0) / 10.0)
    return round(lf * prose * pen, 3)

def parse_one(title, raw):
    nm = _nm()
    rec = {"doc_id": doc_id(title), "title": title, "snapshot_date": SNAPSHOT,
           "snapshot_date_card_label": SNAPSHOT_CARD_LABEL,
           "parser": "theseed-bot+respace", "len_raw": len(raw)}
    m = RX_REDIRECT.match(raw or "")
    if m:
        rec.update(is_redirect=True, redirect_target=m.group(1).strip().lstrip("\\"),
                   raw=raw, plain="", sections=[], categories=[], links=[],
                   footnotes=[], tables=[], len_plain=0)
        return rec

    doc = nm.Namumark(title, raw)
    skip = _skip_classes(nm)

    cats = []
    for c in doc.categories:
        try: cats.append(c.link.replace("분류:", "").strip())
        except Exception: pass

    secs, links, notes, tables = [], [], [], []

    def walk(p, path):
        body = NT.respace(_text_of(p.content, nm, skip, top=True))
        ttl = None
        if p.title:
            ttl = NT.respace(_text_of(p.title, nm, skip)).strip() or None
        num = ".".join(str(i) for i in path) if path else "0"
        secs.append({"section_id": "%s#%s" % (rec["doc_id"], num),
                     "depth": len(path), "level": p.level, "number": num,
                     "title": ttl, "text": body, "n_chars": len(body),
                     "quality": quality(body)})
        ln = []; _collect(p.content, nm, nm.LinkedText, ln)
        for l in ln:
            try:
                if l.is_category or l.is_file: continue
                tgt = (l.get_link() or "") if hasattr(l, "get_link") else ""
                if not isinstance(tgt, str): tgt = str(tgt)
                anchor = None
                if "#" in tgt: tgt, anchor = tgt.split("#", 1)
                links.append({"target": tgt.strip(), "display": (l.get_string() or "").strip(),
                              "anchor": anchor,
                              "external": bool(re.match(r"https?://", tgt, re.I))})
            except Exception: pass
        fn = []; _collect(p.content, nm, getattr(nm, "FootnoteText", ()), fn)
        for f in fn:
            try: notes.append({"section": num, "text": NT.respace(_text_of(f.content, nm, ())).strip()})
            except Exception: pass
        tb = []; _collect(p.content, nm, getattr(nm, "Table", ()), tb)
        for t in tb:
            try:
                cells = []; _collect(t.content, nm, getattr(nm, "TableCell", ()), cells)
                tables.append({"section": num,
                               "cells": [NT.respace(_text_of(c.content, nm, ())).strip() for c in cells]})
            except Exception: pass
        for i, c in enumerate(p.child, 1): walk(c, path + [i])

    walk(doc.paragraphs, [])
    plain = "\n\n".join("%s\n%s" % (s["title"], s["text"]) if s["title"] else s["text"]
                        for s in secs if s["text"] or s["title"]).strip()
    rec.update(is_redirect=False, redirect_target=None, raw=raw, plain=plain,
               sections=secs, categories=cats, links=links, footnotes=notes,
               tables=tables, len_plain=len(plain),
               stats={"n_sections": len(secs), "n_links": len(links),
                      "n_footnotes": len(notes), "n_tables": len(tables),
                      "n_categories": len(cats),
                      "ratio": round(len(plain) / max(len(raw), 1), 3)})
    return rec

def worker(args):
    title, raw = args
    try:
        return ("ok", parse_one(title, raw))
    except Exception as e:
        return ("fail", {"title": title, "error": "%s: %s" % (type(e).__name__, str(e)[:200]),
                         "trace": traceback.format_exc()[-800:], "raw": raw})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default="")
    ap.add_argument("--out", default="/home/user/The_grid/items/all.jsonl.gz")
    ap.add_argument("--failures", default="/home/user/The_grid/items/failures")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start-row", type=int, default=0, help="이 행부터 처리")
    ap.add_argument("--max-rows", type=int, default=0, help="이 개수만 처리")
    ap.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 1))
    ap.add_argument("--progress", type=int, default=20000)
    ap.add_argument("--plain", action="store_true", help="gzip 대신 평문 jsonl")
    a = ap.parse_args()

    import pyarrow.parquet as pq
    path = a.parquet
    if not path:
        from huggingface_hub import hf_hub_download
        path = hf_hub_download("heegyu/namuwiki", "namuwiki_20210301.parquet", repo_type="dataset")
    pf = pq.ParquetFile(path)
    os.makedirs(a.failures, exist_ok=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    opener = open if a.plain else gzip.open
    out = a.out[:-3] if (a.plain and a.out.endswith(".gz")) else a.out
    fh = opener(out, "wt", encoding="utf-8") if not a.plain else open(out, "w", encoding="utf-8")
    ffh = open(os.path.join(a.failures, "failures_%s.jsonl" % SNAPSHOT), "w", encoding="utf-8")

    n = n_ok = n_fail = n_red = 0
    t0 = time.time()

    def batches():
        seen = 0
        emitted = 0
        for b in pf.iter_batches(batch_size=1024, columns=["title", "text"]):
            d = b.to_pydict()
            n_b = len(d["title"])
            if seen + n_b <= a.start_row:      # 배치 통째로 건너뜀
                seen += n_b; continue
            for i in range(n_b):
                if seen >= a.start_row:
                    yield (d["title"][i] or "", d["text"][i] or "")
                    emitted += 1
                    if a.max_rows and emitted >= a.max_rows: return
                seen += 1

    with mp.Pool(a.workers) as pool:
        for status, r in pool.imap(worker, batches(), chunksize=64):
            n += 1
            if status == "ok":
                n_ok += 1
                if r.get("is_redirect"): n_red += 1
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            else:
                n_fail += 1
                fn = os.path.join(a.failures, re.sub(r"[^\w.-]", "_", r["title"])[:120] + ".txt")
                try:
                    with open(fn, "w", encoding="utf-8") as g:
                        g.write("# %s\n# %s\n\n%s" % (r["title"], r["error"], r["raw"]))
                except Exception: pass
                ffh.write(json.dumps({k: v for k, v in r.items() if k != "raw"},
                                     ensure_ascii=False) + "\n")
            if a.progress and n % a.progress == 0:
                el = time.time() - t0
                sys.stderr.write("  %d행  성공 %d  실패 %d  리다이렉트 %d  %.1f분  %.0f행/s\n"
                                 % (n, n_ok, n_fail, n_red, el / 60, n / max(el, 1)))
                sys.stderr.flush()
            if a.limit and n >= a.limit: break

    fh.close(); ffh.close()
    el = time.time() - t0
    meta = {"snapshot_date": SNAPSHOT, "start_row": a.start_row, "max_rows": a.max_rows, "snapshot_date_card_label": SNAPSHOT_CARD_LABEL,
            "parsed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows": n, "ok": n_ok, "failed": n_fail, "redirects": n_red,
            "documents": n_ok - n_red, "elapsed_min": round(el / 60, 1),
            "workers": a.workers, "output": out,
            "output_bytes": os.path.getsize(out) if os.path.exists(out) else None,
            "parser": "theseed-bot+respace",
            "excluded_from_plain": ["FootnoteText", "Table", "TableCell", "Comment", "Category"]}
    mp_path = "/home/user/The_grid/items/parse_meta_%s%s.json" % (
        SNAPSHOT, ("_s%d" % a.start_row) if a.start_row or a.max_rows else "")
    json.dump(meta, open(mp_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.stderr.write("\n[parse] %d행 성공 %d 실패 %d %.1f분  출력 %.2f GB\n"
                     % (n, n_ok, n_fail, el / 60,
                        (meta["output_bytes"] or 0) / 1073741824))

if __name__ == "__main__":
    main()
