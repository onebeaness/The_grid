#!/usr/bin/env python3
"""게임 문서에 달린 분류를 장르와 비장르로 가른다.

배제 규칙을 먼저 적용하고 남은 것을 장르 후보로 둔다.
규칙은 배제 사유별로 이름을 붙여 어느 규칙에 걸렸는지 보고할 수 있게 한다.
"""
import json, re, sys, collections

ITEMS = "/home/user/The_grid/items"
SNAPSHOT = "2021-03-01"

# 배제 규칙. 순서대로 적용하고 첫 일치를 사유로 기록한다.
EXCLUDE = [
 ("연도",       re.compile(r"^(19|20)\d\d년")),
 ("플랫폼",     re.compile(r"^(PlayStation|Xbox|Nintendo|Wii|Stadia|Steam|EA Play|Origin"
                           r"|Windows 게임|Windows 10 게임|macOS 게임|리눅스 게임|DOS 게임"
                           r"|모바일 게임|아케이드 게임|플래시 게임|웹 게임|온라인 게임|VR 게임"
                           r"|닌텐도|패밀리 컴퓨터|슈퍼 패미컴|메가 드라이브|세가 새턴|드림캐스트"
                           r"|게임보이|플레이스테이션 게임|PC-9800|거치형 게임기|휴대용 게임기"
                           r"|Google Play|App Store|Epic Games)")),
 ("플랫폼",     re.compile(r"(하위 호환|Enhanced|Game Pass|앞서 해보기|클라우드 게임)")),
 ("국가",       re.compile(r"^(한국|일본|미국|중국|영국|프랑스|폴란드|캐나다|대만|독일|러시아"
                           r"|스웨덴|호주|우크라이나|체코|핀란드|스페인|이탈리아|브라질|인도)\s*게임$")),
 ("제작·유통사", re.compile(r"(제작사|퍼블리셔|유통 게임|의 게임$|게임 회사|게임 스튜디오"
                           r"|^(세가|닌텐도|카카오게임|게임빌|넥슨|엔씨소프트|넷마블|스마일게이트)$)")),
 ("시리즈·개별작", re.compile(r"(시리즈|/|\(게임\)|\(비디오 게임\)|\(만화\)|\(애니메이션\)"
                           r"|\(소설\)|\(드라마\)|\(영화\))")),
 ("위키관리·메타", re.compile(r"(토막글|나무위키|프로젝트|공개 전 정보|서비스 종료|개발 취소"
                           r"|사건사고|논란|문서$|동음이의어|일람|목록$|분류$)")),
 ("인물",       re.compile(r"(개발자|작곡가|시나리오 라이터|원화가|관련 인물|성우|디렉터"
                           r"|프로듀서|캐릭터$|등장인물|유튜버|리뷰어|BJ)")),
 ("부속요소",   re.compile(r"(게임 용어|게임 음악|게임 내 정보|게임 공략|게임 설정|게임 스토리"
                           r"|게임 시스템|게임 직업|게임 점수|게임 플레이|게임 콘텐츠|게임 브랜드"
                           r"|게임 사이트|게임 방송|게임 행사|게임 잡지|게임잡지|게임 커뮤니티"
                           r"|게임 개발 도구|용어$|아이템|무기|스킬|퀘스트|OST|사운드트랙)")),
 ("제작·유통형태", re.compile(r"^(인디 게임|동인 게임|양산형 게임|프리웨어|오픈 소스|무료 게임"
                           r"|부분 유료화|패키지 게임|리메이크|리마스터|이식작)$")),
 ("e스포츠조직", re.compile(r"(e스포츠 팀|e스포츠 대회|프로게임단|리그$)")),
 ("색인",       re.compile(r"(라틴 문자$|/[ㄱ-ㅎ]$|^[ㄱ-ㅎ]$)")),
 ("원작·매체전환", re.compile(r"(원작|게임화|미디어 믹스|실사화)")),
 ("비게임",     re.compile(r"(메달리스트|올림픽|아시안 게임|월드컵|선수$|구단|방송사|기업"
                           r"|드라마|영화$|애니메이션$|만화$|소설$|웹툰)")),
]

def why_exclude(c):
    for name, rx in EXCLUDE:
        if rx.search(c): return name
    return None

def main():
    d = json.load(open(f"{ITEMS}/game_docs_meta_{SNAPSHOT}.json", encoding="utf-8"))
    cats = d["categories_on_game_docs"]
    minn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    keep, drop = [], collections.defaultdict(list)
    for c, n in cats:
        if n < minn: continue
        w = why_exclude(c)
        if w: drop[w].append((c, n))
        else: keep.append((c, n))
    print("분류 %d종 중 count>=%d 인 %d종을 대상으로 함"
          % (len(cats), minn, sum(1 for _, n in cats if n >= minn)))
    print("장르 후보 %d종, 배제 %d종\n" % (len(keep), sum(len(v) for v in drop.values())))
    print("[배제 사유별]")
    for k in sorted(drop, key=lambda k: -len(drop[k])):
        print("  %-12s %4d종   예) %s" % (k, len(drop[k]),
              ", ".join(c for c, _ in drop[k][:5])))
    print("\n[장르 후보 %d종]" % len(keep))
    for c, n in keep: print("  %5d %s" % (n, c))
    json.dump({"snapshot_date": SNAPSHOT, "min_count": minn,
               "genre_candidates": keep,
               "excluded": {k: v for k, v in drop.items()}},
              open(f"{ITEMS}/game_cat_classified_{SNAPSHOT}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
