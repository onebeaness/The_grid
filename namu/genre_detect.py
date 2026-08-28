#!/usr/bin/env python3
"""장르 문서 판정. 분류 기반과 본문 기반을 나눠 재고 합산 효과를 본다.

이전 판정기는 분류 기반을 도메인 소속 판정으로 잘못 정의했다.
1936 베를린 올림픽이 잡히는 식이었다. 실제 장르 문서를 보고 다시 정의한다.

관측한 장르 문서의 성질
  로그라이크   분류 로그라이크 게임 / 절 로그라이크 게임들이 공유하는 특징 / 총칭하는 말
  대전 액션 게임 분류 대전 액션 / 액션 게임 장르. 격투기를 게임으로 옮긴 장르다
  다크 판타지   분류 다크 판타지 / 판타지 장르의 일종으로 ... 판타지 장르이다
  느와르       분류 느와르 영화, 장르 / 절 문예의 한 장르
"""
import argparse, collections, glob, gzip, json, os, random, re, sys, time

SNAPSHOT = "2021-03-01"
ITEMS = "/home/user/The_grid/items"

# ---------- 신호 A. 문서 제목과 분류명의 겹침 ----------
# 제목이 곧 범주명이면 그 문서는 범주의 대표 문서다. 개별 사례가 아니다.
def cat_title_overlap(title, cats, domain_cats=None):
    """domain_cats 가 주어지면 겹치는 분류가 도메인에 걸린 것일 때만 인정한다.
    1933년과 1007번 지방도도 동명 분류를 갖는다. 도메인 제약이 없으면 전부 통과한다."""
    t = title.strip()
    if not t or "/" in t: return 0, []
    why = []
    for c in cats:
        c = c.strip()
        if domain_cats is not None and c not in domain_cats: continue
        if c == t: why.append("분류=제목:" + c); return 3, why
        if c.startswith(t + " ") or c.endswith(" " + t): why.append("분류⊃제목:" + c); return 3, why
        if t.startswith(c + " ") or t.endswith(" " + c): why.append("제목⊃분류:" + c); return 2, why
    return 0, why

# ---------- 신호 B. 장르 분류 자체 ----------
GENRE_CAT = re.compile(r"(^|\s)(장르|서브\s*장르|하위\s*장르)(\s|$|/)")

# ---------- 신호 C. 머리말 정의 구문 ----------
DEF_STRONG = re.compile(
    r"장르(이다|다\.|다\s|의\s*일종|의\s*하나|를\s*말한|를\s*뜻|를\s*가리키|를\s*지칭|로\s*분류|명)")
DEF_TOTAL = re.compile(r"(총칭|통칭|일컫는\s*말|이르는\s*말|부르는\s*말|아우르는)")
DEF_ONEOF = re.compile(r"(의\s*일종|의\s*한\s*갈래|의\s*하위\s*갈래|에서\s*파생|파생된)")

# ---------- 신호 D. 장르 문서 특유의 절 구성 ----------
SEC_SHARED = re.compile(r"(공유하는\s*특징|특징|클리셰|관습|요소|정의|기원|유래|역사|계보)")
SEC_WORKS = re.compile(r"(대표작|작품|목록|해당\s*작품|주요\s*작품)")
SEC_SUB = re.compile(r"(하위\s*장르|파생|세부\s*분류|분류|갈래)")

# ---------- 신호 E. 제목과 같은 이름의 분류가 거느린 하위 문서 수 ----------
# 장르는 정의상 여러 작품을 거느린다. 로그라이크에는 103편, 고량주에는 0편이 딸린다.
# 규칙 미세조정이 아니라 문서 바깥의 구조를 보는 신호다.
def load_cat_index(path):
    """분류명 -> 하위 문서 수. 첫 토큰과 끝 토큰으로 색인해 접두·접미 대조를 싸게 한다."""
    sz = {}
    for line in open(path, encoding="utf-8"):
        try: o = json.loads(line)
        except Exception: continue
        c = o.get("category")
        if c: sz[c] = o.get("doc_count") or 0
    first, last = collections.defaultdict(list), collections.defaultdict(list)
    for c, n in sz.items():
        t = c.split()
        if not t: continue
        first[t[0]].append((c, n)); last[t[-1]].append((c, n))
    return sz, first, last

