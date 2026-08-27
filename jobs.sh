#!/usr/bin/env bash
# 실행 중인 장시간 작업 확인.
# pgrep -f 는 대기 루프 셸의 명령줄까지 매칭해 오탐을 낸다. 82분을 날린 원인.
# pgrep -x python3 로 실행 파일명을 정확히 맞춘 뒤 cmdline 을 확인한다.
pids_of() {
  local pat="$1" p
  for p in $(pgrep -x python3 2>/dev/null); do
    [ -r "/proc/$p/cmdline" ] || continue
    tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q -- "$pat" && echo "$p"
  done
}
report() {
  local name="$1" pat="$2" log="$3" pids
  pids=$(pids_of "$pat" | tr '\n' ' ')
  if [ -n "$pids" ]; then
    printf "%-16s 실행 중  pid=%s  경과 %s\n" "$name" "${pids% }" \
      "$(ps -o etime= -p ${pids%% *} 2>/dev/null | tr -d ' ')"
  else
    printf "%-16s 종료\n" "$name"
  fi
  [ -f "$log" ] && sed -n '$p' "$log" | sed 's/^/                 /'
}
report "나무위키 파싱"  "parse_dump.py"          /tmp/claude-0/-home-user-The-grid/fde8ecf8-47ea-5e6d-b900-666626e4e91d/tasks/bebisny8j.output
d=$(ls /home/user/The_grid/items/shards/*.done 2>/dev/null | wc -l)
g=$(ls /home/user/The_grid/items/shards/*.jsonl.gz 2>/dev/null | wc -l)
printf "                 샤드 완료 %s/9  (생성 %s)  누적 %s\n" "$d" "$g" \
  "$(du -sh /home/user/The_grid/items/shards 2>/dev/null | cut -f1)"
report "논문 수집"      "collect.py --round 0"   corpus/logs/collect_r0.log
