"""텍스트 추출 -> 섹션 분할 -> 청크 임베딩 -> 벡터 인덱스, 그리고 인용 그래프.

subcommand:
  extract  PDF/초록 -> text/*.json (섹션 단위)
  embed    청크 생성 + 임베딩 -> index/
  refs     참고문헌 파싱 -> 코퍼스 내부 인용 그래프 + 미매칭 참조(눈덩이 입력)
  all      위 셋을 순서대로
"""
import json, os, re, sys, argparse, math, time
import sources as S

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "manifest.jsonl")
RECORDS = os.path.join(HERE, "records.jsonl")
TEXTDIR = os.path.join(HERE, "text")
IDXDIR = os.path.join(HERE, "index")
GRAPH = os.path.join(IDXDIR, "citation_graph.jsonl")
UNMATCHED = os.path.join(IDXDIR, "unmatched_refs.jsonl")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

SECTION_RX = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?("
    r"abstract|introduction|background|related\s+works?|preliminaries|"
    r"problem\s+(?:definition|formulation|statement)|method(?:s|ology)?|approach|model|"
    r"framework|experiment(?:s|al\s+setup)?|evaluation|results?|analysis|"
    r"discussion|limitations?|conclusions?(?:\s+and\s+future\s+work)?|"
    r"future\s+work|references|bibliography|appendix|acknowledge?ments?"
    r")\s*$", re.I)
REF_HEAD_RX = re.compile(r"^\s*(references|bibliography|works\s+cited)\s*$", re.I)

# ---------- extract ----------
def extract_pdf(path):
    import pymupdf
    d = pymupdf.open(path)
    pages = [p.get_text() for p in d]
    d.close()
    return pages

def split_sections(pages):
    lines = []
    for pi, txt in enumerate(pages):
        for ln in txt.split("\n"):
            lines.append((pi + 1, ln))
    secs = []
    cur = {"name": "front", "page_start": 1, "lines": []}
    for pg, ln in lines:
        st = ln.strip()
        if 0 < len(st) <= 60 and SECTION_RX.match(st):
            if cur["lines"]: secs.append(cur)
            cur = {"name": st.lower(), "page_start": pg, "lines": []}
        else:
            cur["lines"].append(ln)
    if cur["lines"]: secs.append(cur)
    out = []
    for s in secs:
        body = re.sub(r"[ \t]+", " ", "\n".join(s["lines"])).strip()
        if len(body) < 40: continue
        out.append({"name": s["name"], "page_start": s["page_start"], "text": body})
    return out

def cmd_extract(args):
    os.makedirs(TEXTDIR, exist_ok=True)
    n_pdf = n_abs = n_fail = 0
    for line in open(MANIFEST, encoding="utf-8"):
        try: m = json.loads(line)
        except Exception: continue
        out = os.path.join(TEXTDIR, re.sub(r"[^A-Za-z0-9._-]", "_", m["key"])[:150] + ".json")
        if os.path.exists(out) and not args.force: continue
        doc = {"key": m["key"], "title": m.get("title"), "year": m.get("year"),
               "venue": m.get("venue"), "doi": m.get("doi"), "families": m.get("families"),
               "citations": m.get("citations"), "source_kind": m["status"], "sections": []}
        if m["status"] == "pdf" and m.get("pdf"):
            p = os.path.join(HERE, m["pdf"])
            if not os.path.exists(p): n_fail += 1; continue
            try:
                doc["sections"] = split_sections(extract_pdf(p)); n_pdf += 1
            except Exception as e:
                doc["error"] = str(e)[:120]; n_fail += 1
        elif m["status"] == "abstract" and m.get("abstract_file"):
            p = os.path.join(HERE, m["abstract_file"])
            if not os.path.exists(p): n_fail += 1; continue
            t = open(p, encoding="utf-8").read()
            doc["sections"] = [{"name": "abstract", "page_start": 1, "text": t.strip()}]
            n_abs += 1
        else:
            continue
        if not doc["sections"]: n_fail += 1; continue
        json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    S.log("[extract] pdf %d, abstract %d, 실패/건너뜀 %d" % (n_pdf, n_abs, n_fail))

# ---------- chunk + embed ----------
def chunks_of(doc, size=1100, overlap=150):
    out = []
    for si, s in enumerate(doc["sections"]):
        if REF_HEAD_RX.match(s["name"]) or s["name"].startswith("reference"): continue
        t = s["text"]
        if len(t) <= size:
            out.append((s["name"], s["page_start"], t)); continue
        i = 0
        while i < len(t):
            piece = t[i:i + size]
            if len(piece) > 200: out.append((s["name"], s["page_start"], piece))
            i += size - overlap
    return out

