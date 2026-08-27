# 횡단 개념

여러 논문에 걸쳐 반복되는 것들. 각 개념 노트는 근거 논문 노트로 링크한다.

## 목록

| 개념 | 한 줄 |
|---|---|
| [[latent-space]] | 심리측정 계열과 추천 계열이 서로 다른 것을 "잠재 공간"이라 부른다. 그리드는 둘 다 필요하다 |
| [[domain-transfer]] | 도메인마다 공간을 잇는 답과 하나의 공간만 만드는 답이 있고, 우리 도메인은 전이가 이미 쉬운 쪽이다 |
| [[cold-start]] | 하나로 불리지만 세 문제다. 아이템 쪽은 풀렸고, 사용자 쪽은 천장이 AUC 0.69~0.86이다 |
| [[perceived-vs-actual-similarity]] | 그리드가 계산하는 것은 실제 유사성이고, 끌림을 움직이는 것은 지각된 유사성이다 |
| [[declared-vs-revealed]] | 같은 사람의 취향인데 어떻게 물었는지에 따라 다른 좌표가 나온다. 그 차이가 재료다 |
| [[text-as-coordinate]] | 아이템을 좌표에 올리는 한계비용이 거의 0이다. 그리고 텍스트는 사용자가 고칠 수 있다 |
| [[overlap-scarcity]] | 두 도메인 모두에 기록이 있는 사용자는 소스 도메인의 1.3~10%다. 곡선은 평평하고 양날이다 |
| [[leakage-audit]] | 수집하지 않아도 예측된다. 좌표가 보호속성의 프록시가 되는지 측정해야 한다 |
| [[calibration]] | 축이 있다는 것과 축이 측정도구라는 것은 다르다 |
| [[centrality-weighting]] | 모든 겹침이 같은 값이 아니다. 개수가 아니라 비율이고, 중심성이 조절한다 |
| [[evaluation-protocol]] | 빌려올 것, 지켜야 할 규칙, 새로 만들어야 할 것 |
| [[what-not-to-build]] | 문헌이 안 된다고 밝힌 것들. 10개 |

## 읽는 순서 제안

**제품 정의를 먼저 보려면**
[[what-not-to-build]] → [[perceived-vs-actual-similarity]] → [[centrality-weighting]]

**시스템 구조를 먼저 보려면**
[[latent-space]] → [[text-as-coordinate]] → [[cold-start]] → [[domain-transfer]] → [[overlap-scarcity]]

**검증과 리스크**
[[calibration]] → [[evaluation-protocol]] → [[leakage-audit]]

## 갈래별 대응

사용자가 정리한 다섯 갈래가 개념 노트로 어떻게 흩어졌는지.

| 갈래 | 주로 기여하는 개념 |
|---|---|
| 1. 취향 구조 자체 | [[latent-space]] [[calibration]] [[declared-vs-revealed]] |
| 2. 소비 기록에서 사람 읽기 | [[leakage-audit]] [[text-as-coordinate]] [[calibration]] |
| 3. 도메인 간 전이 | [[domain-transfer]] [[overlap-scarcity]] [[cold-start]] [[evaluation-protocol]] |
| 4. 텍스트로 좌표 만들기 | [[text-as-coordinate]] [[cold-start]] [[latent-space]] |
| 5. 취향 유사도와 관계 | [[perceived-vs-actual-similarity]] [[centrality-weighting]] [[what-not-to-build]] |

**갈래 5가 [[what-not-to-build]]의 대부분을 차지한다.** 이 갈래는 그리드에 부품을 주는 것이 아니라 제품 정의를 제약한다.
