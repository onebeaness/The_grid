#!/usr/bin/env python3
"""정규식 기준선과 theseed-bot 을 실제 문서 표본에 나란히 돌려 비교."""
import argparse, json, os, re, sys, time, traceback, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import namumark_regex as RG

SNAPSHOT = "2022-03-01"

# ---------- theseed-bot 어댑터 ----------
def _tx(x):
    if x is None: return ""
    if isinstance(x, list): return "".join(_tx(i) for i in x)
    g = getattr(x, "get_string", None)
    if g:
        try: return g()
        except Exception: pass
    return str(x)

def _walk_nodes(x, out, seen=None):
    """content 를 타고 내려가며 모든 노드를 수집."""
    if seen is None: seen = set()
    if x is None: return
    if isinstance(x, list):
        for i in x: _walk_nodes(i, out, seen)
        return
    if id(x) in seen: return
    seen.add(id(x))
    out.append(x)
    c = getattr(x, "content", None)
    if c is not None and not isinstance(c, str): _walk_nodes(c, out, seen)

def theseed_parse(title, text):
    from theseed_bot import namumark as nm
    m = nm.Namumark(title, text)
    secs, nodes = [], []

    def walk(p, path):
        t = _tx(p.title).strip() if p.title else None
        body = _tx(p.content)
        num = ".".join(str(i) for i in path) if path else "0"
        secs.append({"level": p.level, "number": num, "title": t, "text": body})
        _walk_nodes(p.content, nodes)
        for i, c in enumerate(p.child, 1): walk(c, path + [i])

    walk(m.paragraphs, [])
    plain = "\n".join(s["text"] for s in secs if s["text"])
    def count(cname):
        C = getattr(nm, cname, None)
        return sum(1 for n in nodes if C and isinstance(n, C))
    return {
        "redirect": m.redirect,
        "plain": plain,
        "sections": secs,
        "categories": [c.link for c in m.categories],
        "links": count("LinkedText"),
        "footnotes": count("FootnoteText"),
        "tables": count("Table"),
    }

def regex_parse(title, text):
    r = RG.parse(text)
    return {"redirect": r["redirect"], "plain": r["plain"], "sections": r["sections"],
            "categories": r["categories"], "links": len(r["links"]),
            "footnotes": len(r["footnotes"]), "tables": len(r["tables"])}

# ---------- 문법 잔재 탐지 ----------
LEFTOVER = [
    ("나무마크 링크", re.compile(r"\[\[|\]\]")),
    ("중괄호 블록", re.compile(r"\{\{\{|\}\}\}")),
    ("표 구분자", re.compile(r"\|\|")),
    ("절 표기", re.compile(r"^={2,6}\s", re.M)),
    ("각주 표기", re.compile(r"\[\*")),
    ("매크로", re.compile(r"\[(?:br|목차|각주|include|youtube|age|anchor|ruby)\b", re.I)),
    ("볼드/이탤릭", re.compile(r"'''|''")),
    ("HTML 태그", re.compile(r"</?[a-zA-Z]+[^>]*>")),
    ("주석", re.compile(r"^##", re.M)),
]
# 붙은 단어 탐지.
# 한글-라틴 경계는 한국어 문서에 원래 흔하므로(PS4로) 지표가 되지 못한다.
# 요소 제거로 실제로 생기는 결함은 문장 종결 직후 공백 누락이다.
GLUE = re.compile(r"[.!?][가-힣A-Za-z]")              # "문법이다.내부" 형태
SCRIPT_MIX = re.compile(r"(?<=[가-힣])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[가-힣])")

