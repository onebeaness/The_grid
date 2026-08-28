# omnimatch2025

Dai, El-Roby, Adeeb & Thaker (2025). OmniMatch: Overcoming the Cold-Start Problem in Cross-Domain Recommendations using Auxiliary Reviews. *EDBT 2025*, 80–91. DOI 10.48786/EDBT.2025.07
소속 Carleton University. dblp `conf/edbt/DaiEAT25`
보유: 전문 PDF (`papers/omnimatch2025.pdf`, 12쪽)

**해결 경위**: 이전 조사에서 미해결로 기록됨. Crossref 제목검색과 arXiv에서 검색되는 OmniMatch가 전부 데이터 조인 탐색 논문이었고, EDBT DOI 접두사 검색도 0건이었음. 당시 DBLP가 503 상태여서 조회하지 못한 것이 원인. DBLP 복구 후 즉시 특정됨.

## 무엇을 물었는가

- 교차도메인 콜드스타트에서 매핑 함수 방식의 대안 가능성
- 기존 방식은 콜드스타트 사용자의 소스 도메인 특징을 타깃 도메인 특징으로 변환하는 매핑 함수를 학습
- 이 논문은 매핑 대신 **타깃 도메인의 보조 리뷰를 생성**하는 접근을 제시

## 어떻게 측정했는가

**구조**
- 콜드스타트 사용자에 대해 타깃 도메인의 보조 리뷰(auxiliary reviews)를 생성
- 생성된 리뷰에서 도메인 불변 정보를 채굴하고 전이
- 도메인 적대 학습(domain adversarial training)과 지도 대조 학습(supervised contrastive learning)으로 소스와 타깃 특징 추출기의 출력이 도메인 불변이 되도록 강제

**데이터**
- Amazon Review 데이터셋과 Douban 데이터셋
- 도메인 셋. Books, Movies, Music
- 시나리오 여섯. Books→Movies, Movies→Books, Movies→Music, Music→Movies, Books→Music, Music→Books

**절차**
- 리뷰가 없는 레코드 제거
- 각 시나리오에서 두 도메인 모두에 기록이 있는 사용자만 유지
- 중첩 사용자의 80퍼센트를 학습 사용자로 무작위 선정
- 나머지 20퍼센트를 콜드스타트 사용자로 처리. 그 절반을 검증, 절반을 테스트로 배정
- 콜드스타트 사용자의 타깃 도메인 리뷰는 모델에 보이지 않음

**입력 선택**
- 전체 리뷰 대신 **review summary 필드**를 사용
- 소문자 변환과 문장부호 제거
- 전체 리뷰 분석보다 효과적이라는 실험 결과에 근거
- 입력 제약 안에서 더 많은 데이터를 처리할 수 있음

**지표**
- RMSE와 MAE
- 실험당 무작위 5회 시행 평균
- Nvidia A100 40GB 1장

## 무엇이 나왔는가

**전체 성능**
- 여섯 시나리오 전부에서 기존 방법 상회
- Douban 평균 개선. RMSE 23.1퍼센트, MAE 26.6퍼센트
- Amazon 평균 개선. RMSE 7.4퍼센트, MAE 9.1퍼센트
- Douban Books→Movies 최대 개선. RMSE 25.9퍼센트, MAE 32.6퍼센트
- Amazon Movies→Music. RMSE 14.6퍼센트, MAE 13.0퍼센트

**중첩 사용자 비율 스윕**  100 / 80 / 50 / 20퍼센트

| 시나리오 | 방법 | 100% | 80% | 50% | 20% | 열화폭 |
|---|---|---|---|---|---|---|
| Books→Movies | EMCDR | 1.166 | 1.184 | 1.197 | 1.221 | +4.7% |
| Books→Movies | PTUPCDR | 1.049 | 1.066 | 1.143 | 1.225 | +16.8% |
| Books→Movies | **OmniMatch** | **1.031** | 1.036 | 1.041 | **1.071** | **+3.9%** |
| Movies→Music | OmniMatch | 0.940 | 0.953 | 0.973 | 1.006 | +7.0% |
| Books→Music | OmniMatch | 0.962 | 0.976 | 0.991 | 1.014 | +5.4% |

- 중첩 20퍼센트에서도 RMSE 최고 성적 유지
- 저자 해석. 전통적 방식은 소스 표현 학습, 타깃 표현 학습, 매핑 함수 학습의 3단계 최적화이며 학습 데이터 양에 민감
- 중첩 비율이 작으면 매핑 함수가 학습 데이터 부족으로 무너짐
- PTUPCDR 이 100퍼센트에서 1.049 로 좋지만 20퍼센트에서 1.225 로 급락. 매핑 방식의 취약점이 수치로 드러남

## 우리 좌표계로 옮기면

- **매핑 함수 계보에 대한 반례**. [[man2017emcdr]] 이후 [[zhao2020catn]], [[zhu2021tmcdr]] 가 모두 개선한 것이 매핑 함수. 이 논문은 매핑을 버림
- 대신 **타깃 도메인의 텍스트를 생성**해 채움. [[huang2024llmsim]] 의 상호작용 시뮬레이션과 같은 발상이 리뷰 텍스트에 적용된 것
- 3번 갈래와 4번 갈래가 만나는 지점. 교차도메인 전이를 텍스트 생성으로 푸는 접근
- review summary 가 전체 리뷰보다 낫다는 관측은 [[concepts/text-as-coordinate]] 의 청크 설계에 직접 시사점. 긴 텍스트가 항상 낫지 않음
- 중첩 20퍼센트에서 열화 3.9퍼센트는 [[zhao2020catn]] 의 5퍼센트 열화 4.6퍼센트와 같은 구간. [[concepts/overlap-scarcity]] 의 결론을 강화
- 매핑 방식(PTUPCDR)의 16.8퍼센트 열화와 대비되므로, 그리드가 매핑 계열을 채택할 때의 위험이 수치로 확인됨

## 이 논문이 배제하는 것

- **매핑 함수가 교차도메인 콜드스타트의 필수 구성이라는 전제를 배제**
- 전체 리뷰 텍스트가 요약보다 낫다는 가정을 배제. review summary 가 더 효과적
- 중첩 사용자가 많아야 전이가 된다는 가정을 배제. 20퍼센트에서도 최고 성적
- 다만 리뷰가 있는 도메인에서만 성립. 리뷰 없는 도메인에는 적용 불가
- 평점 예측 과제. 랭킹 성능은 이 논문이 다루지 않음
- 중첩 사용자가 전혀 없는 완전 콜드스타트는 다루지 않음

## 관련 노트

[[man2017emcdr]] [[zhao2020catn]] [[zhu2021tmcdr]] [[du2024jicdr]] [[zhang2024copd]] [[huang2024llmsim]] [[concepts/domain-transfer]] [[concepts/overlap-scarcity]] [[concepts/cold-start]] [[concepts/text-as-coordinate]]
