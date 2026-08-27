#!/usr/bin/env python3
"""자연어 질의 -> 근거 청크와 출처.

  python3 query.py "왜 실제 유사성보다 지각된 유사성이 매력을 예측하는가" -k 8
  python3 query.py "cold start overlap ratio" --family cross-domain-rec --min-year 2020
"""
import json, os, sys, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
IDXDIR = os.path.join(HERE, "index")

def load():
    import numpy as np
    emb = np.load(os.path.join(IDXDIR, "emb.npy"))
    chunks = [json.loads(l) for l in open(os.path.join(IDXDIR, "chunks.jsonl"), encoding="utf-8")]
    meta = json.load(open(os.path.join(IDXDIR, "meta.json"), encoding="utf-8"))
    return emb, chunks, meta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=8, help="반환할 청크 수")
    ap.add_argument("--per-paper", type=int, default=2, help="논문당 최대 청크")
    ap.add_argument("--family", default="", help="계열 필터 (쉼표 구분)")
    ap.add_argument("--min-year", type=int, default=0)
    ap.add_argument("--section", default="", help="섹션 이름 부분일치 필터")
    ap.add_argument("--chars", type=int, default=700, help="청크 출력 길이")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    import numpy as np
    from sentence_transformers import SentenceTransformer
    emb, chunks, meta = load()
    model = SentenceTransformer(meta["model"], device="cpu")
    q = model.encode([a.question], convert_to_numpy=True, normalize_embeddings=True)[0]
    sims = emb @ q

    fams = set(a.family.split(",")) if a.family else None
    order = np.argsort(-sims)
    seen = {}
    hits = []
    for i in order:
        c = chunks[i]
        if fams and not (set(c.get("families") or []) & fams): continue
        if a.min_year and (c.get("year") or 0) < a.min_year: continue
        if a.section and a.section.lower() not in (c.get("section") or "").lower(): continue
        if seen.get(c["key"], 0) >= a.per_paper: continue
        seen[c["key"]] = seen.get(c["key"], 0) + 1
        hits.append((float(sims[i]), c))
        if len(hits) >= a.k: break

    if a.json:
        print(json.dumps([{"score": s, **{k: v for k, v in c.items()}} for s, c in hits],
                         ensure_ascii=False, indent=1)); return

    print("질의: %s" % a.question)
    print("인덱스: 청크 %d개 / 문서 %d개 / 모델 %s\n" % (meta["n_chunks"], meta["n_docs"], meta["model"]))
    for n, (s, c) in enumerate(hits, 1):
        src = "전문" if c.get("source_kind") == "pdf" else "초록"
        print("[%d] score=%.3f  %s" % (n, s, c.get("title") or "(제목 없음)"))
        print("    %s | %s | %s | %s | 섹션 %s p.%s | %s"
              % (c.get("year") or "-", (c.get("venue") or "-")[:44],
                 c.get("doi") or "-", ",".join(c.get("families") or []),
                 (c.get("section") or "-")[:28], c.get("page"), src))
        t = c["text"].replace("\n", " ")
        print("    " + (t[:a.chars] + ("..." if len(t) > a.chars else "")))
        print()

if __name__ == "__main__":
    main()
