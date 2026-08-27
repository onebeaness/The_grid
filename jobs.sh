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
report "나무위키 파싱"  "parse_dump.py"          namu/logs/parse.log
report "논문 수집"      "collect.py --round 0"   corpus/logs/collect_r0.log
