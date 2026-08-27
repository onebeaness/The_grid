#!/usr/bin/env python3
"""heegyu/namuwiki 스트리밍 1회 패스.

수집 항목
  리다이렉트 행 수와 실제 문서 수
  namespace 실제 값 분포
  분류 표기 위치 분포(앞 / 끝 / 양쪽 / 중간)
  text 길이 분포
  분류명 역집계(분류 네임스페이스 문서가 없을 때의 대체 경로)
  실제 문서 무작위 표본 100건(저수지 표집)

전체를 메모리에 올리지 않음. 표본과 카운터만 유지.
"""
import argparse, collections, json, os, random, re, sys, time
from array import array

# 데이터셋 카드는 2022/03/01 을 명시. 실제 파일명은 namuwiki_20210301.parquet.
# 어느 쪽이 맞는지 확정할 근거가 없어 둘 다 기록한다. 추정하지 않는다.
SNAPSHOT = "2021-03-01"                       # 실증 판정. 카드 표기 2022-03-01은 오류
SNAPSHOT_CARD_LABEL = "2022-03-01"            # 데이터셋 카드 표기. 실제와 다름
DATASET = "heegyu/namuwiki"
PARQUET = "namuwiki_20210301.parquet"

RX_REDIRECT = re.compile(r"^\s*#\s*(?:redirect|넘겨주기)\s+(.+?)\s*$", re.I | re.M)
RX_CATEGORY = re.compile(r"\[\[(?:분류|Category)\s*:\s*([^\]|]+?)\s*(?:\|[^\]]*)?\]\]", re.I)
RX_HEADING = re.compile(r"^={1,6}#?\s*.+?\s*#?={1,6}\s*$", re.M)

