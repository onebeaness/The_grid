#!/usr/bin/env bash
# 실행 중인 장시간 작업 확인.
# pgrep -f 와 pkill -f 는 자기 명령줄을 매칭해 오탐한다. 두 번 겪음.
# pgrep -x python3 로 실행 파일명을 맞춘 뒤 /proc/<pid>/cmdline 을 확인한다.
cd "$(dirname "$0")"
pids_of() {
  local pat="$1" p
  for p in $(pgrep -x python3 2>/dev/null); do
    [ -r "/proc/$p/cmdline" ] || continue
    tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q -- "$pat" && echo "$p"
  done
}
state() {
  local name="$1" pat="$2" pids
  pids=$(pids_of "$pat" | tr '\n' ' ')
  if [ -n "$pids" ]; then
    printf "%-16s 실행 중  pid=%s  경과 %s\n" "$name" "${pids% }" \
      "$(ps -o etime= -p ${pids%% *} 2>/dev/null | tr -d ' ')"
  else
    printf "%-16s 종료\n" "$name"
  fi
}
state "나무위키 파싱"  "parse_dump.py"
d=$(ls items/shards/*.done 2>/dev/null | wc -l)
g=$(ls items/shards/*.jsonl.gz 2>/dev/null | wc -l)
printf "                 샤드 완료 %s/9  생성 %s  누적 %s  디스크 여유 %s\n" \
  "$d" "$g" "$(du -sh items/shards 2>/dev/null | cut -f1)" "$(df -h /home/user | tail -1 | awk '{print $4}')"
state "논문 수집"      "collect.py"
[ -f corpus/logs/collect_r0.log ] && printf "                 %s\n" "$(grep -E '^  [0-9]+/[0-9]+' corpus/logs/collect_r0.log | tail -1)"
state "분류 집계"      "build_genres.py"
state "본문 판정"      "genre_detect.py"
state "원문 확보"      "fetch.py"