def cmd_embed(args):
    os.makedirs(IDXDIR, exist_ok=True)
    import numpy as np
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME, device="cpu")
    metas, texts = [], []
    files = sorted(f for f in os.listdir(TEXTDIR) if f.endswith(".json"))
    for f in files:
        doc = json.load(open(os.path.join(TEXTDIR, f), encoding="utf-8"))
        for ci, (sec, pg, t) in enumerate(chunks_of(doc)):
            metas.append({"chunk_id": "%s#%d" % (doc["key"], ci), "key": doc["key"],
                          "title": doc.get("title"), "year": doc.get("year"),
                          "venue": doc.get("venue"), "doi": doc.get("doi"),
                          "families": doc.get("families"), "source_kind": doc.get("source_kind"),
                          "section": sec, "page": pg, "n_chars": len(t)})
            texts.append(t)
    S.log("[embed] 문서 %d, 청크 %d" % (len(files), len(texts)))
    if not texts: return
    embs = model.encode(texts, batch_size=64, convert_to_numpy=True,
                        normalize_embeddings=True, show_progress_bar=False)
    np.save(os.path.join(IDXDIR, "emb.npy"), embs.astype("float32"))
    with open(os.path.join(IDXDIR, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for m, t in zip(metas, texts):
            m2 = dict(m); m2["text"] = t
            f.write(json.dumps(m2, ensure_ascii=False) + "\n")
    json.dump({"model": MODEL_NAME, "dim": int(embs.shape[1]), "n_chunks": len(texts),
               "n_docs": len(files), "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
              open(os.path.join(IDXDIR, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    S.log("[embed] 저장 완료. dim=%d" % embs.shape[1])

# ---------- references ----------
def ref_section(doc):
    for s in doc["sections"]:
        if REF_HEAD_RX.match(s["name"]) or s["name"].startswith("reference") \
           or s["name"].startswith("bibliograph"):
            return s["text"]
    return None

SPLIT_NUM = re.compile(r"\n?\s*\[\d{1,3}\]\s*")
SPLIT_DOT = re.compile(r"\n(?=[A-Z][A-Za-z'`-]+,\s*[A-Z])")

def split_refs(txt):
    if not txt: return []
    parts = SPLIT_NUM.split(txt)
    if len(parts) < 4:
        parts = SPLIT_DOT.split(txt)
    out = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip()
        if 40 <= len(p) <= 700: out.append(p)
    return out

class TitleIndex:
    """토큰 역색인으로 후보를 좁힌 뒤 difflib으로 재확인한다."""
    def __init__(self, records):
        self.recs = records
        self.inv = {}
        for i, r in enumerate(records):
            for w in set(r["norm_title"].split()):
                if len(w) < 4: continue
                self.inv.setdefault(w, []).append(i)

    def match(self, ref_text, min_sim=0.72):
        nt = S.norm_title(ref_text)
        toks = [w for w in set(nt.split()) if len(w) >= 4]
        if len(toks) < 3: return None, 0.0
        cnt = {}
        for w in toks:
            for i in self.inv.get(w, []):
                cnt[i] = cnt.get(i, 0) + 1
        if not cnt: return None, 0.0
        best, bs = None, 0.0
        for i, _ in sorted(cnt.items(), key=lambda kv: -kv[1])[:25]:
            cand = self.recs[i]["norm_title"]
            if not cand: continue
            # 참조 문자열은 저자와 서지가 섞여 있으므로 부분 매칭을 본다
            sm = _best_window_sim(nt, cand)
            if sm > bs: best, bs = i, sm
        if best is not None and bs >= min_sim: return self.recs[best], bs
        return None, bs

def _best_window_sim(hay, needle):
    import difflib
    if not needle: return 0.0
    nlen = len(needle.split())
    hw = hay.split()
    if len(hw) <= nlen: return difflib.SequenceMatcher(None, hay, needle).ratio()
    best = 0.0
    for i in range(0, len(hw) - nlen + 1):
        w = " ".join(hw[i:i + nlen])
        r = difflib.SequenceMatcher(None, w, needle).ratio()
        if r > best: best = r
        if best > 0.95: break
    return best

def cmd_refs(args):
    os.makedirs(IDXDIR, exist_ok=True)
    records = []
    for line in open(RECORDS, encoding="utf-8"):
        try: r = json.loads(line)
        except Exception: continue
        if r.get("norm_title"): records.append(r)
    ti = TitleIndex(records)
    S.log("[refs] 제목 색인 %d건" % len(records))

    edges, unmatched = [], {}
    n_docs = n_refs = n_hit = 0
    for f in sorted(os.listdir(TEXTDIR)):
        if not f.endswith(".json"): continue
        doc = json.load(open(os.path.join(TEXTDIR, f), encoding="utf-8"))
        if doc.get("source_kind") != "pdf": continue
        rs = split_refs(ref_section(doc))
        if not rs: continue
        n_docs += 1
        for rt in rs:
            n_refs += 1
            m, sim = ti.match(rt)
            if m:
                edges.append({"src": doc["key"], "dst": m["key"], "sim": round(sim, 3)})
                n_hit += 1
            else:
                k = S.norm_title(rt)[:160]
                if len(k) < 25: continue
                e = unmatched.setdefault(k, {"n": 0, "sample": rt[:400]})
                e["n"] += 1
    with open(GRAPH, "w", encoding="utf-8") as f:
        for e in edges: f.write(json.dumps(e, ensure_ascii=False) + "\n")
    rows = sorted(unmatched.items(), key=lambda kv: -kv[1]["n"])
    with open(UNMATCHED, "w", encoding="utf-8") as f:
        for k, v in rows:
            f.write(json.dumps({"norm": k, "count": v["n"], "sample": v["sample"]},
                               ensure_ascii=False) + "\n")
    S.log("[refs] 참고문헌 있는 문서 %d, 참조 %d, 코퍼스 내부 매칭 %d(%.1f%%), 미매칭 고유 %d"
          % (n_docs, n_refs, n_hit, 100.0 * n_hit / max(1, n_refs), len(rows)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract", "embed", "refs", "all"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd in ("extract", "all"): cmd_extract(a)
    if a.cmd in ("refs", "all"): cmd_refs(a)
    if a.cmd in ("embed", "all"): cmd_embed(a)

if __name__ == "__main__":
    main()
