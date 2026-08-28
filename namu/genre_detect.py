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

# ---------- 제목 접미 ----------
TITLE_SUFFIX = re.compile(r"(물|라이크|라이트|풍|계열|장르|주의|파|사조|양식)$")

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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", default=os.path.join(ITEMS, "shards"))
    ap.add_argument("--rate", type=float, default=0.10, help="표집 비율. 1.0 이면 전수")
    ap.add_argument("--seed", type=int, default=20210301)
    ap.add_argument("--cat-th", type=int, default=3)
    ap.add_argument("--body-th", type=int, default=4)
    ap.add_argument("--out", default=ITEMS)
    ap.add_argument("--no-domain-constraint", action="store_true")
    a = ap.parse_args()

    domain_cats = None
    if not a.no_domain_constraint:
        domain_cats = set()
        gp = os.path.join(ITEMS, "genres.jsonl")
        for line in open(gp, encoding="utf-8"):
            try: o = json.loads(line)
            except Exception: continue
            if o.get("domain_proposals"): domain_cats.add(o["category"])
        sys.stderr.write("[genre] 도메인 걸린 분류 %d종으로 제약\n" % len(domain_cats))

    files = sorted(glob.glob(os.path.join(a.shards, "*.jsonl.gz")))
    files = [f for f in files if os.path.exists(f[:-len(".jsonl.gz")] + ".done")]
    rng = random.Random(a.seed)
    n = 0
    st = collections.Counter()
    only_body, only_cat, both = [], [], []
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
            st["분류판정"] += c_hit; st["본문판정"] += b_hit
            st["둘다"] += (c_hit and b_hit)
            st["분류만"] += (c_hit and not b_hit)
            st["본문만"] += (b_hit and not c_hit)
            row = {"title": r["title"], "cat_score": cs, "body_score": bs,
                   "cat_why": cw, "body_why": bw, "categories": (r.get("categories") or [])[:3]}
            if c_hit and b_hit and len(both) < 50: both.append(row)
            elif b_hit and not c_hit and len(only_body) < 80: only_body.append(row)
            elif c_hit and not b_hit and len(only_cat) < 80: only_cat.append(row)
    el = time.time() - t0
    tot_union = st["분류판정"] + st["본문만"]
    print("표본 %d문서 (표집률 %.2f)  %.1f분" % (n, a.rate, el / 60))
    print("  임계 분류>=%d 본문>=%d" % (a.cat_th, a.body_th))
    print("\n[판정]")
    for k in ("분류판정", "본문판정", "둘다", "분류만", "본문만"):
        print("  %-8s %7d  %5.2f%%" % (k, st[k], 100.0 * st[k] / max(n, 1)))
    print("\n  분류 기반만            %7d  (%.2f%%)" % (st["분류판정"], 100.0 * st["분류판정"] / max(n, 1)))
    print("  본문 기반 추가 시       %7d  (%.2f%%)" % (tot_union, 100.0 * tot_union / max(n, 1)))
    print("  증가                 %+7d  (%+.1f%% 상대)" % (st["본문만"], 100.0 * st["본문만"] / max(st["분류판정"], 1)))
    print("  교집합 비율            %.1f%% (본문판정 중)" % (100.0 * st["둘다"] / max(st["본문판정"], 1)))
    print("\n[본문에서만 잡힌 문서 25]")
    for r in only_body[:25]:
        print("  b=%d %-30s %-26s %s" % (r["body_score"], r["title"][:30],
              ",".join(r["body_why"]), ",".join(r["categories"][:2])[:36]))
    print("\n[분류에서만 잡힌 문서 15]")
    for r in only_cat[:15]:
        print("  c=%d %-30s %s" % (r["cat_score"], r["title"][:30], ",".join(r["cat_why"])[:52]))
    json.dump({"snapshot_date": SNAPSHOT, "sampled": n, "rate": a.rate,
               "cat_threshold": a.cat_th, "body_threshold": a.body_th,
               "stats": dict(st), "union": tot_union, "elapsed_min": round(el / 60, 1),
               "sample_body_only": only_body, "sample_cat_only": only_cat, "sample_both": both},
              open(os.path.join(a.out, "genre_detect_%s.json" % SNAPSHOT), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
