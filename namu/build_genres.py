#!/usr/bin/env python3
"""4단계. 분류 탐색. 계층이 없으므로 분류명 문자열로만 다룬다.

산출
  items/genres.jsonl           분류별 집계와 도메인 제안
  items/category_top1000.md    사람이 눈으로 보고 도메인을 붙일 목록
  items/genre_audit.md         자동 매칭 무작위 표본 100건
자동 매칭은 제안이다. 확정으로 쓰지 않는다.
"""
import argparse, collections, glob, gzip, json, os, re, sys, time

SNAPSHOT = "2021-03-01"
HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = "/home/user/The_grid/items"

HANGUL = re.compile(r"[가-힣]")

def _compile(kws):
    return re.compile("|".join(re.escape(k) for k in sorted(kws, key=len, reverse=True)))

def load_domains():
    d = json.load(open(os.path.join(HERE, "domains.json"), encoding="utf-8"))
    for dom in d["domains"]:
        dom["rx"] = _compile(dom["kw"])
    for nd in d.get("nondomain", []):
        nd["rx"] = _compile(nd["kw"])
    return d["domains"], d.get("nondomain", [])

def _run_bounds(text, i, j):
    """text[i:j] 를 포함하는 한글 연속열의 경계를 반환."""
    a = i
    while a > 0 and HANGUL.match(text[a - 1]): a -= 1
    b = j
    while b < len(text) and HANGUL.match(text[b]): b += 1
    return a, b

def _accept(text, m):
    """한글 키워드는 한글 연속열의 접두 또는 접미일 때만 허용한다.
    내부 위치는 배제한다. 한국어는 공백 없이 합성어를 만들어
    내부 매칭이 대량 오탐을 낸다. 디시인사이드의 시인이 그 예다."""
    i, j = m.start(), m.end()
    kw = m.group(0)
    if not HANGUL.match(kw[0]):
        # 라틴 및 숫자 키워드는 통상 단어 경계를 쓴다
        before = text[i - 1] if i > 0 else " "
        after = text[j] if j < len(text) else " "
        return not (before.isalnum() and before.isascii()) and \
               not (after.isalnum() and after.isascii())
    a, b = _run_bounds(text, i, j)
    return i == a or j == b

def _match(name, groups):
    hits = []
    for g in groups:
        for m in g["rx"].finditer(name):
            if _accept(name, m):
                hits.append({"domain": g["id"], "name": g["name"], "keyword": m.group(0)})
                break
    return hits

