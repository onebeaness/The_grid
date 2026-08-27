"""수집 결과 후처리. 레코드를 지우지 않고 표시만 한다.
 - junk: 학술 논문이 아닌 항목(도서 판매 페이지, 목차, 정오표 등)
 - dup_group: 정규화 제목이 같은 근접 중복. 대표 1건만 rep=True
"""
import json, os, re, collections
import sources as S

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDS = os.path.join(HERE, "records.jsonl")

JUNK_RX = [
    re.compile(r"^\s*(download|read)\s+(pdf|online|book)", re.I),
    re.compile(r"^\s*(front|back)\s+matter\s*$", re.I),
    re.compile(r"^\s*(table of contents|contents|index|colophon|masthead)\s*$", re.I),
    re.compile(r"^\s*editorial\s+(board|advisory)", re.I),
    re.compile(r"^\s*(erratum|corrigendum|correction to|retraction)\b", re.I),
    re.compile(r"^\s*(list of (reviewers|contributors)|acknowledge?ment of reviewers)", re.I),
    re.compile(r"^\s*(author|subject)\s+index\s*$", re.I),
    re.compile(r"^\s*(issue information|cover image|frontmatter|backmatter)", re.I),
    re.compile(r"^\s*(book\s+reviews?|reviewed work|review of)\s*[:.]?\s*$", re.I),
    re.compile(r"^\s*(abstracts?|proceedings)\s+of\s+the\b", re.I),
    re.compile(r"^\s*call for papers", re.I),
]

def is_junk(r):
    t = (r.get("title") or "").strip()
    if len(t) < 12: return "title_too_short"
    for rx in JUNK_RX:
        if rx.search(t): return "non_article_title"
    letters = sum(c.isalpha() for c in t)
    if letters < len(t) * 0.5: return "title_mostly_nonalpha"
    return None

def main():
    recs = []
    for line in open(RECORDS, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        try: recs.append(json.loads(line))
        except Exception: pass

    n_junk = 0
    for r in recs:
        j = is_junk(r)
        r["junk"] = bool(j)
        r["junk_reason"] = j
        if j: n_junk += 1

    groups = collections.defaultdict(list)
    for r in recs:
        nt = r.get("norm_title") or ""
        if nt: groups[nt].append(r)

    n_dup = 0
    for nt, g in groups.items():
        if len(g) == 1:
            g[0]["dup_group"] = None; g[0]["rep"] = True; continue
        # 대표: 초록 있음 > 인용수 > DOI 있음 > 소스 수
        g.sort(key=lambda r: (0 if r.get("abstract") else 1,
                              -(r.get("citations") or 0),
                              0 if r.get("doi") else 1,
                              -len(r.get("sources") or [])))
        gid = "g:" + nt[:100]
        for i, r in enumerate(g):
            r["dup_group"] = gid
            r["rep"] = (i == 0)
            if i: n_dup += 1

    tmp = RECORDS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, RECORDS)
    usable = sum(1 for r in recs if r["rep"] and not r["junk"])
    S.log("[postprocess] 총 %d건. 비논문 표시 %d, 근접중복 비대표 %d, 유효 대표 %d"
          % (len(recs), n_junk, n_dup, usable))

if __name__ == "__main__":
    main()
