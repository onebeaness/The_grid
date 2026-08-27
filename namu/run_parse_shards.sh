#!/usr/bin/env bash
# 샤드 단위 파싱. 완료된 샤드는 남으므로 중단되어도 이어서 할 수 있다.
set -u
cd "$(dirname "$0")"
P=$(ls /home/user/hf-cache/hub/datasets--heegyu--namuwiki/snapshots/*/namuwiki_20210301.parquet)
OUT=/home/user/The_grid/items/shards
TOTAL=867024
SIZE=${SHARD_SIZE:-100000}
W=${WORKERS:-4}
for ((s=0; s<TOTAL; s+=SIZE)); do
  f="$OUT/shard_$(printf %07d $s).jsonl.gz"
  d="$OUT/shard_$(printf %07d $s).done"
  if [ -f "$d" ]; then echo "skip  $s (완료됨)"; continue; fi
  echo "=== shard $s ($(date -u +%H:%M:%S))"
  python3 parse_dump.py --parquet "$P" --workers "$W" \
    --start-row "$s" --max-rows "$SIZE" --progress 25000 --out "$f" || { echo "FAIL $s"; exit 1; }
  touch "$d"
done
echo "ALL_SHARDS_DONE"
