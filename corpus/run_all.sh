#!/usr/bin/env bash
# 전체 파이프라인. 각 단계는 재실행 가능하다.
set -u
cd "$(dirname "$0")"
FETCH_TARGET="${FETCH_TARGET:-4000}"
log(){ echo "== $(date -u +%H:%M:%S) $*"; }

log "postprocess";            python3 postprocess.py
log "fetch (target=$FETCH_TARGET)"; python3 fetch.py --target "$FETCH_TARGET"
log "extract";                python3 index.py extract
log "refs";                   python3 index.py refs

for R in 1 2; do
  log "snowball round $R";    python3 snowball.py --round "$R" --min-count 2
  log "postprocess";          python3 postprocess.py
  log "fetch round $R";       python3 fetch.py --target "$FETCH_TARGET"
  log "extract";              python3 index.py extract
  log "refs";                 python3 index.py refs
done

log "embed";                  python3 index.py embed
log "snapshot";               gzip -9 -c records.jsonl > records.jsonl.gz
log "report";                 python3 report.py | tee report.txt
log "완료"
