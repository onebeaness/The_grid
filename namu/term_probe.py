#!/usr/bin/env python3
"""용어별 문서 존재 여부 확인.

  제목 완전 일치 문서가 있는가
  리다이렉트로만 존재하는가. 있다면 대상은 무엇인가
  다른 제목 아래 서술돼 있는가
  문서가 없다면 본문에서 몇 건이나 언급되는가
"""
import argparse, collections, glob, gzip, json, os, re, sys, time

SNAPSHOT = "2021-03-01"
ITEMS = "/home/user/The_grid/items"

TERMS = {
 "소울라이크":      ["소울라이크", "소울 라이크", "Soulslike", "소울류"],
 "시티팝":         ["시티팝", "시티 팝", "City Pop", "시티뮤직"],
 "오픈월드":        ["오픈월드", "오픈 월드", "Open World"],
 "타임 루프":       ["타임 루프", "타임루프", "시간 루프", "루프물"],
 "하이 판타지":      ["하이 판타지", "하이판타지", "High Fantasy", "정통 판타지"],
 "메트로배니아":     ["메트로배니아", "메트로바니아", "Metroidvania"],
 "배틀로얄":        ["배틀로얄", "배틀 로얄", "배틀로열", "Battle Royale"],
 "소셜 디덕션":      ["소셜 디덕션", "소셜디덕션", "Social Deduction", "마피아 게임"],
 "로파이":         ["로파이", "로 파이", "Lo-fi", "lofi"],
 "시부야케이":       ["시부야케이", "시부야 케이", "시부야계", "Shibuya-kei"],
 "이세계물":        ["이세계물", "이세계 물", "이세계"],
 "아이돌물":        ["아이돌물", "아이돌 물"],
 "힐링물":         ["힐링물", "힐링 물", "치유계"],
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", default=os.path.join(ITEMS, "shards"))
    ap.add_argument("--out", default=ITEMS)
    a = ap.parse_args()

    # 라틴 표기 변종은 대소문자가 다르게 나타난다. 소문자 키로만 역참조한다.
    # 원래 코드는 원표기 키로 찾아서 대소문자가 다르면 조용히 버리거나
    # 리다이렉트 분기에서 첫 용어로 오귀속시켰다.
    v2c = {}
    for canon, vs in TERMS.items():
        for v in vs: v2c[v.lower()] = (canon, v)
    rx = re.compile("|".join(re.escape(v) for v in sorted(v2c, key=len, reverse=True)), re.I)

    def look(tok):
        return v2c.get(tok.lower())

    res = {c: {"exact_title": [], "redirect": [], "title_contains": [],
               "mention_docs": 0, "mention_total": 0, "section_title": [],
               "by_variant": collections.Counter(), "variant_docs": collections.Counter(),
               "top_mention": []} for c in TERMS}
    topm = {c: collections.Counter() for c in TERMS}

    files = sorted(glob.glob(os.path.join(a.shards, "*.jsonl.gz")))
    files = [f for f in files if os.path.exists(f[:-len(".jsonl.gz")] + ".done")]
    n = 0
    t0 = time.time()
    for f in files:
        for line in gzip.open(f, "rt", encoding="utf-8"):
            try: r = json.loads(line)
            except Exception: continue
            n += 1
            title = (r.get("title") or "").strip()
            hit = look(title)
            if hit:
                c, v = hit
                if r.get("is_redirect"):
                    res[c]["redirect"].append({"title": title, "variant": v,
                                               "target": r.get("redirect_target"), "exact": True})
                else:
                    res[c]["exact_title"].append({"title": title, "variant": v,
                        "len_plain": r.get("len_plain"), "categories": (r.get("categories") or [])[:4],
                        "sections": [s.get("title") for s in (r.get("sections") or [])[:8]],
                        "head": ((r.get("sections") or [{}])[0].get("text") or "")[:300]})
                continue
            if r.get("is_redirect"):
                m = rx.search(title)
                if m:
                    h = look(m.group(0))
                    if h and len(res[h[0]]["redirect"]) < 40:
                        res[h[0]]["redirect"].append({"title": title, "variant": h[1],
                                                      "target": r.get("redirect_target"), "exact": False})
                continue
            for m in rx.finditer(title):
                h = look(m.group(0))
                if h and len(res[h[0]]["title_contains"]) < 30:
                    res[h[0]]["title_contains"].append({"title": title, "variant": h[1],
                                                        "len_plain": r.get("len_plain")})
            plain = r.get("plain") or ""
            if plain:
                cnt, vcnt = collections.Counter(), collections.Counter()
                for m in rx.finditer(plain):
                    h = look(m.group(0))
                    if h: cnt[h[0]] += 1; vcnt[h] += 1
                for c, c2 in cnt.items():
                    res[c]["mention_docs"] += 1
                    res[c]["mention_total"] += c2
                    topm[c][title] = c2
                for (c, v), c2 in vcnt.items():
                    res[c]["by_variant"][v] += c2
                    res[c]["variant_docs"][v] += 1
            for s in (r.get("sections") or []):
                st = s.get("title") or ""
                for m in rx.finditer(st):
                    h = look(m.group(0))
                    if h and len(res[h[0]]["section_title"]) < 25:
                        res[h[0]]["section_title"].append({"doc": title, "section": st, "variant": h[1]})
            if n % 100000 == 0:
                sys.stderr.write("  %d문서 %.1f분\n" % (n, (time.time() - t0) / 60))
                sys.stderr.flush()
    for c in res:
        res[c]["top_mention"] = topm[c].most_common(12)
        res[c]["by_variant"] = dict(res[c]["by_variant"])
        res[c]["variant_docs"] = dict(res[c]["variant_docs"])
    json.dump({"snapshot_date": SNAPSHOT, "scanned": n, "terms": TERMS, "result": res},
              open(os.path.join(a.out, "term_probe_%s.json" % SNAPSHOT), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.stderr.write("[probe] %d문서 %.1f분\n" % (n, (time.time() - t0) / 60))

if __name__ == "__main__":
    main()