def match_domains(name, domains):
    """분류명에 걸리는 도메인 전부와 근거 키워드를 반환. 복수 도메인 허용."""
    return _match(name, domains)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", default=os.path.join(ITEMS, "shards"),
                    help="샤드 디렉터리. 합본을 만들지 않고 순회한다")
    ap.add_argument("--all", default="", help="단일 파일을 쓸 경우에만 지정")
    ap.add_argument("--top", type=int, default=1000)
    ap.add_argument("--audit", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20210301)
    a = ap.parse_args()

    domains, nondomains = load_domains()
    cat_docs = collections.Counter()
    cat_samples = collections.defaultdict(list)   # (n_chars, title)
    doc_cats = 0
    n_doc = 0
    # 커버리지 계산용. 분류명을 정수로 인턴해 두 번째 순회를 없앤다.
    # 샤드 합계가 수 GB이므로 두 번 읽으면 IO 비용이 두 배가 된다.
    cat_id = {}
    doc_catsets = []

    t0 = time.time()

    def iter_records():
        """샤드를 순서대로 순회한다. 합본 파일을 만들지 않는다."""
        if a.all:
            files = [a.all]
        else:
            files = sorted(glob.glob(os.path.join(a.shards, "*.jsonl.gz")))
            files = [f for f in files if os.path.exists(f[:-len(".jsonl.gz")] + ".done")]
        if not files:
            raise SystemExit("읽을 샤드가 없습니다: %s" % a.shards)
        sys.stderr.write("[genres] 샤드 %d개 순회\n" % len(files))
        for f in files:
            op = gzip.open if f.endswith(".gz") else open
            for line in op(f, "rt", encoding="utf-8"):
                yield line

    for line in iter_records():
        try: r = json.loads(line)
        except Exception: continue
        if r.get("is_redirect"): continue
        n_doc += 1
        cs = r.get("categories") or []
        if cs: doc_cats += 1
        ids = []
        for c in cs:
            cat_docs[c] += 1
            i = cat_id.get(c)
            if i is None:
                i = len(cat_id); cat_id[c] = i
            ids.append(i)
            sm = cat_samples[c]
            sm.append((r.get("len_plain") or 0, r["title"]))
            if len(sm) > 24:
                sm.sort(key=lambda x: -x[0]); del sm[8:]
        doc_catsets.append(frozenset(ids))
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
    top_ids = frozenset(cat_id[n] for n, _ in top if n in cat_id)
    covered = sum(1 for cs_ in doc_catsets if cs_ & top_ids)

    # 도메인 제안
    rows = []
    for name, cnt in ranked:
        hits = match_domains(name, domains)
        nd = _match(name, nondomains)
        rows.append({"snapshot_date": SNAPSHOT, "category": name, "doc_count": cnt,
                     "rank": len(rows) + 1, "in_top": name in top_names,
                     "domain_proposals": hits,
                     "nondomain_proposals": nd,
                     "n_domain_hits": len(hits),
                     "samples": [t for _, t in sorted(cat_samples[name], key=lambda x: -x[0])[:3]],
                     "status": "제안"})
    with open(os.path.join(ITEMS, "genres.jsonl"), "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 확정 도메인 초안. 도메인 제안이 있으면 그것을, 없고 비대상이면 비대상을, 둘 다 없으면 미판정
    for r in rows:
        if r["domain_proposals"]:
            r["draft"] = ", ".join(h["name"] for h in r["domain_proposals"])
        elif r["nondomain_proposals"]:
            r["draft"] = "비대상: " + ", ".join(h["name"] for h in r["nondomain_proposals"])
        else:
            r["draft"] = "미판정"

    matched = [r for r in rows if r["n_domain_hits"] > 0]
    multi = [r for r in rows if r["n_domain_hits"] > 1]

    # 교차 도메인 목록. 6단계에서 가장 중요한 신호
    multi_sorted = sorted(multi, key=lambda r: -r["doc_count"])
    with open(os.path.join(ITEMS, "category_multidomain.md"), "w", encoding="utf-8") as f:
        f.write("# 복수 도메인에 걸치는 분류\n\n")
        f.write("스냅샷 %s. 문서 수 내림차순. %d종.\n\n" % (SNAPSHOT, len(multi_sorted)))
        f.write("한 항목이 한 도메인에만 속한다는 전제를 버리고 복수 도메인을 허용한 결과.\n")
        f.write("억지로 하나로 만들면 이 정보가 사라진다. 6단계 미포함 영역 판단의 입력.\n\n")
        f.write("| 순위 | 분류명 | 문서 수 | 도메인 | 근거 키워드 | 대표 문서 |\n")
        f.write("|---|---|---|---|---|---|\n")
        for i, r in enumerate(multi_sorted[:1500], 1):
            f.write("| %d | %s | %d | %s | %s | %s |\n"
                    % (i, r["category"], r["doc_count"],
                       ", ".join(h["name"] for h in r["domain_proposals"]),
                       ", ".join(h["keyword"] for h in r["domain_proposals"]),
                       (r["samples"][0][:24] if r["samples"] else "-")))
    # 도메인 쌍 빈도
    pair = collections.Counter()
    for r in multi:
        ns = sorted(h["name"] for h in r["domain_proposals"])
        for i in range(len(ns)):
            for j in range(i + 1, len(ns)):
                pair[(ns[i], ns[j])] += 1

    # 상위 1000 목록
    with open(os.path.join(ITEMS, "category_top%d.md" % a.top), "w", encoding="utf-8") as f:
        f.write("# 분류 상위 %d종\n\n" % a.top)
        f.write("스냅샷 %s. 문서 수 내림차순.\n\n" % SNAPSHOT)
        f.write("분류 계층 없음. 분류 네임스페이스 문서가 덤프에 0건이라 상위 하위 관계를 알 수 없음.\n")
        f.write("도메인 열은 자동 매칭 제안. 확정 아님. 눈으로 보고 채울 것.\n\n")
        f.write("| 순위 | 분류명 | 문서 수 | 도메인 제안 | 비대상 제안 | 대표 문서 3개 | 확정 도메인(초안) |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in rows[:a.top]:
            props = ", ".join(h["name"] for h in r["domain_proposals"]) or "-"
            nds_ = ", ".join(h["name"] for h in r["nondomain_proposals"]) or "-"
            samp = " / ".join(x[:20] for x in r["samples"]) or "-"
            f.write("| %d | %s | %d | %s | %s | %s | %s |\n"
                    % (r["rank"], r["category"], r["doc_count"], props, nds_, samp, r["draft"]))

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

    nd_count = collections.Counter()
    for r in rows:
        for h in r["nondomain_proposals"]: nd_count[h["name"]] += 1
    nd_docs = collections.Counter()
    for r in rows:
        for h in r["nondomain_proposals"]: nd_docs[h["name"]] += r["doc_count"]
    draft_dist = collections.Counter(
        ("도메인" if r["domain_proposals"] else ("비대상" if r["nondomain_proposals"] else "미판정"))
        for r in rows)
    draft_docs = collections.Counter()
    for r in rows:
        k = "도메인" if r["domain_proposals"] else ("비대상" if r["nondomain_proposals"] else "미판정")
        draft_docs[k] += r["doc_count"]

    dom_count = collections.Counter()
    for r in rows:
        for h in r["domain_proposals"]: dom_count[h["name"]] += 1
    dom_docs = collections.Counter()
    for r in rows:
        for h in r["domain_proposals"]: dom_docs[h["name"]] += r["doc_count"]

    summary = {
        "snapshot_date": SNAPSHOT, "documents": n_doc,
        "source": "shards" if not a.all else a.all,
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
        "nondomain_category_counts": dict(nd_count.most_common()),
        "nondomain_doc_counts": dict(nd_docs.most_common()),
        "draft_distribution_categories": dict(draft_dist),
        "draft_distribution_docs": dict(draft_docs),
        "domain_pair_counts": {" + ".join(k): v for k, v in pair.most_common(40)},
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
    print("\n[확정 도메인 초안 분포]")
    for k in ("도메인", "비대상", "미판정"):
        print("  %-8s %6d종  %9d 분류-문서쌍" % (k, draft_dist[k], draft_docs[k]))
    print("\n도메인별 제안 분류 수 / 문서 수")
    for k, v in dom_count.most_common(): print("  %-14s %6d종  %8d문서" % (k, v, dom_docs[k]))
    print("\n비대상별 분류 수 / 문서 수")
    for k, v in nd_count.most_common(): print("  %-14s %6d종  %8d문서" % (k, v, nd_docs[k]))
    print("\n복수 도메인 분류 %d종. 상위 도메인 쌍" % len(multi))
    for k, v in pair.most_common(12): print("  %-30s %6d종" % (" + ".join(k), v))

if __name__ == "__main__":
    main()
