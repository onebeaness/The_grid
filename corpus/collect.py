"""계열별 질의어를 소스에 던져 레코드를 모으고 병합한다.
DOI와 정규화 제목으로 중복을 합치되, 제목 유사도로 재확인한다.
중단 후 재실행하면 done.jsonl에 남은 (query, source) 쌍은 건너뛴다."""
import json, os, sys, time, argparse
import sources as S

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDS = os.path.join(HERE, "records.jsonl")
DONE = os.path.join(HERE, "done.jsonl")
STATELOG = os.path.join(HERE, "collect_state.json")

TITLE_SIM_MERGE = 0.90   # 정규화 제목이 같아도 원 제목 유사도가 이 아래면 병합하지 않는다
YEAR_TOL = 2

class Store:
    def __init__(self):
        self.by_key = {}
        self.doi_idx = {}
        self.title_idx = {}
        self._load()

    def _load(self):
        if not os.path.exists(RECORDS): return
        for line in open(RECORDS, encoding="utf-8"):
            line = line.strip()
            if not line: continue
            try: r = json.loads(line)
            except Exception: continue
            self._register(r)
        S.log("[store] 기존 레코드 %d건 로드" % len(self.by_key))

    def _register(self, r):
        k = r["key"]
        self.by_key[k] = r
        if r.get("doi"): self.doi_idx[r["doi"]] = k
        nt = r.get("norm_title")
        if nt: self.title_idx.setdefault(nt, []).append(k)

    def _newkey(self, r):
        if r.get("doi"): return "doi:" + r["doi"]
        if r.get("arxiv_id"): return "arxiv:" + r["arxiv_id"].split("v")[0]
        if r.get("pmid"): return "pmid:" + r["pmid"]
        if r.get("s2_id"): return "s2:" + r["s2_id"]
        return "t:" + (r.get("norm_title") or "")[:120]

    def _find(self, r):
        if r.get("doi") and r["doi"] in self.doi_idx:
            return self.doi_idx[r["doi"]]
        nt = r.get("norm_title")
        if not nt: return None
        for k in self.title_idx.get(nt, []):
            e = self.by_key[k]
            # 정규화 제목이 같아도 원 제목 유사도로 재확인
            if S.title_sim(e.get("title") or "", r.get("title") or "") < TITLE_SIM_MERGE:
                continue
            ya, yb = e.get("year"), r.get("year")
            if ya and yb and abs(ya - yb) > YEAR_TOL:
                continue
            # DOI가 둘 다 있는데 다르면 다른 논문이다
            if e.get("doi") and r.get("doi") and e["doi"] != r["doi"]:
                continue
            return k
        return None

    def add(self, r, family, query, rnd):
        r["families"] = sorted(set((r.get("families") or []) + [family]))
        r["queries"] = sorted(set((r.get("queries") or []) + [query]))
        r["round"] = rnd
        k = self._find(r)
        if k is None:
            r["key"] = self._newkey(r)
            while r["key"] in self.by_key and self.by_key[r["key"]].get("norm_title") != r.get("norm_title"):
                r["key"] += "_x"
            self._register(r)
            return "new"
        e = self.by_key[k]
        merge(e, r)
        return "merged"

    def flush(self):
        tmp = RECORDS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in self.by_key.values():
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, RECORDS)

def merge(e, r):
    for f in ("doi", "arxiv_id", "pmid", "s2_id", "openalex_id", "dblp_key",
              "venue", "year", "oa_url", "title"):
        if not e.get(f) and r.get(f): e[f] = r[f]
    if r.get("authors") and len(r["authors"]) > len(e.get("authors") or []):
        e["authors"] = r["authors"]
    if r.get("citations") is not None:
        e["citations"] = max(e.get("citations") or 0, r["citations"])
    if r.get("abstract") and len(r["abstract"]) > len(e.get("abstract") or ""):
        e["abstract"] = r["abstract"]; e["abstract_source"] = r.get("abstract_source")
    for f in ("sources", "families", "queries"):
        e[f] = sorted(set((e.get(f) or []) + (r.get(f) or [])))
    e["round"] = min(e.get("round", 99), r.get("round", 99))
    if e.get("doi"): e["doi"] = e["doi"].lower()
    e["norm_title"] = S.norm_title(e.get("title"))

