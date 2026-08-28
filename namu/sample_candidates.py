#!/usr/bin/env python3
"""정밀도 채점용 무작위 표본 추출.

앞쪽 N건을 모으는 방식은 제목 정렬 앞쪽에 몰린다. 신호 적용 전후를
비교하려면 같은 방식의 무작위 표집이어야 한다.
"""
import argparse, json, random, sys

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--min-sub", type=int, default=0)
ap.add_argument("--n", type=int, default=40)
ap.add_argument("--seed", type=int, default=20210301)
ap.add_argument("--by-path", action="store_true", help="경로별로 n건씩")
a = ap.parse_args()

rows = []
for line in open(a.src, encoding="utf-8"):
    o = json.loads(line)
    if o.get("sub_count", 0) >= a.min_sub: rows.append(o)
rng = random.Random(a.seed)
groups = {"전체": rows}
if a.by_path:
    groups = {}
    for r in rows: groups.setdefault(r["path"], []).append(r)
sys.stderr.write("모집단 %d건\n" % len(rows))
for g, L in sorted(groups.items()):
    pick = rng.sample(L, min(a.n, len(L)))
    print("\n### %s  (모집단 %d)" % (g, len(L)))
    for r in sorted(pick, key=lambda x: x["title"]):
        print("- %s | n=%d | c=%d b=%d | %s | %s" % (
            r["title"], r["sub_count"], r["cat_score"], r["body_score"],
            ",".join(r["categories"][:3])[:50], (r["lead"] or "")[:110]))