def sub_count(title, idx):
    """제목과 같은 이름이거나 제목으로 시작·끝나는 분류의 하위 문서 수. 최대값을 쓴다.
    로그라이크 -> 분류:로그라이크 게임 103. 서부극 -> 분류:서부극 59."""
    sz, first, last = idx
    t = title.split("/")[0].strip()
    if not t: return 0, None
    best, bc = 0, None
    if t in sz: best, bc = sz[t], t
    tt = t.split()
    for c, n in first.get(tt[0], ()):
        if c.startswith(t + " ") and n > best: best, bc = n, c
    for c, n in last.get(tt[-1], ()):
        if c.endswith(" " + t) and n > best: best, bc = n, c
    return best, bc

# ---------- 제목 접미 ----------
TITLE_SUFFIX = re.compile(r"(물|라이크|라이트|풍|계열|장르|주의|파|사조|양식)$")

def lead_sentence(secs):
    """개요 첫 문장. 사람이 눈으로 판정할 때 쓰는 근거."""
    head = ""
    for sec in secs or []:
        nm = sec.get("title") or ""
        if sec.get("number") == "0" or re.search(r"(개요|설명|정의|소개)", nm):
            head = (sec.get("text") or "").strip()
            if head: break
    if not head and secs:
        head = (secs[0].get("text") or "").strip()
    head = re.sub(r"\s+", " ", head)
    m = re.search(r"^(.{5,200}?[.!?]|.{5,200}?다\.)(\s|$)", head)
    return (m.group(1) if m else head[:200]).strip()

def signals(rec, domain_cats=None):
    title = (rec.get("title") or "").strip()
    cats = rec.get("categories") or []
    secs = rec.get("sections") or []

    # 분류 기반
    a, why_a = cat_title_overlap(title, cats, domain_cats)
    if any(GENRE_CAT.search(c) for c in cats):
        a += 3; why_a.append("장르분류")
    cat_score, cat_why = a, why_a

    # 본문 기반
    head = ""
    for s in secs:
        nm = (s.get("title") or "")
        if s.get("number") == "0" or re.search(r"(개요|설명|정의|소개)", nm):
            head += (s.get("text") or "")[:900]
        if len(head) >= 900: break
    if not head and secs:
        head = (secs[0].get("text") or "")[:900]
    sec_titles = " ".join((s.get("title") or "") for s in secs)

    b, why_b = 0, []
    if DEF_STRONG.search(head): b += 3; why_b.append("장르정의")
    if DEF_TOTAL.search(head): b += 2; why_b.append("총칭구문")
    if DEF_ONEOF.search(head): b += 2; why_b.append("일종/파생")
    n = 0
    if SEC_SHARED.search(sec_titles): n += 1
    if SEC_WORKS.search(sec_titles): n += 1
    if SEC_SUB.search(sec_titles): n += 1
    if n >= 2: b += 2; why_b.append("장르절%d" % n)
    elif n == 1: b += 1; why_b.append("장르절1")
    if TITLE_SUFFIX.search(title) and "/" not in title:
        b += 1; why_b.append("제목접미")
    return cat_score, cat_why, b, why_b

