# 아이템 코퍼스

나무위키 덤프 기반 아이템 코퍼스. 논문 코퍼스(`corpus/`)와 분리. CLAUDE.md 49행.

## 산출물

- `all.jsonl`: 문서당 JSON 한 줄
- `genres.jsonl`: 도메인별 분류 탐색 결과
- `proposals.md`: 미포함 영역 제안. 자동 편입 없음
- `rating_map.json`: 연령 등급 원본 표기와 매핑
- `parser_candidates.json`: 파서 후보와 커밋 해시
- `failures/`: 파싱 실패 문서 원문

## 스냅샷

모든 산출물에 `snapshot_date` 포함. CLAUDE.md 61행.

## 원본 취급

덤프는 `rb`로만 개방. rename, chmod, 삭제, 덮어쓰기 없음. CLAUDE.md 63행.
작업 전후 크기, mtime, 체크섬 대조로 무결성 증명.

## git 제외

`all.jsonl`은 대용량. git 제외 후 스냅샷 압축본만 커밋. CLAUDE.md 64행.

## 파서 후보

| 후보 | 상태 | 사유 |
|---|---|---|
| 정규식 기준선 | 채택 후보 | 외부 의존 없음 |
| theseed-bot | 채택 후보 | PyPI 미등재. 로컬 클론 커밋 해시 고정 |
| namumark-clone-core | 비교 대상 | npm 2025-10-28 unpublish. 로컬 클론 커밋 해시 고정 |
| biryo | 제외 | Scala 2.11 대상. 환경은 JDK 21. 빌드 불가 판단 |

커밋 해시는 `parser_candidates.json`에 기록. 재현 불가 경로가 둘이므로 고정 필요.

## 평문 생성 규칙

- 요소 제거 자리에 공백 삽입이 기본. 없는 합성어 생성 방지
- 각주는 예외. 앞 단어에 붙고 뒤에 조사가 이어지므로 직접 결합
  - 예) `각주 하나[* 내용]와` 는 `각주 하나와` 로 복원
- 품질 검사에 붙은 단어 잔존 여부 표본 확인 포함
