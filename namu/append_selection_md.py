#!/usr/bin/env python3
"""장르 분류 선정 근거를 행렬 보고서에 덧붙인다."""
import json, re, sys, collections
sys.path.insert(0, "/home/user/The_grid/namu")
from game_genre_list import GENRES, KIND
from classify_game_cats import why_exclude

ITEMS = "/home/user/The_grid/items"
meta = json.load(open(f"{ITEMS}/game_docs_meta_2021-03-01.json", encoding="utf-8"))
cats = meta["categories_on_game_docs"]
MIN = 3

used, dropped_rule, dropped_manual = [], collections.defaultdict(list), []
SUBJ = re.compile(r"(를|을|으로) (소재로|배경으로) 한 작품$|를 배경으로 한 작품$")
subj = []
for c, n in cats:
    if n < MIN: continue
    if c in GENRES: used.append((c, n)); continue
    if SUBJ.search(c): subj.append((c, n)); continue
    w = why_exclude(c)
    if w: dropped_rule[w].append((c, n))
    else: dropped_manual.append((c, n))

txt = []
A = txt.append
A("\n## 부록. 장르 분류 선정\n")
A("게임 문서 %s건에 달린 분류 %s종 중 %s건 이상 등장한 %d종을 대상으로 함.\n"
  % (format(meta["docs_game"], ","), format(len(cats), ","), MIN,
     sum(1 for _, n in cats if n >= MIN)))
A("### 씨앗 선정\n")
A("게임 도메인 키워드로 걸린 분류 815종을 씨앗으로 쓰지 않음. 낱말 `게임` 에")
A("걸린 목록이라 양방향으로 틀림.\n")
A("- 비게임이 들어옴. 대한민국의 아시안 게임 메달리스트 505, 라이어 게임 80,")
A("  이미테이션 게임 42, 소사이어티 게임 38, 환상게임 29")
A("- 장르가 빠짐. 오픈 월드, 배틀로얄, ARPG, 대전 액션, 비주얼 노벨, TPS,")
A("  전략 시뮬레이션, SRPG, 건설 경영 시뮬레이션, 종스크롤 슈팅, RTS 가 없었음\n")
A("대신 발매 연도 분류와 플랫폼 분류 178종을 씨앗으로 씀. `2017년 게임` 에 속한")
A("문서는 게임임. 그 문서가 달고 있는 분류를 전부 모아 대상으로 삼음.\n")
A("### 포함 기준\n")
A("작품이 무엇을 하는 것인지를 가리키는 분류. 조작 방식, 진행 구조, 세계관,")
A("정서, 서사 형식, 대상 지향.\n")
A("### 제외 기준\n")
A("플랫폼, 발매 연도, 제작사, 유통사, 시리즈, 개별 작품, IP, 위키 관리, 인물,")
A("부속 요소, 제작·유통 형태, 색인, 소재.\n")
A("### 확정 장르 %d종\n" % len(GENRES))
A("| 갈래 | 종수 | 실제 등장 |\n|---|---|---|")
kc = collections.Counter(KIND.values())
uc = collections.Counter(KIND.get(c) for c, _ in used)
for k in ("메커닉", "세계관·정서", "서사 형식", "대상·지향"):
    A("| %s | %d | %d |" % (k, kc[k], uc[k]))
A("")
A("어휘 %d종 중 %d종이 게임 문서에 실제로 등장. 미등장 5종은" % (len(GENRES), len(used)))
A("MOBA, 메트로배니아, 미소녀 게임, 미니어처 게임, 추상전략게임.")
A("메트로배니아는 같은 이름의 분류가 없고 해당 문서가 `액션 게임`, `ARPG` 를 닮.\n")
A("### 규칙으로 제외한 것 %d종\n" % sum(len(v) for v in dropped_rule.values()))
A("| 사유 | 종수 | 예 |\n|---|---|---|")
for k in sorted(dropped_rule, key=lambda k: -len(dropped_rule[k])):
    ex = ", ".join(c for c, _ in sorted(dropped_rule[k], key=lambda x: -x[1])[:6])
    A("| %s | %d | %s |" % (k, len(dropped_rule[k]), ex))
A("")
A("### 소재 분류 %d종. 별도 축으로 분리\n" % len(subj))
A("`~를 소재로 한 작품`, `~를 배경으로 한 작품` 은 제재이지 장르가 아니라고")
A("보고 이번 행렬에서 제외. 매체 무관 분류이며 별도 축으로 쓸 수 있으므로 목록만 남김.\n")
A("상위 20종. " + ", ".join("%s %d" % (c, n) for c, n in sorted(subj, key=lambda x: -x[1])[:20]) + "\n")
A("### 수동으로 제외한 것 %d종\n" % len(dropped_manual))
A("규칙에 걸리지 않았으나 장르가 아닌 것. 제작사, 개별 IP, 하드웨어가 대부분.\n")
A("| 분류 | 문서 수 |\n|---|---|")
for c, n in sorted(dropped_manual, key=lambda x: -x[1]):
    A("| %s | %d |" % (c, n))
A("")

with open(f"{ITEMS}/genre_matrix.md", "a", encoding="utf-8") as f:
    f.write("\n".join(txt))
print("appended. 장르 %d, 규칙제외 %d, 소재 %d, 수동제외 %d"
      % (len(used), sum(len(v) for v in dropped_rule.values()), len(subj), len(dropped_manual)))
