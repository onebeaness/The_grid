#!/usr/bin/env python3
"""게재지 정규화와 계열별 핵심 목록 초안.

인용수는 Crossref 에만 붙지만 게재지는 PubMed 100퍼센트, arXiv 100퍼센트,
DBLP 99.6퍼센트, Crossref 82.4퍼센트로 붙는다. 인용수 공백을 우회한다.
"""
import collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAM = {"cultural-sociology": "문화소비 사회학", "taste-psychology": "취향 구조 심리학",
       "cross-domain-rec": "교차도메인 추천", "representation-learning": "표현 학습",
       "consumer-behavior": "소비자행동", "similarity-attraction": "취향 유사성과 관계",
       "inference-privacy": "추론과 프라이버시"}

# 게재지가 아닌 것. 프리프린트 서버, 심사 서비스, 데이터셋 레코드, 시리즈명
NONVENUE = re.compile(
    r"^(arxiv|corr|ssrn|biorxiv|medrxiv|preprints?|research square|zenodo|osf)"
    r"|faculty opinions|psycextra|psyctests|psycarticles"
    r"|^lecture notes in (computer science|artificial intelligence|networks)$"
    r"|^communications in computer and information science$"
    r"|^advances in intelligent systems"
    r"|^proceedings of spie$|^sae technical paper", re.I)

ABBREV = {
    "expert syst. appl.": "expert systems with applications",
    "knowl.-based syst.": "knowledge-based systems",
    "knowl based syst": "knowledge-based systems",
    "ieee trans. knowl. data eng.": "ieee transactions on knowledge and data engineering",
    "acm trans. inf. syst.": "acm transactions on information systems",
    "j. mach. learn. res.": "journal of machine learning research",
    "neurocomputing": "neurocomputing",
    "inf. process. manag.": "information processing and management",
    "j. pers. soc. psychol.": "journal of personality and social psychology",
    "pers. individ. differ.": "personality and individual differences",
    "plos one": "plos one",
}

DROP_PREFIX = re.compile(
    r"^(proceedings of the|proceedings of|the proceedings of|proc\.?\s+of\s+the|proc\.?\s+of)\s+", re.I)
DROP_ORDINAL = re.compile(
    r"^\d+(st|nd|rd|th)\s+", re.I)
DROP_YEAR = re.compile(r"\b(19|20)\d{2}\b")
DROP_PAREN = re.compile(r"\s*\([^)]*\)\s*$")

def normalize(v):
    if not v: return None
    if isinstance(v, (list, tuple)): v = ", ".join(str(x) for x in v)
    s = re.sub(r"&amp;", "&", v)
    s = re.sub(r"\s+", " ", s).strip()
    s = DROP_PAREN.sub("", s)
    s = DROP_PREFIX.sub("", s)
    s = DROP_ORDINAL.sub("", s)
    s = DROP_YEAR.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.-")
    low = s.lower()
    if NONVENUE.search(low): return None
    low = ABBREV.get(low, low)
    return low

def display(name, counter):
    """정규화 키에 대해 가장 흔한 원 표기를 고른다."""
    return counter[name].most_common(1)[0][0] if counter.get(name) else name

def main():
    recs = [json.loads(l) for l in open(os.path.join(HERE, "records.jsonl"), encoding="utf-8")]
    f = lambda n: format(n, ",")
    print("=" * 92)
    print("게재지 정규화와 계열별 커버리지")
    print("=" * 92)

    raw_v = sum(1 for r in recs if r.get("venue"))
    norm_ok = 0
    disp = collections.defaultdict(collections.Counter)
    per_fam = collections.defaultdict(collections.Counter)
    for r in recs:
        n = normalize(r.get("venue"))
        if not n: continue
        norm_ok += 1
        disp[n][re.sub(r"\s+", " ", str(r["venue"])).strip()] += 1
        for fid in (r.get("families") or []): per_fam[fid][n] += 1

    print("\n전체 %s건 / 게재지 원값 보유 %s건 / 정규화 후 유효 %s건"
          % (f(len(recs)), f(raw_v), f(norm_ok)))
    print("  비게재지로 제외 %s건" % f(raw_v - norm_ok))

    print("\n[계열별 상위 N종 커버리지]  유효 게재지 보유 레코드 기준")
    print("  %-20s %8s %8s %8s %8s %8s %8s"
          % ("계열", "레코드", "고유", "상위20", "상위30", "상위40", "상위100"))
    summary = {}
    for fid, name in FAM.items():
        c = per_fam[fid]
        tot = sum(c.values())
        if not tot: continue
        cov = lambda k: 100.0 * sum(v for _, v in c.most_common(k)) / tot
        summary[fid] = {"records": tot, "unique": len(c),
                        "cov20": round(cov(20), 1), "cov30": round(cov(30), 1),
                        "cov40": round(cov(40), 1), "cov100": round(cov(100), 1)}
        print("  %-20s %8s %8s %7.1f%% %7.1f%% %7.1f%% %7.1f%%"
              % (name, f(tot), f(len(c)), cov(20), cov(30), cov(40), cov(100)))

    # 초안 목록
    out = {"generated_note": "정규화 키 기준. 표시는 최빈 원 표기.", "families": {}}
    lines = ["# 계열별 핵심 게재지 초안\n",
             "자동 추출. 확정 아님. 문서 수 기준 상위 40종.\n",
             "비게재지(프리프린트 서버, 심사 서비스, 데이터셋 레코드, 시리즈명)는 제외했다.\n",
             "표기 변이는 소문자 정규화, `Proceedings of the` 접두어 제거, 서수 제거, 연도 제거로 병합했다.\n"]
    for fid, name in FAM.items():
        c = per_fam[fid]
        if not c: continue
        tot = sum(c.values())
        lines.append("\n## %s\n" % name)
        lines.append("유효 레코드 %s건, 고유 게재지 %s종. 상위 40종이 %.1f퍼센트를 덮는다.\n"
                     % (f(tot), f(len(c)), 100.0 * sum(v for _, v in c.most_common(40)) / tot))
        lines.append("| 순위 | 게재지 | 건수 | 누적 % | 핵심 여부 |")
        lines.append("|---|---|---|---|---|")
        acc = 0
        rows = []
        for i, (k, v) in enumerate(c.most_common(40), 1):
            acc += v
            d = display(k, disp)
            lines.append("| %d | %s | %d | %.1f%% |  |" % (i, d, v, 100.0 * acc / tot))
            rows.append({"rank": i, "venue_display": d, "venue_key": k, "count": v,
                         "cum_pct": round(100.0 * acc / tot, 1)})
        out["families"][fid] = {"name": name, "records": tot, "unique": len(c),
                                "coverage": summary.get(fid), "top40": rows}
    with open(os.path.join(HERE, "venue_core_draft.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    json.dump(out, open(os.path.join(HERE, "venue_core_draft.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n저장: corpus/venue_core_draft.md, corpus/venue_core_draft.json")

if __name__ == "__main__":
    main()