SUB_GRID = (0, 1, 3, 5, 10, 20, 50)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", default=os.path.join(ITEMS, "shards"))
    ap.add_argument("--rate", type=float, default=0.10, help="표집 비율. 1.0 이면 전수")
    ap.add_argument("--seed", type=int, default=20210301)
    ap.add_argument("--cat-th", type=int, default=3)
    ap.add_argument("--body-th", type=int, default=4)
    ap.add_argument("--sub-th", type=int, default=5, help="하위 문서 수 임계. 확정 후보에 적용")
    ap.add_argument("--out", default=ITEMS)
    ap.add_argument("--tag", default="")
    ap.add_argument("--emit-candidates", default="", help="합집합 후보 전체를 jsonl 로 기록")
    ap.add_argument("--no-domain-constraint", action="store_true")
    a = ap.parse_args()

    domain_cats = None
    if not a.no_domain_constraint:
        domain_cats = set()
        for line in open(os.path.join(ITEMS, "genres.jsonl"), encoding="utf-8"):
            try: o = json.loads(line)
            except Exception: continue
            if o.get("domain_proposals"): domain_cats.add(o["category"])
        sys.stderr.write("[genre] 도메인 걸린 분류 %d종으로 제약\n" % len(domain_cats))
    idx = load_cat_index(os.path.join(ITEMS, "genres.jsonl"))
    sys.stderr.write("[genre] 분류 하위 문서 수 색인 %d종\n" % len(idx[0]))

    files = sorted(glob.glob(os.path.join(a.shards, "*.jsonl.gz")))
    files = [f for f in files if os.path.exists(f[:-len(".jsonl.gz")] + ".done")]
    rng = random.Random(a.seed)
    n = 0
    st = collections.Counter()
    curve = collections.Counter()          # (경로, 임계) -> 잔존 건수
    only_body, only_cat, both = [], [], []
    emit = open(a.emit_candidates, "w", encoding="utf-8") if a.emit_candidates else None
    t0 = time.time()
    for f in files:
        for line in gzip.open(f, "rt", encoding="utf-8"):
            if a.rate < 1.0 and rng.random() > a.rate: continue
            try: r = json.loads(line)
            except Exception: continue
            if r.get("is_redirect"): continue
            n += 1
            cs, cw, bs, bw = signals(r, domain_cats)
            c_hit, b_hit = cs >= a.cat_th, bs >= a.body_th
            if not (c_hit or b_hit): continue
            sc, sname = sub_count(r["title"], idx)
            path = "둘다" if (c_hit and b_hit) else ("분류만" if c_hit else "본문만")
            st["분류판정"] += c_hit; st["본문판정"] += b_hit; st[path] += 1
            for g in SUB_GRID:
                if sc >= g:
                    curve[("합집합", g)] += 1
                    curve[(path, g)] += 1
            row = {"title": r["title"], "cat_score": cs, "body_score": bs,
                   "cat_why": cw, "body_why": bw, "path": path,
                   "sub_count": sc, "sub_cat": sname,
                   "categories": (r.get("categories") or [])[:6],
                   "lead": lead_sentence(r.get("sections"))}
            if emit and sc >= a.sub_th: emit.write(json.dumps(row, ensure_ascii=False) + "\n")
            if sc < a.sub_th: continue          # 표본은 신호 적용 후 기준
            if path == "둘다" and len(both) < 60: both.append(row)
            elif path == "본문만" and len(only_body) < 80: only_body.append(row)
            elif path == "분류만" and len(only_cat) < 80: only_cat.append(row)
    if emit: emit.close()
    el = time.time() - t0
    union0 = curve[("합집합", 0)]
    print("표본 %d문서 (표집률 %.2f)  %.1f분" % (n, a.rate, el / 60))
    print("  임계 분류>=%d 본문>=%d 하위문서>=%d" % (a.cat_th, a.body_th, a.sub_th))
    print("\n[신호 적용 전]")
    for k in ("분류판정", "본문판정", "분류만", "본문만", "둘다"):
        print("  %-6s %7d  %5.2f%%" % (k, st[k], 100.0 * st[k] / max(n, 1)))
    print("  합집합 %7d  %5.2f%%" % (union0, 100.0 * union0 / max(n, 1)))
    print("\n[하위 문서 수 임계별 잔존]")
    print("  %6s %10s %10s %10s %10s" % ("임계", "합집합", "분류만", "본문만", "둘다"))
    for g in SUB_GRID:
        print("  %6d %10d %10d %10d %10d" % (g, curve[("합집합", g)],
              curve[("분류만", g)], curve[("본문만", g)], curve[("둘다", g)]))
    print("\n[본문만 · 신호 통과 25]")
    for r in only_body[:25]:
        print("  b=%d n=%-5d %-24s %-22s %s" % (r["body_score"], r["sub_count"],
              r["title"][:24], ",".join(r["body_why"])[:22], (r["sub_cat"] or "")[:24]))
    print("\n[분류만 · 신호 통과 25]")
    for r in only_cat[:25]:
        print("  c=%d n=%-5d %-24s %s" % (r["cat_score"], r["sub_count"],
              r["title"][:24], ",".join(r["cat_why"])[:40]))
    tag = ("_" + a.tag) if a.tag else ""
    json.dump({"snapshot_date": SNAPSHOT, "sampled": n, "rate": a.rate,
               "cat_threshold": a.cat_th, "body_threshold": a.body_th,
               "sub_threshold": a.sub_th, "stats": dict(st),
               "sub_curve": {"%s|%d" % k: v for k, v in curve.items()},
               "elapsed_min": round(el / 60, 1),
               "sample_body_only": only_body, "sample_cat_only": only_cat,
               "sample_both": both},
              open(os.path.join(a.out, "genre_detect_%s%s.json" % (SNAPSHOT, tag)), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
