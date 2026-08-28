#!/usr/bin/env python3
"""본문 기반 장르 문서 판정. 분류 기반과 비교.

분류 체계가 향유 대상 중심이 아니므로 분류만으로는 장르를 뽑는 데 상한이 있다.
상위 1,000종 커버리지 46퍼센트, 상위권이 독립운동가와 철도역과 위키 관리용 분류.

장르 문서는 본문에 장르 정의, 공유 특징, 파생 관계가 서술된다는 성질을 쓴다.
"""
import argparse, collections, glob, gzip, json, os, random, re, sys, time

SNAPSHOT = "2021-03-01"
ITEMS = "/home/user/The_grid/items"

# ---------- 제목 기반 ----------
TITLE_SUFFIX = re.compile(
    r"(물|라이크|라이트|풍|계열|장르|주의|파|사조|양식|기법|스타일|형식)$")
TITLE_GENREWORD = re.compile(
    r"(장르|하위\s*장르|서브\s*장르)")

# ---------- 본문 정의 구문 ----------
# 개요 절에서 "X는 ... 장르이다" 형태
DEF_GENRE = re.compile(
    r"장르(이|중|의\s*하나|를\s*뜻|를\s*말|를\s*가리키|다\.|이다|입니다|로\s*분류)")
DEF_ONEOF = re.compile(r"(의\s*일종|의\s*한\s*갈래|의\s*하위\s*장르|에서\s*파생|파생된\s*장르)")
DEF_TERM = re.compile(r"(을|를)\s*(통칭|지칭|일컫|이르는\s*말)")
# 장르 문서에 흔한 절 제목
SEC_GENRE = re.compile(r"(특징|클리셰|대표작|하위\s*장르|역사|기원|정의|유래|분류)")
# 파생 관계 서술
DERIV = re.compile(r"(파생|영향을\s*받|시초|원조|효시|계보|아류|서브\s*장르)")

def title_signal(title):
    t = title.strip()
    if "/" in t: return 0, []      # 하위 문서는 장르 문서가 아님
    s, why = 0, []
    if TITLE_SUFFIX.search(t): s += 2; why.append("제목접미")
    if TITLE_GENREWORD.search(t): s += 2; why.append("제목장르어")
    return s, why

def body_signal(rec, head_chars=1200):
    """개요 성격의 앞부분과 절 제목을 본다."""
    secs = rec.get("sections") or []
    head = ""
    for s in secs:
        nm = (s.get("title") or "")
        if s.get("number") == "0" or "개요" in nm or "정의" in nm or "소개" in nm:
            head += (s.get("text") or "")[:head_chars]
        if len(head) >= head_chars: break
    if not head:
        head = "".join((s.get("text") or "")[:400] for s in secs[:2])[:head_chars]
    sec_titles = " ".join((s.get("title") or "") for s in secs)

    s, why = 0, []
    if DEF_GENRE.search(head): s += 3; why.append("장르정의구문")
    if DEF_ONEOF.search(head): s += 2; why.append("일종/파생구문")
    if DEF_TERM.search(head): s += 1; why.append("통칭구문")
    n_sec = len(SEC_GENRE.findall(sec_titles))
    if n_sec >= 2: s += 2; why.append("장르절구성%d" % n_sec)
    elif n_sec == 1: s += 1; why.append("장르절1")
    if DERIV.search(head): s += 1; why.append("파생서술")
    return s, why

def cat_signal(rec, domain_cats):
    """분류 기반. 분류명이 도메인 키워드에 걸리는지."""
    cs = rec.get("categories") or []
    hit = [c for c in cs if c in domain_cats]
    return (2 if hit else 0), (["분류:" + hit[0]] if hit else [])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", default=os.path.join(ITEMS, "shards"))
    ap.add_argument("--sample", type=int, default=40000, help="0이면 전수")
    ap.add_argument("--seed", type=int, default=20210301)
    ap.add_argument("--threshold", type=int, default=3)
    ap.add_argument("--out", default=ITEMS)
    a = ap.parse_args()

    # 도메인에 걸린 분류명 집합
    domain_cats = set()
    gp = os.path.join(ITEMS, "genres.jsonl")
    if os.path.exists(gp):
        for line in open(gp, encoding="utf-8"):
            try: o = json.loads(line)
            except Exception: continue
            if o.get("domain_proposals"): domain_cats.add(o["category"])
    sys.stderr.write("[genre] 도메인 걸린 분류 %d종\n" % len(domain_cats))

    files = sorted(glob.glob(os.path.join(a.shards, "*.jsonl.gz")))
    files = [f for f in files if os.path.exists(f[:-len(".jsonl.gz")] + ".done")]
    rng = random.Random(a.seed)
    keep = 1.0 if not a.sample else None

    n = 0
    stat = collections.Counter()
    both, only_cat, only_body, neither = [], [], [], []
    t0 = time.time()
    for f in files:
        for line in gzip.open(f, "rt", encoding="utf-8"):
            try: r = json.loads(line)
            except Exception: continue
            if r.get("is_redirect"): continue
            if a.sample and rng.random() > 0.08: continue   # 약 8퍼센트 표집
            n += 1
            cs, cw = cat_signal(r, domain_cats)
            ts, tw = title_signal(r.get("title") or "")
            bs, bw = body_signal(r)
            cat_hit = cs >= 2
            body_hit = (ts + bs) >= a.threshold
            stat["분류판정"] += cat_hit
            stat["본문판정"] += body_hit
            stat["둘다"] += (cat_hit and body_hit)
            stat["분류만"] += (cat_hit and not body_hit)
            stat["본문만"] += (body_hit and not cat_hit)
            stat["둘다아님"] += (not cat_hit and not body_hit)
            row = {"title": r["title"], "cat": cw, "why": tw + bw,
                   "score": ts + bs, "n_cat": len(r.get("categories") or [])}
            if cat_hit and body_hit and len(both) < 40: both.append(row)
            elif body_hit and not cat_hit and len(only_body) < 60: only_body.append(row)
            elif cat_hit and not body_hit and len(only_cat) < 60: only_cat.append(row)
            if a.sample and n >= a.sample: break
        if a.sample and n >= a.sample: break

    el = time.time() - t0
    print("표본 %d문서  %.1f분" % (n, el / 60))
    print("\n[판정 결과]")
    for k in ("분류판정", "본문판정", "둘다", "분류만", "본문만", "둘다아님"):
        print("  %-8s %7d  %5.2f%%" % (k, stat[k], 100.0 * stat[k] / max(n, 1)))
    print("\n  분류 기반만: %d건" % stat["분류판정"])
    print("  본문 기반 추가 시: %d건 (증가 %+d, %+.1f%%)"
          % (stat["분류판정"] + stat["본문만"], stat["본문만"],
             100.0 * stat["본문만"] / max(stat["분류판정"], 1)))

    print("\n[본문에서만 잡힌 문서 표본 20]")
    for r in only_body[:20]:
        print("  score=%d %-34s %s" % (r["score"], r["title"][:34], ",".join(r["why"])))
    print("\n[분류에서만 잡힌 문서 표본 12]")
    for r in only_cat[:12]:
        print("  %-40s %s" % (r["title"][:40], ",".join(r["cat"])))

    json.dump({"snapshot_date": SNAPSHOT, "sampled": n, "threshold": a.threshold,
               "stats": dict(stat), "elapsed_min": round(el / 60, 1),
               "sample_body_only": only_body, "sample_cat_only": only_cat,
               "sample_both": both},
              open(os.path.join(a.out, "genre_detect_%s.json" % SNAPSHOT), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
