#!/usr/bin/env python3
"""확인된 장르 문서에서 하위 문서 수 신호가 무엇을 잃는지 잰다.

정밀도 채점은 판정자 주관이 들어간다. 재현 손실은 목록이 고정되면
계산만 남는다. 표본에서 장르로 채점한 문서와 보정에 쓴 문서를 모두 넣는다.
"""
import json, sys
sys.path.insert(0, "/home/user/The_grid/namu")
from genre_detect import load_cat_index, sub_count

CONFIRMED = """
BL 소설|교향시|그라인드코어|기업물|능력자 배틀|뱀 게임|소드 앤 소서리|슈팅 게임|시리어스물
야구 만화|연애 어드벤처 게임|이고깽|포스트 아포칼립스|디스코|보사노바|시리어스 게임|재즈 록
학원물/한국|MMORPG|io게임|느와르|드라마|리듬 게임|사극 로맨스|요리물|뮤지컬|비주얼 노벨
컨템퍼러리 R&B|틴 팝|퓨전 판타지|희곡|방탈출|중금속음악|슈게이징|로그라이크|다크 판타지
사이버펑크|성장물|스팀펑크|좀비 아포칼립스|메트로배니아|슬래셔|대전 액션 게임|데스코어
샹송|서부극|K-POP|MC물|기생물|2차 창작|이탈로 디스코|칩튠
""".replace("\n", "|").split("|")
CONFIRMED = [t.strip() for t in CONFIRMED if t.strip()]

idx = load_cat_index("/home/user/The_grid/items/genres.jsonl")
rows = [(t,) + sub_count(t, idx) for t in CONFIRMED]
rows.sort(key=lambda r: r[1])
print("확인된 장르 문서 %d편. 채점 주체 Claude." % len(rows))
for g in (1, 3, 5, 10, 20):
    keep = sum(1 for r in rows if r[1] >= g)
    print("  임계 %2d  잔존 %2d/%d  (%.0f%%)  손실 %d편" % (g, keep, len(rows),
          100.0 * keep / len(rows), len(rows) - keep))
print("\n하위 문서 수 0인 장르 문서")
print("  " + ", ".join(r[0] for r in rows if r[1] == 0))