def load_done():
    d = set()
    if os.path.exists(DONE):
        for line in open(DONE, encoding="utf-8"):
            try: o = json.loads(line)
            except Exception: continue
            d.add((o["family"], o["query"], o["source"]))
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=0)
    ap.add_argument("--per-query", type=int, default=200)
    ap.add_argument("--families", default="")
    ap.add_argument("--queries-file", default="")   # 눈덩이용 추가 질의어
    args = ap.parse_args()

    kw = json.load(open(os.path.join(HERE, "keywords.json"), encoding="utf-8"))
    fams = kw["families"]
    if args.families:
        want = set(args.families.split(","))
        fams = [f for f in fams if f["id"] in want]

    if args.queries_file:
        extra = json.load(open(args.queries_file, encoding="utf-8"))
        fams = extra["families"]

    store = Store()
    done = load_done()
    donef = open(DONE, "a", encoding="utf-8")
    caps = []
    t0 = time.time()
    n_new = n_mrg = n_rej = 0

    tasks = []
    for fam in fams:
        qs = fam["core"] + fam["expanded"]
        for q in qs:
            for src in fam["sources"]:
                if (fam["id"], q, src) in done: continue
                tasks.append((fam["id"], q, src))
    # 빠르고 안정적인 소스를 먼저, 느린 S2를 마지막으로
    PRIO = {"crossref": 0, "arxiv": 1, "pubmed": 2, "openproceedings": 3,
            "dblp": 4, "openalex": 5, "semanticscholar": 6}
    tasks.sort(key=lambda t: (PRIO.get(t[2], 9), t[0], t[1]))
    S.log("[collect] 라운드 %d, 남은 (질의,소스) %d개" % (args.round, len(tasks)))

    for i, (fid, q, src) in enumerate(tasks):
        st = S.STATE.get(src)
        if st and not st["ok"]:
            donef.write(json.dumps({"family": fid, "query": q, "source": src,
                                    "skipped": st["reason"]}, ensure_ascii=False) + "\n")
            continue
        fn = S.SEARCHERS.get(src)
        if not fn: continue
        try:
            got = fn(q, limit=args.per_query)
        except Exception as ex:
            S.log("  [err] %s/%s: %s" % (src, q[:40], str(ex)[:80])); got = []
        if len(got) >= args.per_query:
            caps.append({"family": fid, "query": q, "source": src, "capped_at": args.per_query})
        a = b = rej = 0
        for r in got:
            if not r.get("title"): continue
            if not S.relevant(q, r):
                rej += 1; continue
            if store.add(r, fid, q, args.round) == "new": a += 1
            else: b += 1
        n_new += a; n_mrg += b; n_rej += rej
        donef.write(json.dumps({"family": fid, "query": q, "source": src,
                                "got": len(got), "new": a, "rejected": rej},
                               ensure_ascii=False) + "\n")
        donef.flush()
        if (i + 1) % 25 == 0:
            store.flush()
            S.log("  %d/%d  총 %d건 (신규 %d, 병합 %d, 무관 제외 %d)  %.0f분"
                  % (i + 1, len(tasks), len(store.by_key), n_new, n_mrg, n_rej,
                     (time.time() - t0) / 60))

    store.flush()
    donef.close()
    json.dump({"round": args.round, "state": S.STATE, "capped": caps,
               "total_records": len(store.by_key), "rejected_irrelevant": n_rej,
               "elapsed_min": round((time.time() - t0) / 60, 1)},
              open(STATELOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    S.log("[collect] 완료. 총 %d건. 상한 도달 질의 %d개. %.0f분"
          % (len(store.by_key), len(caps), (time.time() - t0) / 60))

if __name__ == "__main__":
    main()
