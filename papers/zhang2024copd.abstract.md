# zhang2024copd

Zhang et al. (2024). Coherence-guided Preference Disentanglement for Cross-domain Recommendation (CoPD).

게재지: ACM TOIS
DOI: 10.1145/3742855
접근: 전문 미확보 (닫힌 게재지 또는 다운로드 실패)
초록 출처: crossref

## 초록

Discovering user preferences across different domains is pivotal in cross-domain recommendation systems, particularly when platforms lack comprehensive user-item interactive data. The limited presence of shared users often hampers the effective modeling of common preferences. While leveraging shared items’ attributes, such as category and popularity, can enhance cross-domain recommendation performance, the scarcity of shared items between domains has limited research in this area. To address this, we propose a Coherence-guided Preference Disentanglement (CoPD) method aimed at improving cross-domain recommendation by (i) explicitly extracting shared item attributes to guide the learning of shared user preferences and (ii) disentangling these preferences to identify specific user interests transferred between domains. CoPD introduces coherence constraints on item embeddings of shared and specific domains, aiding in extracting shared attributes. Moreover, it utilizes these attributes to guide the disentanglement of user preferences into separate embeddings for interest and conformity through a popularity-weighted loss. Experiments conducted on real-world datasets demonstrate the superior performance of our proposed CoPD over existing competitive baselines, highlighting its effectiveness in enhancing cross-domain recommendation performance. The code is available at https://github.com/XiangZongyi/CoPD .
