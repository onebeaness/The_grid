#!/usr/bin/env python3
"""4단계. 분류 탐색. 계층이 없으므로 분류명 문자열로만 다룬다.

산출
  items/genres.jsonl           분류별 집계와 도메인 제안
  items/category_top1000.md    사람이 눈으로 보고 도메인을 붙일 목록
  items/genre_audit.md         자동 매칭 무작위 표본 100건
자동 매칭은 제안이다. 확정으로 쓰지 않는다.
"""
import argparse, collections, gzip, json, os, re, sys, time

SNAPSHOT = "2021-03-01"
HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = "/home/user/The_grid/items"

def load_domains():
    d = json.load(open(os.path.join(HERE, "domains.json"), encoding="utf-8"))
    for dom in d["domains"]:
        dom["rx"] = re.compile("|".join(re.escape(k) for k in sorted(dom["kw"], key=len, reverse=True)))
    return d["domains"]

def match_domains(name, domains):
    """분류명에 걸리는 도메인 전부와 근거 키워드를 반환."""
    hits = []
    for dom in domains:
        m = dom["rx"].search(name)
        if m: hits.append({"domain": dom["id"], "name": dom["name"], "keyword": m.group(0)})
    return hits

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", default=os.path.join(ITEMS, "all.jsonl.gz"))
    ap.add_argument("--top", type=int, default=1000)
    ap.add_argument("--audit", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20210301)
    a = ap.parse_args()

    domains = load_domains()
    cat_docs = collections.Counter()
    cat_samples = collections.defaultdict(list)   # (n_chars, title)
    doc_cats = 0
    n_doc = 0

    t0 = time.time()
    op = gzip.open if a.all.endswith(".gz") else open
    for line in op(a.all, "rt", encoding="utf-8"):
        try: r = json.loads(line)
        except Exception: continue
        if r.get("is_redirect"): continue
        n_doc += 1
        cs = r.get("categories") or []
        if cs: doc_cats += 1
        for c in cs:
            cat_docs[c] += 1
            s = cat_samples[c]
            s.append((r.get("len_plain") or 0, r["title"]))
            if len(s) > 24:
                s.sort(key=lambda x: -x[0]); del s[8:]
        if n_doc % 100000 == 0:
            sys.stderr.write("  %d문서  분류 %d종  %.1f분\n"
                             % (n_doc, len(cat_docs), (time.time()-t0)/60))

    ranked = cat_docs.most_common()
    top = ranked[:a.top]
    top_names = set(n for n, _ in top)

    # 상위 N 분류가 덮는 문서 비율. 문서 단위 중복 없이 세려면 재순회가 필요하므로
    # 분류-문서 쌍 기준과 문서 기준을 모두 낸다
    pair_total = sum(cat_docs.values())
    pair_top = sum(c for _, c in top)
    covered = 0
    for line in op(a.all, "rt", encoding="utf-8"):
        try: r = json.loads(line)
        except Exception: continue
        if r.get("is_redirect"): continue
        if any(c in top_names for c in (r.get("categories") or [])): covered += 1

    # 도메인 제안
    rows = []
    for name, cnt in ranked:
        hits = match_domains(name, domains)
        rows.append({"snapshot_date": SNAPSHOT, "category": name, "doc_count": cnt,
                     "rank": len(rows) + 1, "in_top": name in top_names,
                     "domain_proposals": hits,
                     "n_domain_hits": len(hits),
                     "samples": [t for _, t in sorted(cat_samples[name], key=lambda x: -x[0])[:3]],
                     "status": "제안"})
    with open(os.path.join(ITEMS, "genres.jsonl"), "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

    matched = [r for r in rows if r["n_domain_hits"] > 0]
    multi = [r for r in rows if r["n_domain_hits"] > 1]

    # 상위 1000 목록
    with open(os.path.join(ITEMS, "category_top%d.md" % a.top), "w", encoding="utf-8") as f:
        f.write("# 분류 상위 %d종\n\n" % a.top)
        f.write("스냅샷 %s. 문서 수 내림차순.\n\n" % SNAPSHOT)
        f.write("분류 계층 없음. 분류 네임스페이스 문서가 덤프에 0건이라 상위 하위 관계를 알 수 없음.\n")
        f.write("도메인 열은 자동 매칭 제안. 확정 아님. 눈으로 보고 채울 것.\n\n")
        f.write("| 순위 | 분류명 | 문서 수 | 도메인 제안 | 대표 문서 3개 | 확정 도메인 |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in rows[:a.top]:
            props = ", ".join(h["name"] for h in r["domain_proposals"]) or "-"
            samp = " / ".join(s[:22] for s in r["samples"]) or "-"
            f.write("| %d | %s | %d | %s | %s |  |\n"
                    % (r["rank"], r["category"], r["doc_count"], props, samp))

    # 감사 표본
    import random
    rng = random.Random(a.seed)
    pool = [r for r in matched if not r["in_top"]]
    audit = rng.sample(pool, min(a.audit, len(pool)))
    with open(os.path.join(ITEMS, "genre_audit.md"), "w", encoding="utf-8") as f:
        f.write("# 자동 매칭 감사 표본\n\n")
        f.write("스냅샷 %s. 상위 %d종 밖에서 무작위 %d건. seed %d.\n\n"
                % (SNAPSHOT, a.top, len(audit), a.seed))
        f.write("| 분류명 | 문서 수 | 제안 도메인 | 근거 키워드 | 대표 문서 | 판정 |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in audit:
            f.write("| %s | %d | %s | %s | %s |  |\n"
                    % (r["category"], r["doc_count"],
                       ", ".join(h["name"] for h in r["domain_proposals"]),
                       ", ".join(h["keyword"] for h in r["domain_proposals"]),
                       (r["samples"][0][:26] if r["samples"] else "-")))

    dom_count = collections.Counter()
    for r in rows:
        for h in r["domain_proposals"]: dom_count[h["name"]] += 1
    dom_docs = collections.Counter()
    for r in rows:
        for h in r["domain_proposals"]: dom_docs[h["name"]] += r["doc_count"]

    summary = {
        "snapshot_date": SNAPSHOT, "documents": n_doc,
        "documents_with_category": doc_cats,
        "unique_categories": len(cat_docs),
        "category_doc_pairs": pair_total,
        "top_n": a.top,
        "top_n_pair_share": round(100.0 * pair_top / max(pair_total, 1), 2),
        "top_n_document_coverage": covered,
        "top_n_document_coverage_pct": round(100.0 * covered / max(n_doc, 1), 2),
        "categories_matched_by_pattern": len(matched),
        "categories_matched_pct": round(100.0 * len(matched) / max(len(cat_docs), 1), 2),
        "categories_multi_domain": len(multi),
        "domain_category_counts": dict(dom_count.most_common()),
        "domain_doc_counts": dict(dom_docs.most_common()),
        "elapsed_min": round((time.time()-t0)/60, 1),
        "status": "자동 매칭은 제안. 확정 아님.",
    }
    json.dump(summary, open(os.path.join(ITEMS, "genres_summary_%s.json" % SNAPSHOT), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)

    print("문서 %d  분류 %d종  분류-문서 쌍 %d" % (n_doc, len(cat_docs), pair_total))
    print("상위 %d종이 덮는 문서 %d건 (%.2f%%),  분류-문서 쌍 기준 %.2f%%"
          % (a.top, covered, summary["top_n_document_coverage_pct"], summary["top_n_pair_share"]))
    print("패턴 매칭된 분류 %d종 (%.2f%%),  둘 이상 도메인 %d종"
          % (len(matched), summary["categories_matched_pct"], len(multi)))
    print("\n도메인별 제안 분류 수 / 문서 수")
    for k in dom_count: print("  %-14s %6d종  %8d문서" % (k, dom_count[k], dom_docs[k]))

if __name__ == "__main__":
    main()