def is_redirect(t):
    return bool(t) and bool(re.match(r"^\s*#\s*(?:redirect|넘겨주기)\s", t, re.I))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0이면 전체")
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20220301)
    ap.add_argument("--out", default="/home/user/The_grid/items")
    ap.add_argument("--progress", type=int, default=50000)
    ap.add_argument("--parquet", default="")
    a = ap.parse_args()

    os.environ.setdefault("HF_HOME", "/home/user/hf-cache")
    rng = random.Random(a.seed)

    import pyarrow.parquet as pq
    path = a.parquet
    if not path:
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(DATASET, PARQUET, repo_type="dataset")
    pf = pq.ParquetFile(path)
    fstat = os.stat(path)
    file_meta = {"path": path, "name": os.path.basename(path),
                 "size_bytes": fstat.st_size, "rows": pf.metadata.num_rows,
                 "row_groups": pf.metadata.num_row_groups,
                 "created_by": pf.metadata.created_by}

    def rows_iter():
        for batch in pf.iter_batches(batch_size=2048,
                                     columns=["title", "text", "contributors", "namespace"]):
            d = batch.to_pydict()
            for i in range(len(d["title"])):
                yield {"title": d["title"][i], "text": d["text"][i],
                       "contributors": d["contributors"][i], "namespace": d["namespace"][i]}
    ds = rows_iter()

    n = 0
    n_redirect = 0
    n_doc = 0
    n_empty = 0
    ns_count = collections.Counter()
    ns_examples = {}
    lens_doc = array("i")
    lens_redirect = array("i")
    cat_names = collections.Counter()
    cat_per_doc = array("i")
    pos_count = collections.Counter()
    n_doc_with_cat = 0
    redirect_targets = collections.Counter()
    heading_count = array("i")
    reservoir = []
    contrib_present = 0

    t0 = time.time()
    for row in ds:
        n += 1
        title = row.get("title") or ""
        text = row.get("text") or ""
        ns = row.get("namespace")
        ns_count[repr(ns)] += 1
        if repr(ns) not in ns_examples:
            ns_examples[repr(ns)] = title
        if row.get("contributors"): contrib_present += 1

        if not text.strip():
            n_empty += 1
        if is_redirect(text):
            n_redirect += 1
            lens_redirect.append(min(len(text), 2 ** 31 - 1))
            m = RX_REDIRECT.search(text)
            if m: redirect_targets[m.group(1).strip().lstrip("\\")] += 1
        else:
            n_doc += 1
            L = len(text)
            lens_doc.append(min(L, 2 ** 31 - 1))
            heading_count.append(len(RX_HEADING.findall(text)))

            ms = list(RX_CATEGORY.finditer(text))
            cat_per_doc.append(len(ms))
            if ms:
                n_doc_with_cat += 1
                for m in ms: cat_names[m.group(1).strip()] += 1
                win = max(300, int(L * 0.05))
                has_front = any(m.start() < win for m in ms)
                has_end = any(m.end() > L - win for m in ms)
                if has_front and has_end: pos_count["양쪽"] += 1
                elif has_front: pos_count["앞"] += 1
                elif has_end: pos_count["끝"] += 1
                else: pos_count["중간"] += 1
            else:
                pos_count["분류 없음"] += 1

            # 저수지 표집. 실제 문서에서만
            if len(reservoir) < a.sample:
                reservoir.append({"title": title, "text": text, "row_index": n - 1})
            else:
                j = rng.randrange(n_doc)
                if j < a.sample:
                    reservoir[j] = {"title": title, "text": text, "row_index": n - 1}

        if a.progress and n % a.progress == 0:
            el = time.time() - t0
            sys.stderr.write("  %d행  문서 %d  리다이렉트 %d  %.1f분  %.0f행/s\n"
                             % (n, n_doc, n_redirect, el / 60, n / max(el, 1)))
            sys.stderr.flush()
        if a.limit and n >= a.limit: break

    el = time.time() - t0

    def pct(arr, ps=(1, 5, 25, 50, 75, 90, 95, 99)):
        if not len(arr): return {}
        s = sorted(arr)
        return {("p%d" % p): s[min(len(s) - 1, int(len(s) * p / 100))] for p in ps}

    def hist(arr, edges):
        h = collections.Counter()
        for v in arr:
            for e in edges:
                if v < e: h["<%d" % e] += 1; break
            else: h[">=%d" % edges[-1]] += 1
        return {k: h[k] for k in (["<%d" % e for e in edges] + [">=%d" % edges[-1]]) if h.get(k)}

    EDGES = [50, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
    rep = {
        "snapshot_date": SNAPSHOT,
        "snapshot_date_source": "데이터셋 카드 README 표기",
        "snapshot_date_card_label": SNAPSHOT_CARD_LABEL,
        "snapshot_date_discrepancy": ("카드는 2022/03/01, 파일명은 namuwiki_20210301. "
                                      "확정 근거 없음. 둘 다 기록."),
        "dataset": DATASET,
        "file": file_meta,
        "scanned_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scan_complete": not a.limit,
        "elapsed_min": round(el / 60, 1),
        "rows_total": n,
        "rows_redirect": n_redirect,
        "rows_document": n_doc,
        "rows_empty_text": n_empty,
        "redirect_ratio": round(n_redirect / max(n, 1), 4),
        "contributors_nonempty": contrib_present,
        "namespace_distribution": dict(ns_count),
        "namespace_examples": ns_examples,
        "text_length_document": {"percentiles": pct(lens_doc), "histogram": hist(lens_doc, EDGES),
                                 "mean": round(sum(lens_doc) / max(len(lens_doc), 1), 1)},
        "text_length_redirect": {"percentiles": pct(lens_redirect),
                                 "mean": round(sum(lens_redirect) / max(len(lens_redirect), 1), 1)},
        "category_position": dict(pos_count),
        "documents_with_category": n_doc_with_cat,
        "categories_per_document": {"percentiles": pct(cat_per_doc),
                                    "mean": round(sum(cat_per_doc) / max(len(cat_per_doc), 1), 2)},
        "unique_category_names": len(cat_names),
        "headings_per_document": {"percentiles": pct(heading_count),
                                  "mean": round(sum(heading_count) / max(len(heading_count), 1), 2)},
        "category_namespace_documents": sum(v for k, v in ns_count.items() if "분류" in k or "Category" in k),
        "note": "분류는 별도 필드가 아니라 본문 [[분류:이름]] 표기에서 추출. 위치가 앞뒤로 갈림.",
    }

    os.makedirs(a.out, exist_ok=True)
    json.dump(rep, open(os.path.join(a.out, "scan_%s.json" % SNAPSHOT), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    with open(os.path.join(a.out, "category_names_%s.jsonl" % SNAPSHOT), "w", encoding="utf-8") as f:
        for name, c in cat_names.most_common():
            f.write(json.dumps({"snapshot_date": SNAPSHOT, "category": name, "doc_count": c},
                               ensure_ascii=False) + "\n")
    with open(os.path.join(a.out, "redirect_targets_%s.jsonl" % SNAPSHOT), "w", encoding="utf-8") as f:
        for name, c in redirect_targets.most_common():
            f.write(json.dumps({"snapshot_date": SNAPSHOT, "target": name, "count": c},
                               ensure_ascii=False) + "\n")
    sp = "/home/user/The_grid/namu/samples/real_sample_%d.jsonl" % a.sample
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        for r in reservoir:
            r["snapshot_date"] = SNAPSHOT
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    sys.stderr.write("\n[scan] 완료 %d행 / 문서 %d / 리다이렉트 %d / 분류명 %d종 / 표본 %d건 / %.1f분\n"
                     % (n, n_doc, n_redirect, len(cat_names), len(reservoir), el / 60))

if __name__ == "__main__":
    main()
