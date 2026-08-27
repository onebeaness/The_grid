# 코퍼스

취향·소비 관련 연구자료를 폭넓게 수집해 임베딩·검색·분석 가능한 로컬 코퍼스로 만든다.
선별이 아니라 수집이 목적이므로 관련성 게이트만 두고 주제 필터는 걸지 않는다.

## 파이프라인

```
keywords.json ─► collect.py ─► records.jsonl ─► postprocess.py
                                    │
                                    ▼
                               fetch.py ─► pdf/ , abstracts/ , manifest.jsonl
                                    │
                                    ▼
                          index.py extract ─► text/*.json (섹션 단위)
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            index.py refs                    index.py embed
     citation_graph.jsonl                    index/emb.npy
     unmatched_refs.jsonl                    index/chunks.jsonl
                    │                               │
                    ▼                               ▼
             snowball.py ──(2회전)──► collect       query.py
```

## 실행

```bash
python3 collect.py --round 0 --per-query 200      # 수집
python3 postprocess.py                            # 비논문·근접중복 표시
python3 fetch.py --target 4000                    # 원문 확보
python3 index.py extract                          # 텍스트 추출
python3 index.py refs                             # 인용 그래프 + 미매칭 참조
python3 index.py embed                            # 청크 임베딩
python3 snowball.py --round 1 --min-count 2       # 눈덩이 1회전
python3 report.py                                 # 현황
python3 query.py "질문" -k 8                      # 검색
```

`bash run_all.sh` 로 전체를 순서대로 돌린다. 각 단계는 중단 후 재실행하면 이어서 진행한다.

`records.jsonl`과 `done.jsonl`은 수집 중 계속 바뀌고 10만 건대에서 100MB를 넘어 git에 넣지 않는다.
완료 시점의 `records.jsonl.gz` 스냅샷만 커밋한다.

## 지난 작업에서 걸린 것들의 처리

| 문제 | 처리 |
|---|---|
| Semantic Scholar 무인증 429 | Retry-After 존중 지수 백오프. 연속 12회면 사유를 남기고 그 라운드에서 제외 |
| OpenAlex 일일 예산 소진 | 응답 본문에서 budget 감지 즉시 소스 차단. 재시도하지 않고 스킵 사유 기록 |
| PubMed가 엉뚱한 논문 반환 | `pubmed_abstract_by_doi`는 efetch 레코드의 `ArticleId[doi]`가 실제로 일치할 때만 반환. 제목 유사도 0.85 재확인 |
| 퍼지 매칭 오탐 | 병합은 정규화 제목 일치 + 원 제목 유사도 0.90 + 연도 허용오차 2년 + DOI 불일치 배제를 모두 통과해야 성립 |
| Crossref 커서 페이징이 관련도 정렬을 끔 | offset 페이징으로 교체 |
| 키워드 검색의 느슨한 매칭 | `sources.relevant()` 관련성 게이트. 질의어 토큰이 제목·초록·게재지에 실제로 나타나야 통과 |
| PNAS Cloudflare, ACM DL 차단 | 초록만 저장하고 `blocked_reason`에 `cloudflare_challenge` / `acm_dl_block` 기록 |
| DBLP 5xx | 연속 6회면 소스 차단 |

## 상한과 그 기록

무음 절단을 만들지 않는다. 상한에 걸린 것은 전부 기록한다.

| 상한 | 값 | 기록 위치 |
|---|---|---|
| 질의당 결과 수 | `--per-query` (기본 200) | `collect_state.json`의 `capped` |
| Crossref 관련도 유효 깊이 | 1000건 | 코드 주석, 위 `capped`에 반영 |
| 원문 시도 총량 | `--target` | `skipped_fetch.jsonl` (사유 포함, 메타데이터는 보유) |
| 디스크 | 8GB | `manifest.jsonl`의 `attempts[].via=disk_guard` |
| S2 라운드 내 재시도 | 연속 429 12회 | `collect_state.json`의 `state.semanticscholar.reason` |

## 파일

| 파일 | 내용 |
|---|---|
| `records.jsonl` | 병합된 서지 레코드. 계열, 질의어, 소스, 연도, 인용수, 학회지, 초록 |
| `manifest.jsonl` | 항목별 원문 확보 상태. `status` = pdf / abstract / none, 시도 이력과 차단 사유 |
| `skipped_fetch.jsonl` | 원문을 시도하지 않은 항목과 사유 |
| `text/*.json` | 섹션 단위로 분할한 본문 |
| `index/chunks.jsonl` | 청크 텍스트와 메타 |
| `index/emb.npy` | 정규화된 청크 임베딩 (all-MiniLM-L6-v2, 384차원) |
| `index/citation_graph.jsonl` | 코퍼스 내부 인용 간선 `{src, dst, sim}` |
| `index/unmatched_refs.jsonl` | 코퍼스에 없는 반복 등장 참조. 눈덩이 입력 |
| `done.jsonl` | 완료한 (계열, 질의어, 소스). 재개용 |

`pdf/`, `text/`, `index/emb.npy`, `logs/` 는 git에 넣지 않는다.

## 인용 그래프에 대한 단서

Semantic Scholar가 429로 막혀 있어 인용 관계는 **PDF 참고문헌 절을 파싱해 코퍼스 내부에서 매칭**해 만든다.
따라서 간선은 전문을 확보한 논문에서 나가는 것만 있고, 코퍼스 밖으로 나가는 인용은 `unmatched_refs.jsonl`에 남는다.
S2가 열리면 `snowball.py --s2-top N`으로 보강한다.
