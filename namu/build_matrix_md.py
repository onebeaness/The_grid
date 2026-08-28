#!/usr/bin/env python3
"""장르 행렬 보고서. 수치와 목록만. 해석 없음."""
import json

ITEMS = "/home/user/The_grid/items"
d = json.load(open(f"{ITEMS}/genre_matrix.json", encoding="utf-8"))
top = d["top_genres"]
cells = d["cells"]
MIN = d["thresholds"]["min_cell"]

def cell(a, b):
    if a == b: return None
    k = "%s|%s" % tuple(sorted((a, b)))
    return cells.get(k)

def grid(w, field, fmt, empty="·", scarce="*"):
    w.write("| # | 장르 | " + " | ".join("%02d" % (i + 1) for i in range(len(top))) + " |\n")
    w.write("|---|---|" + "---|" * len(top) + "\n")
    for i, g in enumerate(top):
        row = []
        for j, h in enumerate(top):
            if i == j: row.append("—"); continue
            c = cell(g, h)
            if not c: row.append(empty); continue
            if c["n"] < MIN:
                row.append(scarce if field != "n" else "%d%s" % (c["n"], scarce)); continue
            v = c[field]
            row.append(fmt % v if v is not None else empty)
        w.write("| %02d | %s | %s |\n" % (i + 1, g, " | ".join(row)))

w = open(f"{ITEMS}/genre_matrix.md", "w", encoding="utf-8")
w.write("# 장르 동시 출현 행렬. 게임 도메인\n\n")
w.write("스냅샷 %s. 나무위키 덤프 기반.\n\n" % d["snapshot_date"])

w.write("## 대리 지표 명시\n\n")
w.write("- 셀 값 중 평균 본문 길이와 평균 기여자 수는 **인기도가 아니라 관심의 대리 지표**\n")
w.write("- 나무위키에는 판매량도 리뷰 수도 없음. 이 둘이 확보 가능한 대리값\n")
w.write("- 오래된 게임일수록 문서가 누적되므로 **시간 편향**이 있음. 보정하지 않음\n")
w.write("- 기여자 수는 `namubot` 과 `관리자` 를 제외한 값\n")
w.write("- 스냅샷이 2021-03-01 이므로 그 이후 형성된 조합은 원리적으로 없음\n\n")

w.write("## 1. 규모\n\n| 항목 | 값 |\n|---|---|\n")
for k, v in (("게임 문서", d["docs_game"]), ("장르 분류 1개 이상", d["docs_with_genre"]),
             ("장르 분류 2개 이상", d["docs_multi_genre"]),
             ("장르 어휘", d["genre_vocab"]), ("실제 등장한 장르", d["genre_used"]),
             ("장르 조합", d["pairs_total"]),
             ("조합 중 %d건 이상" % MIN, d["pairs_ge3"])):
    w.write("| %s | %s |\n" % (k, format(v, ",")))
b, bm = d["baseline_with_genre"], d["baseline_multi_genre"]
w.write("\n### 기준선\n\n| 모집단 | 문서 수 | 평균 길이 | 중앙 길이 | 평균 기여자 | 중앙 기여자 |\n")
w.write("|---|---|---|---|---|---|\n")
w.write("| 장르 있는 문서 | %s | %s | %s | %s | %s |\n" % (
    format(b["n"], ","), format(b["mean_len"], ","), format(b["median_len"], ","),
    b["mean_contrib"], b["median_contrib"]))
w.write("| 복수 장르 문서 | %s | %s | %s | %s | %s |\n" % (
    format(bm["n"], ","), format(bm["mean_len"], ","), format(bm["median_len"], ","),
    bm["mean_contrib"], bm["median_contrib"]))

w.write("\n## 2. 상위 25 장르\n\n")
w.write("| # | 장르 | 갈래 | 문서 수 | 평균 길이 | 평균 기여자 |\n|---|---|---|---|---|---|\n")
for i, g in enumerate(top):
    dg = d["diagonal"][g]
    w.write("| %02d | %s | %s | %d | %s | %s |\n" % (
        i + 1, g, d["genre_kind"].get(g) or "", dg["n"],
        format(dg["mean_len"], ","), dg["mean_contrib"]))

w.write("\n## 3. 격자. 조합 문서 수\n\n")
w.write("`·` 은 조합 0건. `*` 표시는 %d건 미만으로 표본 부족.\n\n" % MIN)
grid(w, "n", "%d")

w.write("\n## 4. 격자. 평균 본문 길이\n\n")
w.write("표본 부족 셀(%d건 미만)은 `*`. 조합 0건은 `·`.\n\n" % MIN)
grid(w, "mean_len", "%d")

w.write("\n## 5. 격자. 평균 기여자 수\n\n")
w.write("봇 제외. 표본 부족 셀은 `*`. 조합 0건은 `·`.\n\n")
grid(w, "mean_contrib", "%.0f")

th = d["thresholds"]
w.write("\n## 6. 조합이 많은데 평균 길이가 짧은 셀\n\n")
w.write("조건: 문서 수 %d건 이상(상위 25%%)이고 평균 길이 %s자 이하(하위 25%%).\n\n"
        % (th["n_p75"], format(th["len_p25"], ",")))
w.write("| 조합 | 문서 수 | 평균 길이 | 평균 기여자 |\n|---|---|---|---|\n")
for r in d["many_short"]:
    w.write("| %s | %d | %s | %s |\n" % (" × ".join(r["pair"]), r["n"],
            format(r["mean_len"], ","), r["mean_contrib"]))

w.write("\n## 7. 조합이 적은데 평균 길이가 긴 셀\n\n")
w.write("조건: 문서 수 %d건 이하(하위 25%%, 단 %d건 이상)이고 평균 길이 %s자 이상(상위 25%%).\n\n"
        % (th["n_p25"], MIN, format(th["len_p75"], ",")))
w.write("| 조합 | 문서 수 | 평균 길이 | 평균 기여자 |\n|---|---|---|---|\n")
for r in d["few_long"]:
    w.write("| %s | %d | %s | %s |\n" % (" × ".join(r["pair"]), r["n"],
            format(r["mean_len"], ","), r["mean_contrib"]))

emp = d["empty_cells_top25"]
w.write("\n## 8. 완전히 빈 셀\n\n")
w.write("상위 25 장르의 조합 %d개 중 %d개가 0건.\n\n" % (25 * 24 // 2, len(emp)))
w.write("**이 공백이 실제 공백인지 스냅샷 공백인지 구분되지 않음.** 2021-03-01 이후\n")
w.write("형성된 조합은 덤프에 없음. 또한 나무위키 편집자가 그 조합에 분류를 달지\n")
w.write("않았을 뿐일 수도 있음. 분류 부여 여부와 작품 존재 여부는 별개.\n\n")
w.write("| 조합 |\n|---|\n")
for a, bb in emp:
    w.write("| %s × %s |\n" % (a, bb))
w.close()
print("wrote genre_matrix.md")