def leftovers(t):
    return {name: len(rx.findall(t)) for name, rx in LEFTOVER if rx.search(t)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default="samples/real_sample_100.jsonl")
    ap.add_argument("--out", default="/home/user/The_grid/items")
    ap.add_argument("--dump-diff", type=int, default=10)
    a = ap.parse_args()

    docs = [json.loads(l) for l in open(a.sample, encoding="utf-8")]
    print("표본 %d건" % len(docs))

    engines = {"regex": regex_parse, "theseed": theseed_parse}
    agg = {k: collections.Counter() for k in engines}
    times = {k: 0.0 for k in engines}
    errs = {k: [] for k in engines}
    rows = []

    for d in docs:
        title, text = d["title"], d["text"]
        row = {"title": title, "len_raw": len(text)}
        for name, fn in engines.items():
            t0 = time.time()
            try:
                r = fn(title, text)
                dt = time.time() - t0
                times[name] += dt
                lo = leftovers(r["plain"])
                row[name] = {
                    "ok": True, "sec": round(dt, 4),
                    "len_plain": len(r["plain"]),
                    "ratio": round(len(r["plain"]) / max(len(text), 1), 3),
                    "n_sections": len(r["sections"]),
                    "n_categories": len(r["categories"]),
                    "categories": r["categories"],
                    "links": r["links"], "footnotes": r["footnotes"], "tables": r["tables"],
                    "leftover": lo, "leftover_total": sum(lo.values()),
                    "glue_risk": len(GLUE.findall(r["plain"])),
                    "script_mix": len(SCRIPT_MIX.findall(r["plain"])),
                    "glue_samples": [r["plain"][max(0,m.start()-28):m.start()+22]
                                     for m in list(GLUE.finditer(r["plain"]))[:3]],
                    "redirect": r["redirect"],
                }
                agg[name]["ok"] += 1
                agg[name]["sections"] += len(r["sections"])
                agg[name]["categories"] += len(r["categories"])
                agg[name]["links"] += r["links"]
                agg[name]["footnotes"] += r["footnotes"]
                agg[name]["tables"] += r["tables"]
                agg[name]["plain_chars"] += len(r["plain"])
                agg[name]["leftover"] += sum(lo.values())
                agg[name]["glue"] += len(GLUE.findall(r["plain"]))
                agg[name]["script_mix"] += len(SCRIPT_MIX.findall(r["plain"]))
                if lo: agg[name]["docs_with_leftover"] += 1
            except Exception as e:
                times[name] += time.time() - t0
                agg[name]["fail"] += 1
                errs[name].append({"title": title, "error": "%s: %s" % (type(e).__name__, e),
                                   "trace": traceback.format_exc()[-500:]})
                row[name] = {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:120])}
        rows.append(row)

    n = len(docs)
    print()
    print("=" * 78)
    print("파서 비교  실제 문서 %d건  스냅샷 %s" % (n, SNAPSHOT))
    print("=" * 78)
    print("%-22s %12s %12s" % ("항목", "정규식", "theseed-bot"))
    def line(label, key, fmt="%12s"):
        print(("%-22s " + fmt + " " + fmt) % (label, agg["regex"][key], agg["theseed"][key]))
    line("성공", "ok"); line("실패", "fail")
    print("%-22s %12.2f %12.2f" % ("총 소요(초)", times["regex"], times["theseed"]))
    print("%-22s %12.1f %12.1f" % ("문서당 평균(ms)", 1000*times["regex"]/n, 1000*times["theseed"]/n))
    okr = max(agg["regex"]["ok"], 1); okt = max(agg["theseed"]["ok"], 1)
    print("%-22s %12.0f %12.0f" % ("평문 평균 길이", agg["regex"]["plain_chars"]/okr, agg["theseed"]["plain_chars"]/okt))
    print("%-22s %12.2f %12.2f" % ("절 평균", agg["regex"]["sections"]/okr, agg["theseed"]["sections"]/okt))
    print("%-22s %12.2f %12.2f" % ("분류 평균", agg["regex"]["categories"]/okr, agg["theseed"]["categories"]/okt))
    print("%-22s %12.2f %12.2f" % ("링크 평균", agg["regex"]["links"]/okr, agg["theseed"]["links"]/okt))
    print("%-22s %12.2f %12.2f" % ("각주 평균", agg["regex"]["footnotes"]/okr, agg["theseed"]["footnotes"]/okt))
    print("%-22s %12.2f %12.2f" % ("표 평균", agg["regex"]["tables"]/okr, agg["theseed"]["tables"]/okt))
    line("문법 잔재 총계", "leftover")
    line("잔재 있는 문서", "docs_with_leftover")
    line("붙은 단어(종결부호 직후)", "glue")
    line("한글-라틴 경계(참고)", "script_mix")

    print("\n[붙은 단어 표본]")
    for name in engines:
        got = []
        for r in rows:
            if r.get(name, {}).get("ok"):
                got += r[name].get("glue_samples") or []
            if len(got) >= 4: break
        print("  %-9s %s" % (name, (" | ".join(x.replace("\n", " ") for x in got[:4]) or "없음")))

    print("\n[정규식 잔재 표본]")
    shown = 0
    for r in rows:
        rr = r.get("regex", {})
        if rr.get("ok") and rr["leftover_total"] > 20 and shown < 5:
            print("  %-34s 잔재 %4d  %s" % (r["title"][:34], rr["leftover_total"], rr["leftover"]))
            shown += 1

    # 잔재 유형별
    print("\n[문법 잔재 유형별]")
    for name in engines:
        c = collections.Counter()
        for r in rows:
            if r.get(name, {}).get("ok"):
                for k, v in r[name]["leftover"].items(): c[k] += v
        print("  %-10s %s" % (name, dict(c.most_common()) or "없음"))

    # 분류 일치
    print("\n[분류 추출 일치]")
    same = diff = 0
    for r in rows:
        if r["regex"]["ok"] and r["theseed"].get("ok"):
            if set(r["regex"]["categories"]) == set(x.replace("분류:", "") for x in r["theseed"]["categories"]):
                same += 1
            else: diff += 1
    print("  일치 %d / 불일치 %d" % (same, diff))

    for name in engines:
        if errs[name]:
            print("\n[%s 실패 %d건]" % (name, len(errs[name])))
            for e in errs[name][:8]: print("  %-40s %s" % (e["title"][:40], e["error"][:90]))

    os.makedirs(a.out, exist_ok=True)
    json.dump({"snapshot_date": SNAPSHOT, "n_docs": n,
               "aggregate": {k: dict(v) for k, v in agg.items()},
               "seconds": times, "errors": errs, "per_doc": rows},
              open(os.path.join(a.out, "parser_comparison_%s.json" % SNAPSHOT), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n저장: items/parser_comparison_%s.json" % SNAPSHOT)

if __name__ == "__main__":
    main()
