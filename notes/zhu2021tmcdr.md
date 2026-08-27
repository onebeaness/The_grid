# zhu2021tmcdr

Zhu et al. (2021). Transfer-Meta Framework for Cross-domain Recommendation to Cold-Start Users (TMCDR). *SIGIR 2021*. DOI 10.1145/3404835.3463010 / arXiv 2105.04785
보유: 전문 PDF (`papers/zhu2021tmcdr.pdf`)

## 무엇을 물었는가

EMCDR 계열은 매핑 함수를 **중첩 사용자 표본에 맞춰** 학습한다. 그런데 실제 적용 대상은 학습에서 못 본 콜드스타트 사용자다. 이 간극을 메타러닝으로 좁힐 수 있는가. 즉 "매핑을 학습"하는 대신 "매핑을 학습하는 법을 학습"하면 나아지는가.

## 어떻게 측정했는가

**구조**: 2단계. (1) transfer 단계에서 도메인별 임베딩을 사전학습한다. (2) meta 단계에서 임베딩을 고정한 채 task-oriented 메타 네트워크를 학습한다. 학습 태스크 하나는 **사용자 두 명의 샘플만** 포함하도록 구성해 타깃 태스크(콜드스타트)를 흉내낸다.

**데이터와 태스크** — 6개 CDR 태스크
- Amazon 5-core에서 7개 카테고리 선정: apps_for_android, video_games, home_and_kitchen, movies_and_tv, cds_and_vinyl, books, tools_and_home_improvement
  - S1: apps_for_android → video_games
  - S2: home_and_kitchen → tools_and_home_improvement
  - S3: movies_and_tv → cds_and_vinyl
  - S4: books → movies_and_tv
- Douban 3개 도메인
  - S5: movie → music
  - S6: music → book

**절차**: 각 태스크에서 중첩 사용자의 약 **20%** 를 콜드스타트 사용자로 무작위 지정하고, 그들의 타깃 도메인 샘플 전부를 테스트에 쓴다. 평점을 이진 암묵 피드백으로 변환, 양성 1개당 음성 4개 샘플링. 임베딩 차원 256, 배치 1280, Adam. 지표는 **AUC와 NDCG@10**, 3회 시행 평균.

## 무엇이 나왔는가

TMCDR_MF 성적
| 태스크 | AUC | NDCG@10 | 최고 베이스라인 AUC |
|---|---|---|---|
| S1 apps → games | 0.7501 | 0.2246 | 0.7271 (EMCDR_MF) |
| S2 home → tools | 0.7253 | 0.2427 | 0.7232 (ListRank-MF) |
| S3 movies → cds | 0.8282 | 0.3334 | 0.8191 (CML) |
| S4 books → movies | 0.8056 | 0.2775 | 0.7936 (EMCDR_MF) |
| **S5 Douban movie → music** | **0.8589** | 0.3483 | 0.8524 (CST) |
| **S6 Douban music → book** | **0.8442** | 0.3778 | 0.8406 (CST) |

논문 자체의 관찰 중 우리에게 중요한 것:
- EMCDR_MF가 EMCDR_ori_MF를 크게 앞선다. 이유는 **중첩 사용자만으로는 아이템 일부밖에 못 덮기 때문**이다. 중첩 사용자 샘플만 쓰는 것보다 전체 샘플을 쓰는 게 낫다.
- CMF, BPR, ListRank-MF, CML의 상대 성능이 시나리오마다 다르다. **태스크마다 다른 모델이 맞다.**
- Douban 결과의 신뢰구간이 Amazon보다 좁다.

## 우리 좌표계로 옮기면

**평가 지표와 태스크 구성을 여기서 가져온다.** AUC + NDCG@K, 도메인 쌍별 태스크 매트릭스, 중첩 사용자 20%를 콜드스타트로 홀드아웃. 그리드 전이 계층의 표준 평가는 이 형태여야 한다.

그런데 이 논문에서 가장 값어치 있는 것은 저자들이 강조하지 않은 부분이다. **S5와 S6, 즉 우리 사례와 가장 가까운 엔터테인먼트 도메인 쌍에서 TMCDR의 이득이 가장 작다.**

- S5: TMCDR 0.8589 vs CST 0.8524 → **+0.8%**
- S6: TMCDR 0.8442 vs CST 0.8406 → **+0.4%**
- 심지어 S5에서 단순 CMF가 0.8465다. 정교한 메타러닝 프레임워크가 collective MF 대비 1.5% 앞선다.

반면 Amazon 이종 카테고리(S1 apps→games)에서는 절대 AUC가 0.75로 낮고 개선폭은 크다.

읽는 방식은 이렇다. **영화·음악·책처럼 서로 가까운 엔터테인먼트 도메인 사이에서는 전이가 이미 쉽고, 정교한 전이 기법의 한계이익이 작다.** 그리드가 "도메인 전이 기술"을 차별점으로 내세우는 것은 이 데이터에서 지지받지 못한다. 우리가 다루려는 도메인들은 전이가 어려운 쪽이 아니라 쉬운 쪽이다.

동시에 상한선도 준다. 이 조건에서도 **AUC 0.84~0.86이 천장**이다. → [[concepts/cold-start]]

"태스크마다 다른 모델이 맞다"는 관찰은 그리드에 직접 부담을 준다. 단일 전이 모델로 모든 도메인 쌍을 덮는 설계는 이 데이터와 맞지 않는다. 도메인 쌍별 전이 행렬을 두고 각각 다르게 다뤄야 한다.

## 이 논문이 배제하는 것

- **중첩 사용자 샘플만으로 매핑을 학습하는 것이 최선이라는 가정**을 배제한다(EMCDR_ori 대 EMCDR 비교).
- **하나의 CDR 모델이 모든 도메인 쌍에서 최선이라는 가정**을 배제한다.
- 이 논문은 **콘텐츠·텍스트 정보를 쓰지 않는다.** 상호작용 신호만의 전이다.
- **아이템 콜드스타트**를 다루지 않는다. 사용자 콜드스타트만이다.
- 20% 홀드아웃 하나만 본다. **중첩 비율 자체를 변화시키지 않는다.** 그건 [[zhao2020catn]]의 설계다.

## 관련 노트

[[man2017emcdr]] [[zhao2020catn]] [[zhang2024copd]] [[du2024jicdr]] [[concepts/domain-transfer]] [[concepts/cold-start]] [[concepts/evaluation-protocol]]
