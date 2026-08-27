"""눈덩이 확장.
입력: index/unmatched_refs.jsonl (코퍼스에 없는데 반복 등장하는 참조)
      + 인용수 높은 코퍼스 논문의 S2 references/citations (가능할 때)
처리: 참조 문자열을 Crossref로 해소하고 제목 유사도로 재확인한 뒤 records.jsonl에 병합.
"""
import json, os, re, sys, time, argparse, urllib.parse
import sources as S
from collect import Store, merge

HERE = os.path.dirname(os.path.abspath(__file__))
IDXDIR = os.path.join(HERE, "index")
UNMATCHED = os.path.join(IDXDIR, "unmatched_refs.jsonl")

def resolve_reference(ref_text, min_sim=0.72):
    """참조 문자열 -> Crossref 레코드. 제목이 참조 문자열 안에 실제로 있는지 확인."""
    u = ("https://api.crossref.org/works?query.bibliographic="
         + urllib.parse.quote(ref_text[:400]) + "&rows=3"
         + "&select=DOI,title,author,issued,container-title,is-referenced-by-count,abstract")
    d, _ = S.jget(u)
    if not d: return None, 0.0
    nt = S.norm_title(ref_text)
    best, bs = None, 0.0
    for it in (d.get("message", {}).get("items") or []):
        ti = (it.get("title") or [""])[0]
        if not ti: continue
        cand = S.norm_title(ti)
        if len(cand.split()) < 3: continue
        sim = _win(nt, cand)
        if sim > bs: best, bs = it, sim
    if not best or bs < min_sim: return None, bs
    it = best
    yr = None
    try: yr = int(it["issued"]["date-parts"][0][0])
    except Exception: pass
    au = []
    for a in (it.get("author") or [])[:30]:
        nm = " ".join(x for x in [a.get("given"), a.get("family")] if x)
        if nm: au.append(nm)
    return S.rec(doi=it.get("DOI"), title=(it.get("title") or [""])[0], authors=au, year=yr,
                 venue=(it.get("container-title") or [None])[0],
                 citations=it.get("is-referenced-by-count"),
                 abstract=S.clean_abs(it.get("abstract")),
                 abstract_source="crossref" if it.get("abstract") else None,
                 sources=["crossref"]), bs

def _win(hay, needle):
    import difflib
    nlen = len(needle.split()); hw = hay.split()
    if len(hw) <= nlen: return difflib.SequenceMatcher(None, hay, needle).ratio()
    best = 0.0
    for i in range(0, len(hw) - nlen + 1):
        r = difflib.SequenceMatcher(None, " ".join(hw[i:i + nlen]), needle).ratio()
        if r > best: best = r
        if best > 0.95: break
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--min-count", type=int, default=2, help="이 횟수 이상 반복 등장한 참조만")
    ap.add_argument("--max-refs", type=int, default=4000)
    ap.add_argument("--s2-top", type=int, default=0, help="인용수 상위 N편의 S2 참조/피인용도 수집")
    a = ap.parse_args()

    store = Store()
    rows = []
    if os.path.exists(UNMATCHED):
        for line in open(UNMATCHED, encoding="utf-8"):
            try: o = json.loads(line)
            except Exception: continue
            if o["count"] >= a.min_count: rows.append(o)
    rows.sort(key=lambda o: -o["count"])
    rows = rows[:a.max_refs]
    S.log("[snowball r%d] 해소 대상 참조 %d건 (count>=%d)" % (a.round, len(rows), a.min_count))

    n_ok = n_new = 0
    t0 = time.time()
    log = open(os.path.join(HERE, "logs", "snowball_r%d.jsonl" % a.round), "w", encoding="utf-8")
    for i, o in enumerate(rows):
        r, sim = resolve_reference(o["sample"])
        rec_ = {"count": o["count"], "sample": o["sample"][:200], "sim": round(sim, 3)}
        if r:
            n_ok += 1
            st = store.add(r, "snowball", "ref:" + o["norm"][:60], a.round)
            if st == "new": n_new += 1
            rec_.update(resolved=True, doi=r.get("doi"), title=r.get("title"), status=st)
        else:
            rec_.update(resolved=False)
        log.write(json.dumps(rec_, ensure_ascii=False) + "\n")
        if (i + 1) % 100 == 0:
            store.flush(); log.flush()
            S.log("  %d/%d  해소 %d, 신규 %d  %.0f분"
                  % (i + 1, len(rows), n_ok, n_new, (time.time() - t0) / 60))

    if a.s2_top and S.STATE["semanticscholar"]["ok"]:
        recs = sorted(store.by_key.values(), key=lambda r: -(r.get("citations") or 0))[:a.s2_top]
        S.log("[snowball r%d] S2 참조/피인용 상위 %d편" % (a.round, len(recs)))
        for i, r in enumerate(recs):
            ident = ("DOI:" + r["doi"]) if r.get("doi") else (r.get("s2_id") or "")
            if not ident: continue
            for kind in ("references", "citations"):
                for p in S.s2_refs_cites(ident, kind=kind, limit=200):
                    if store.add(p, "snowball", "s2:%s:%s" % (kind, ident), a.round) == "new":
                        n_new += 1
            if not S.STATE["semanticscholar"]["ok"]:
                S.log("  S2 중단: " + str(S.STATE["semanticscholar"]["reason"])); break

    store.flush(); log.close()
    S.log("[snowball r%d] 완료. 해소 %d/%d, 신규 %d, 총 %d건. %.0f분"
          % (a.round, n_ok, len(rows), n_new, len(store.by_key), (time.time() - t0) / 60))

if __name__ == "__main__":
    main()
