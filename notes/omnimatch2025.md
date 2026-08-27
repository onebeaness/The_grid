# omnimatch2025

**미해결 항목.** 제공된 서지로 논문을 특정하지 못했다.

제공된 정보: "OmniMatch (2025). EDBT. Amazon과 Douban 기준 콜드스타트 벤치마킹"

## 확인한 것

다음 경로를 모두 시도했고 해당 논문을 찾지 못했다.

- Crossref 제목 검색 `OmniMatch` → 2건. 둘 다 데이터 통합 분야다.
  - `10.14778/3749646.3749715` OmniMatch: Joinability Discovery in Data Products (VLDB 2025)
  - `10.23889/ijpds.v9i5.2588` OmniMatch: A Large Language Model-Based Data Linkage Tool (IJPDS 2024)
- arXiv 제목 검색 `OmniMatch` → 1건. `2403.07653` OmniMatch: Effective Self-Supervised Any-Join Discovery in Tabular Data. 역시 데이터 조인 탐색이다.
- Crossref에서 EDBT DOI 접두사 `10.48786`에 교차도메인 추천·콜드스타트 벤치마크 논문 검색 → 0건
- Semantic Scholar 검색 → 결과 없음(무인증 호출 제한 포함)

검색되는 OmniMatch는 전부 **테이블 데이터의 조인 가능성 탐색** 논문이고, 추천 시스템 논문이 아니다.

## 가능성

1. 이름이 다르게 기억된 논문일 수 있다.
2. EDBT가 아닌 다른 학회일 수 있다.
3. 아직 색인되지 않은 최신 논문일 수 있다.

## 필요한 것

저자명 또는 URL. 둘 중 하나만 있으면 특정된다.

## 이 갈래에서 이 자리가 하던 역할

사용자 정리에서 이 논문은 "Amazon과 Douban 기준 콜드스타트 벤치마킹"을 맡고 있었다. 그 역할은 현재 [[zhu2021tmcdr]](Amazon 7개 카테고리 + Douban 3개 도메인, AUC/NDCG@K)과 [[zhao2020catn]](중첩 비율 스윕)이 상당 부분 대신하고 있다. 다만 **표준화된 벤치마크 스위트**라는 역할은 비어 있고, 그 자리는 [[survey2025coldstart]]가 조망 수준에서만 메운다.

## 관련 노트

[[zhu2021tmcdr]] [[zhao2020catn]] [[survey2025coldstart]] [[concepts/evaluation-protocol]]
