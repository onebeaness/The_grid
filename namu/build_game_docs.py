#!/usr/bin/env python3
"""게임 문서 추출.

도메인 키워드 815종을 그대로 쓰지 않는다. 그 목록은 `게임` 이라는 낱말에
걸린 것이라 대한민국의 아시안 게임 메달리스트, 이미테이션 게임, 라이어 게임
같은 비게임 문서를 끌고 온다. 반대로 오픈 월드, 배틀로얄, 메트로배니아 같은
장르 분류는 낱말이 없어 빠진다.

대신 발매 연도 분류와 플랫폼 분류를 씨앗으로 쓴다. `2017년 게임` 에 속한
문서는 게임이다. 그 문서들이 실제로 달고 있는 분류를 전부 모으면 장르 분류가
낱말 없이도 들어온다.
"""
import glob, gzip, json, re, sys, time, collections

ITEMS = "/home/user/The_grid/items"
SNAPSHOT = "2021-03-01"

YEAR = re.compile(r"^(19|20)\d\d년 게임(/|$)")
PLATFORM = re.compile(
    r"^(PlayStation|Xbox|Nintendo|Wii|Stadia|Steam|DOS 게임|Windows 게임|Windows 10 게임"
    r"|macOS 게임|리눅스 게임|모바일 게임|아케이드 게임|플래시 게임|웹 게임|온라인 게임"
    r"|닌텐도|패밀리 컴퓨터 게임|슈퍼 패미컴 게임|메가 드라이브 게임|세가 새턴 게임"
    r"|드림캐스트 게임|게임보이|플레이스테이션 게임|PC-9800 시리즈 게임|VR 게임"
    r"|거치형 게임기|휴대용 게임기)")

def is_seed(c):
    return bool(YEAR.match(c) or PLATFORM.match(c))

def main():
    contrib = {}
    for line in gzip.open(f"{ITEMS}/contributors_{SNAPSHOT}.jsonl.gz", "rt", encoding="utf-8"):
        o = json.loads(line)
        contrib[o["title"]] = (o["n_contrib"], o["n_contrib_nobot"])
    sys.stderr.write("[game] 기여자 %d행\n" % len(contrib))

    out = gzip.open(f"{ITEMS}/game_docs_{SNAPSHOT}.jsonl.gz", "wt", encoding="utf-8")
    seedcat = collections.Counter()
    catfreq = collections.Counter()
    n = n_game = 0
    t0 = time.time()
    for f in sorted(glob.glob(f"{ITEMS}/shards/*.jsonl.gz")):
        for line in gzip.open(f, "rt", encoding="utf-8"):
            if '"is_redirect": true' in line: continue
            r = json.loads(line)
            if r.get("is_redirect"): continue
            n += 1
            cats = r.get("categories") or []
            hits = [c for c in cats if is_seed(c)]
            if not hits: continue
            n_game += 1
            for c in hits: seedcat[c] += 1
            for c in cats: catfreq[c] += 1
            cn = contrib.get(r["title"], (None, None))
            out.write(json.dumps({
                "title": r["title"], "doc_id": r["doc_id"],
                "len_plain": r.get("len_plain"), "n_contrib": cn[0], "n_contrib_nobot": cn[1],
                "n_sections": (r.get("stats") or {}).get("n_sections"),
                "categories": cats}, ensure_ascii=False) + "\n")
    out.close()
    el = (time.time() - t0) / 60
    sys.stderr.write("[game] 전체 %d문서 중 게임 %d문서 %.1f분\n" % (n, n_game, el))
    json.dump({"snapshot_date": SNAPSHOT, "docs_total": n, "docs_game": n_game,
               "seed_categories": seedcat.most_common(),
               "categories_on_game_docs": catfreq.most_common(),
               "elapsed_min": round(el, 1)},
              open(f"{ITEMS}/game_docs_meta_{SNAPSHOT}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
