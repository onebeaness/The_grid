#!/usr/bin/env python3
"""장르 × 장르 동시 출현 행렬. 게임 도메인.

셀 값 셋
  조합 문서 수
  조합 문서의 평균 본문 길이
  조합 문서의 평균 기여자 수 (봇 제외)

뒤의 둘은 인기도가 아니라 관심의 대리 지표다. 오래된 게임일수록 누적되는
시간 편향이 있다. 스냅샷은 2021-03-01 이므로 그 이후 형성된 조합은 없다.
"""
import gzip, json, math, statistics, sys, collections
sys.path.insert(0, "/home/user/The_grid/namu")
from game_genre_list import GENRES, KIND

ITEMS = "/home/user/The_grid/items"
SNAPSHOT = "2021-03-01"
TOPN = 25
MIN_CELL = 3

def main():
    docs = []
    for line in gzip.open(f"{ITEMS}/game_docs_{SNAPSHOT}.jsonl.gz", "rt", encoding="utf-8"):
        o = json.loads(line)
        g = sorted({c for c in o["categories"] if c in GENRES})
        o["genres"] = g
        docs.append(o)
    n_all = len(docs)
    with_g = [d for d in docs if d["genres"]]
    multi = [d for d in docs if len(d["genres"]) >= 2]

    gfreq = collections.Counter()
    for d in with_g:
        for g in d["genres"]: gfreq[g] += 1

    pair_docs = collections.defaultdict(list)
    for d in multi:
        g = d["genres"]
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                pair_docs[(g[i], g[j])].append(d)

    def agg(ds):
        L = [d["len_plain"] for d in ds if d.get("len_plain") is not None]
        C = [d["n_contrib_nobot"] for d in ds if d.get("n_contrib_nobot") is not None]
        return {"n": len(ds),
                "mean_len": round(statistics.mean(L)) if L else None,
                "median_len": round(statistics.median(L)) if L else None,
                "mean_contrib": round(statistics.mean(C), 1) if C else None,
                "median_contrib": round(statistics.median(C), 1) if C else None}

    cells = {"%s|%s" % k: agg(v) for k, v in pair_docs.items()}
    base = agg(with_g)
    base_multi = agg(multi)

    # 대각. 장르 단독 기준선
    diag = {g: agg([d for d in with_g if g in d["genres"]]) for g in gfreq}

    top = [g for g, _ in gfreq.most_common(TOPN)]
    # 상위 25 격자에서 빈 셀
    empty = []
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            k = tuple(sorted((top[i], top[j])))
            if not pair_docs.get(k): empty.append(list(k))

    # 5번 추출
    ok = [(k, v) for k, v in cells.items() if v["n"] >= MIN_CELL and v["mean_len"]]
    ns = sorted(v["n"] for _, v in ok)
    ls = sorted(v["mean_len"] for _, v in ok)
    q = lambda a, p: a[min(len(a) - 1, int(len(a) * p))]
    n_hi, n_lo = q(ns, 0.75), q(ns, 0.25)
    l_hi, l_lo = q(ls, 0.75), q(ls, 0.25)
    many_short = sorted([(k, v) for k, v in ok if v["n"] >= n_hi and v["mean_len"] <= l_lo],
                        key=lambda x: x[1]["mean_len"])
    few_long = sorted([(k, v) for k, v in ok if v["n"] <= n_lo and v["mean_len"] >= l_hi],
                      key=lambda x: -x[1]["mean_len"])

    out = {
     "snapshot_date": SNAPSHOT,
     "domain": "game",
     "proxy_note": ("본문 길이와 기여자 수는 인기도가 아니라 관심의 대리 지표. "
                    "오래된 게임일수록 누적되는 시간 편향 있음. 판매량과 리뷰 수는 덤프에 없음"),
     "contrib_note": "기여자 수는 namubot 과 관리자를 제외한 값",
     "docs_game": n_all, "docs_with_genre": len(with_g), "docs_multi_genre": len(multi),
     "genre_vocab": len(GENRES), "genre_used": len(gfreq),
     "pairs_total": len(pair_docs),
     "pairs_ge3": sum(1 for v in cells.values() if v["n"] >= MIN_CELL),
     "baseline_with_genre": base, "baseline_multi_genre": base_multi,
     "genre_freq": gfreq.most_common(),
     "genre_kind": {g: KIND.get(g) for g in gfreq},
     "diagonal": diag,
     "top_genres": top,
     "cells": cells,
     "empty_cells_top%d" % TOPN: empty,
     "thresholds": {"min_cell": MIN_CELL, "n_p75": n_hi, "n_p25": n_lo,
                    "len_p75": l_hi, "len_p25": l_lo},
     "many_short": [{"pair": k.split("|"), **v} for k, v in many_short],
     "few_long": [{"pair": k.split("|"), **v} for k, v in few_long],
    }
    json.dump(out, open(f"{ITEMS}/genre_matrix.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("게임 문서 %d" % n_all)
    print("장르 분류 1개 이상 %d (%.1f%%)" % (len(with_g), 100.0 * len(with_g) / n_all))
    print("장르 분류 2개 이상 %d (%.1f%%)" % (len(multi), 100.0 * len(multi) / n_all))
    print("어휘 %d종 중 실제 등장 %d종" % (len(GENRES), len(gfreq)))
    print("조합 %d종, 그중 3건 이상 %d종" % (len(pair_docs), out["pairs_ge3"]))
    print("기준선 (장르 있는 문서 전체) 평균 길이 %s 평균 기여자 %s"
          % (base["mean_len"], base["mean_contrib"]))
    print("기준선 (복수 장르 문서) 평균 길이 %s 평균 기여자 %s"
          % (base_multi["mean_len"], base_multi["mean_contrib"]))
    print("상위 %d 격자의 빈 셀 %d / %d" % (TOPN, len(empty), TOPN * (TOPN - 1) // 2))

if __name__ == "__main__":
    main()
