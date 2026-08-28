#!/usr/bin/env python3
"""문서별 기여자 수. 원본 덤프에서 title 과 contributors 두 열만 읽는다.

contributors 는 쉼표로 이어붙인 문자열. 사용자명과 IP 가 섞여 있고
namubot 같은 봇도 들어 있다. 원시 수와 봇 제외 수를 함께 남긴다.
원본은 읽기 전용으로만 연다.
"""
import gzip, json, sys, time
import pyarrow.parquet as pq

SRC = ("/home/user/hf-cache/hub/datasets--heegyu--namuwiki/snapshots/"
       "5631a9bd17a096bab2cd02ea23adbf2327db0d91/namuwiki_20210301.parquet")
OUT = "/home/user/The_grid/items/contributors_2021-03-01.jsonl.gz"
BOTS = {"namubot", "관리자"}

f = pq.ParquetFile(SRC)
w = gzip.open(OUT, "wt", encoding="utf-8")
n = 0
t0 = time.time()
for b in f.iter_batches(batch_size=20000, columns=["title", "contributors"]):
    for t, c in zip(b.column("title").to_pylist(), b.column("contributors").to_pylist()):
        parts = [x for x in (c or "").split(",") if x]
        nb = sum(1 for x in parts if x not in BOTS and not x.startswith("r:namubot"))
        w.write(json.dumps({"title": t, "n_contrib": len(parts), "n_contrib_nobot": nb},
                           ensure_ascii=False) + "\n")
        n += 1
    if n % 200000 < 20000:
        sys.stderr.write("  %d행 %.1f분\n" % (n, (time.time() - t0) / 60)); sys.stderr.flush()
w.close()
sys.stderr.write("[contrib] %d행 %.1f분\n" % (n, (time.time() - t0) / 60))
