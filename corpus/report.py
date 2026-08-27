"""수집 현황 집계. 해석은 하지 않는다."""
import json, os, collections, argparse

HERE = os.path.dirname(os.path.abspath(__file__))

def load(p):
    out = []
    if not os.path.exists(p): return out
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out

def bar(n, mx, w=34):
    return "#" * max(0, int(round(w * n / mx))) if mx else ""

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    recs = load(os.path.join(HERE, "records.jsonl"))
    man = {m["key"]: m for m in load(os.path.join(HERE, "manifest.jsonl"))}
    skipped = load(os.path.join(HERE, "skipped_fetch.jsonl"))
    fams = json.load(open(os.path.join(HERE, "keywords.json"), encoding="utf-8"))["families"]
    name = {f["id"]: f["name_ko"] for f in fams}
    name["snowball"] = "눈덩이 확장"

    print("=" * 78)
    print("수집 현황")
    print("=" * 78)
    print("레코드 총계        %d" % len(recs))
    print("원문 시도          %d" % len(man))
    print("원문 미시도(상한)  %d" % len(skipped))

    st = collections.Counter(m["status"] for m in man.values())
    tot = sum(st.values()) or 1
    print("\n[원문 확보 상태]")
    for k, label in (("pdf", "전문 PDF"), ("abstract", "초록만"), ("none", "확보 실패")):
        print("  %-10s %6d  %5.1f%%" % (label, st.get(k, 0), 100.0 * st.get(k, 0) / tot))

    print("\n[계열별]")
    print("  %-26s %7s %7s %7s %7s %7s" % ("계열", "레코드", "시도", "전문", "초록", "전문%"))
    fam_c = collections.Counter()
    for r in recs:
        for f in (r.get("families") or ["_none"]): fam_c[f] += 1
    for f, n in fam_c.most_common():
        keys = [r["key"] for r in recs if f in (r.get("families") or [])]
        mm = [man[k] for k in keys if k in man]
        p = sum(1 for m in mm if m["status"] == "pdf")
        ab = sum(1 for m in mm if m["status"] == "abstract")
        print("  %-26s %7d %7d %7d %7d %6.1f%%"
              % (name.get(f, f)[:26], n, len(mm), p, ab, 100.0 * p / max(1, len(mm))))

    print("\n[연도 분포]")
    yrs = collections.Counter(r["year"] for r in recs if r.get("year") and 1950 <= r["year"] <= 2027)
    if yrs:
        mx = max(yrs.values())
        for y in sorted(yrs):
            if y < 1990 and yrs[y] < mx * 0.02: continue
            print("  %4d %6d %s" % (y, yrs[y], bar(yrs[y], mx)))
        old = sum(v for k, v in yrs.items() if k < 1990)
        if old: print("  1990 이전 합계 %d" % old)
        print("  연도 미상 %d" % sum(1 for r in recs if not r.get("year")))

    print("\n[빈출 저자 상위 %d]" % a.top)
    au = collections.Counter()
    for r in recs:
        for x in (r.get("authors") or [])[:12]:
            if x and len(x) > 3: au[x.strip()] += 1
    for n, c in au.most_common(a.top): print("  %5d  %s" % (c, n))

    print("\n[빈출 학회지 상위 %d]" % a.top)
    vn = collections.Counter(r["venue"].strip() for r in recs if r.get("venue"))
    for n, c in vn.most_common(a.top): print("  %5d  %s" % (c, n[:66]))

    print("\n[소스별 기여]")
    sc = collections.Counter()
    for r in recs:
        for s in (r.get("sources") or []): sc[s] += 1
    for s, c in sc.most_common(): print("  %-18s %6d" % (s, c))

    print("\n[인용 그래프]")
    g = load(os.path.join(HERE, "index", "citation_graph.jsonl"))
    um = load(os.path.join(HERE, "index", "unmatched_refs.jsonl"))
    nodes = set(e["src"] for e in g) | set(e["dst"] for e in g)
    print("  간선 %d, 노드 %d, 미매칭 고유 참조 %d" % (len(g), len(nodes), len(um)))
    if g:
        ind = collections.Counter(e["dst"] for e in g)
        t = {r["key"]: r.get("title") for r in recs}
        print("  코퍼스 내 피인용 상위:")
        for k, c in ind.most_common(10):
            print("    %4d  %s" % (c, (t.get(k) or k)[:62]))

    mp = os.path.join(HERE, "index", "meta.json")
    if os.path.exists(mp):
        m = json.load(open(mp, encoding="utf-8"))
        print("\n[벡터 인덱스]")
        print("  문서 %d, 청크 %d, dim %d, 모델 %s" % (m["n_docs"], m["n_chunks"], m["dim"], m["model"]))

    print("\n[차단 사유 상위]")
    br = collections.Counter(m.get("blocked_reason") for m in man.values()
                             if m["status"] != "pdf" and m.get("blocked_reason"))
    for r_, c in br.most_common(12): print("  %6d  %s" % (c, r_))

if __name__ == "__main__":
    main()
