#!/usr/bin/env python3
"""관측 편향 확인.

장르 분류 2개 이상인 문서와 1개 이하인 문서를 비교한다.
앞쪽이 길고 기여자가 많으면 관측 대상이 이미 인기순으로 걸러진 것이고,
셀 평균 길이를 인기도로 읽는 것이 순환이 된다.
"""
import gzip, json, re, statistics, sys, collections
sys.path.insert(0, "/home/user/The_grid/namu")
from game_genre_list import GENRES

ITEMS = "/home/user/The_grid/items"
YEAR = re.compile(r"^((?:19|20)\d\d)년 게임(/|$)")

docs = []
for line in gzip.open(f"{ITEMS}/game_docs_2021-03-01.jsonl.gz", "rt", encoding="utf-8"):
    o = json.loads(line)
    o["ng"] = len({c for c in o["categories"] if c in GENRES})
    ys = [int(m.group(1)) for c in o["categories"] for m in [YEAR.match(c)] if m]
    o["year"] = min(ys) if ys else None
    docs.append(o)

def desc(ds):
    L = [d["len_plain"] for d in ds if d.get("len_plain") is not None]
    C = [d["n_contrib_nobot"] for d in ds if d.get("n_contrib_nobot") is not None]
    Y = [d["year"] for d in ds if d["year"]]
    q = lambda a, p: sorted(a)[min(len(a) - 1, int(len(a) * p))] if a else None
    return {"n": len(ds),
            "mean_len": round(statistics.mean(L)) if L else None,
            "median_len": round(statistics.median(L)) if L else None,
            "p90_len": q(L, 0.90), "p10_len": q(L, 0.10),
            "mean_contrib": round(statistics.mean(C), 1) if C else None,
            "median_contrib": round(statistics.median(C)) if C else None,
            "p90_contrib": q(C, 0.90),
            "year_n": len(Y), "median_year": round(statistics.median(Y)) if Y else None,
            "mean_year": round(statistics.mean(Y), 1) if Y else None}

groups = {"장르 2개 이상": [d for d in docs if d["ng"] >= 2],
          "장르 1개": [d for d in docs if d["ng"] == 1],
          "장르 0개": [d for d in docs if d["ng"] == 0],
          "장르 1개 이하": [d for d in docs if d["ng"] <= 1],
          "전체 게임 문서": docs}
res = {k: desc(v) for k, v in groups.items()}

print("%-14s %6s %8s %8s %8s %8s %8s %7s %7s" %
      ("집단", "문서", "평균길이", "중앙길이", "p90길이", "평균기여", "중앙기여", "p90기여", "중앙연도"))
for k in ("장르 2개 이상", "장르 1개", "장르 0개", "장르 1개 이하", "전체 게임 문서"):
    r = res[k]
    print("%-14s %6d %8s %8s %8s %8s %8s %7s %7s" % (
        k, r["n"], format(r["mean_len"], ","), format(r["median_len"], ","),
        format(r["p90_len"], ","), r["mean_contrib"], r["median_contrib"],
        r["p90_contrib"], r["median_year"]))

print("\n[장르 개수별]")
byn = collections.defaultdict(list)
for d in docs: byn[min(d["ng"], 5)].append(d)
for k in sorted(byn):
    r = desc(byn[k])
    print("  장르 %s개%s  n=%5d 평균길이 %7s 중앙길이 %6s 평균기여 %6s 중앙연도 %s" % (
        k, "+" if k == 5 else " ", r["n"], format(r["mean_len"], ","),
        format(r["median_len"], ","), r["mean_contrib"], r["median_year"]))

print("\n[발매 연도 분포. 연도 분류 있는 문서만]")
ya = collections.Counter(); yb = collections.Counter()
for d in docs:
    if not d["year"]: continue
    (ya if d["ng"] >= 2 else yb)[d["year"] // 5 * 5] += 1
print("  %6s %8s %8s %8s" % ("연대", "2개이상", "1개이하", "2개이상비율"))
for y in sorted(set(ya) | set(yb)):
    a, b = ya[y], yb[y]
    print("  %4d년대 %7d %8d %10.1f%%" % (y, a, b, 100.0 * a / max(a + b, 1)))

json.dump({"snapshot_date": "2021-03-01", "groups": res,
           "by_genre_count": {str(k): desc(v) for k, v in byn.items()},
           "year_multi": dict(ya), "year_single": dict(yb)},
          open(f"{ITEMS}/genre_matrix_bias.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
