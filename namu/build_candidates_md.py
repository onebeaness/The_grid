#!/usr/bin/env python3
"""장르 후보 목록. 사람이 눈으로 판정하기 위한 산출물.

판정 경로별로 나눠 싣는다. 경로마다 정밀도가 다르므로 위에서부터 보다가
멈출 수 있게 한다. 하위 문서 수는 열로만 두고 거르는 데 쓰지 않는다.
표본 채점에서 이 신호가 정밀도와 재현을 동시에 떨어뜨렸기 때문이다.
"""
import json, re, sys

SRC = "/home/user/The_grid/items/genre_candidates_all.jsonl"
OUT = "/home/user/The_grid/items/genre_candidates.md"
ORDER = ["둘다", "본문만", "분류만"]
HEAD = {
 "둘다":  ("분류 경로와 본문 경로가 모두 잡은 문서",
           "표본 20건 채점에서 장르 13건. 정밀도 65퍼센트. 세 경로 중 가장 높음"),
 "본문만": ("본문 경로만 잡은 문서",
           "표본 20건 채점에서 장르 0건에서 2건. 정밀도 0에서 10퍼센트"),
 "분류만": ("분류 경로만 잡은 문서",
           "표본 20건 채점에서 장르 5건. 정밀도 25퍼센트. 부피의 81퍼센트가 여기"),
}

def clean(s, n):
    s = re.sub(r"\s+", " ", s or "").replace("|", "／").strip()
    return s[:n] + ("…" if len(s) > n else "")

rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
by = {}
for r in rows: by.setdefault(r["path"], []).append(r)

w = open(OUT, "w", encoding="utf-8")
w.write("# 장르 후보 목록\n\n")
w.write("스냅샷 2021-03-01. 전수 571,375문서. 합집합 %d건.\n\n" % len(rows))
w.write("판정 주체는 규칙. 사람 확인 대기.\n\n")
w.write("## 읽는 법\n\n")
w.write("- 경로: 어느 신호가 잡았는지. 정밀도가 경로마다 다름\n")
w.write("- 하위: 문서 제목과 같은 이름의 분류가 거느린 문서 수\n")
w.write("- 하위 문서 수는 열로만 둠. 거르는 데 쓰지 않음\n")
w.write("- 확인된 장르 문서 52편 중 19편이 하위 문서 수 0. 교향시, 그라인드코어,\n")
w.write("  보사노바, 재즈 록, 데스코어, 칩튠이 여기 해당. 임계를 걸면 이들이 사라짐\n\n")
w.write("## 경로별 규모\n\n| 경로 | 건수 | 비중 |\n|---|---|---|\n")
for p in ORDER:
    n = len(by.get(p, []))
    w.write("| %s | %d | %.1f%% |\n" % (p, n, 100.0 * n / len(rows)))
w.write("| 합계 | %d | 100.0%% |\n\n" % len(rows))

for p in ORDER:
    L = sorted(by.get(p, []), key=lambda r: r["title"])
    t, note = HEAD[p]
    w.write("\n## %s. %d건\n\n%s\n\n" % (t, len(L), note))
    w.write("| 제목 | 분류 | 하위 | 근거 | 개요 첫 문장 |\n|---|---|---|---|---|\n")
    for r in L:
        why = ",".join((r["cat_why"] or []) + (r["body_why"] or []))
        w.write("| %s | %s | %d | %s | %s |\n" % (
            clean(r["title"], 40), clean(", ".join(r["categories"][:3]), 46),
            r["sub_count"], clean(why, 40), clean(r["lead"], 120)))
w.close()
sys.stderr.write("wrote %s\n" % OUT)
