#!/usr/bin/env python3
"""상위 셀의 구성 문서. 3건짜리 셀은 한 문서가 평균을 끌어올렸을 수 있다."""
import gzip, json, statistics, sys
sys.path.insert(0, "/home/user/The_grid/namu")
from game_genre_list import GENRES

ITEMS = "/home/user/The_grid/items"
d = json.load(open(f"{ITEMS}/genre_matrix.json", encoding="utf-8"))

docs = []
for line in gzip.open(f"{ITEMS}/game_docs_2021-03-01.jsonl.gz", "rt", encoding="utf-8"):
    o = json.loads(line)
    o["genres"] = {c for c in o["categories"] if c in GENRES}
    if len(o["genres"]) >= 2: docs.append(o)

def members(a, b):
    return sorted([x for x in docs if a in x["genres"] and b in x["genres"]],
                  key=lambda x: -(x["len_plain"] or 0))

out = []
for r in d["few_long"]:
    a, b = r["pair"]
    ms = members(a, b)
    L = [m["len_plain"] for m in ms]
    C = [m["n_contrib_nobot"] for m in ms]
    print("\n%s × %s   n=%d 평균길이 %s 중앙길이 %s 평균기여 %s 중앙기여 %s" % (
        a, b, len(ms), format(round(statistics.mean(L)), ","),
        format(round(statistics.median(L)), ","),
        round(statistics.mean(C), 1), round(statistics.median(C))))
    for m in ms:
        print("    %-42s %7s자 %5s명" % (m["title"][:42], format(m["len_plain"], ","),
                                        m["n_contrib_nobot"]))
    out.append({"pair": [a, b], "n": len(ms),
                "mean_len": round(statistics.mean(L)), "median_len": round(statistics.median(L)),
                "mean_contrib": round(statistics.mean(C), 1),
                "median_contrib": round(statistics.median(C)),
                "max_len_share": round(max(L) / sum(L), 3),
                "docs": [{"title": m["title"], "len_plain": m["len_plain"],
                          "n_contrib_nobot": m["n_contrib_nobot"]} for m in ms]})

print("\n[표본 기준별 조합 수]")
cnt = {}
for th in (2, 3, 4, 5, 8, 10, 15, 20, 30):
    cnt[th] = sum(1 for v in d["cells"].values() if v["n"] >= th)
    print("  %2d건 이상 %4d종" % (th, cnt[th]))

json.dump({"snapshot_date": "2021-03-01", "few_long_members": out,
           "pairs_by_threshold": cnt},
          open(f"{ITEMS}/genre_matrix_cells.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
