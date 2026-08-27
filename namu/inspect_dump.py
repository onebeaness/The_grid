#!/usr/bin/env python3
"""나무위키 덤프 구조 분석. 읽기 전용 스트리밍.

원본은 'rb'로만 연다. rename/chmod/삭제/덮어쓰기를 하지 않는다.
2GB급을 전제로 전체를 메모리에 올리지 않고 청크로 훑는다.

  python3 inspect_dump.py <경로> --snapshot 2026-08-01 --sample 30
"""
import argparse, hashlib, io, json, os, re, sys, time, collections

CHUNK = 1 << 20   # 1MB

MAGIC = [
    (b"\x1f\x8b",                 "gzip"),
    (b"\xfd7zXZ\x00",             "xz"),
    (b"\x28\xb5\x2f\xfd",         "zstd"),
    (b"7z\xbc\xaf\x27\x1c",       "7z"),
    (b"BZh",                      "bzip2"),
    (b"PK\x03\x04",               "zip"),
    (b"SQLite format 3\x00",      "sqlite3"),
]

def detect_compression(head, path):
    for sig, name in MAGIC:
        if head.startswith(sig): return name
    if len(head) > 262 and head[257:262] == b"ustar": return "tar"
    return None

def opener(path, comp):
    """항상 읽기 전용. 압축이면 스트리밍 디코더를 씌운다."""
    if comp is None:
        return open(path, "rb")
    if comp == "gzip":
        import gzip; return gzip.open(path, "rb")
    if comp == "xz":
        import lzma; return lzma.open(path, "rb")
    if comp == "bzip2":
        import bz2; return bz2.open(path, "rb")
    if comp == "zstd":
        try:
            import zstandard as zstd
        except ImportError:
            raise SystemExit("zstd 덤프입니다. `pip install zstandard` 후 다시 실행하세요.")
        return zstd.ZstdDecompressor().stream_reader(open(path, "rb"))
    raise SystemExit("압축 형식 %s 는 스트리밍 미지원입니다. 먼저 풀어 주세요." % comp)

def sniff_encoding(b):
    if b.startswith(b"\xef\xbb\xbf"): return "utf-8-sig", "BOM"
    if b.startswith(b"\xff\xfe"): return "utf-16-le", "BOM"
    if b.startswith(b"\xfe\xff"): return "utf-16-be", "BOM"
    try:
        b.decode("utf-8"); return "utf-8", "엄격 디코딩 통과"
    except UnicodeDecodeError as e:
        # 청크 경계에서 잘린 문자일 수 있으니 끝을 조금 잘라 재시도
        for cut in range(1, 5):
            try:
                b[:-cut].decode("utf-8"); return "utf-8", "엄격 통과(경계 %d바이트 절단)" % cut
            except UnicodeDecodeError: pass
        return "unknown", "utf-8 실패: %s" % str(e)[:80]

def detect_container(head_text):
    s = head_text.lstrip()
    if s.startswith("["): return "json_array"
    if s.startswith("{"):
        first = s.split("\n", 1)[0]
        try:
            json.loads(first); return "jsonl"
        except Exception: return "json_object_or_jsonl"
    if s.startswith("<?xml") or s.startswith("<mediawiki") or s.startswith("<"): return "xml"
    if re.match(r"(?is)^\s*(--|/\*|insert\s+into|create\s+table|drop\s+table)", s): return "sql"
    return "unknown"

class JSONObjectStream:
    """최상위 배열/JSONL에서 객체를 하나씩 떼어낸다. 전체를 메모리에 올리지 않는다."""
    def __init__(self, fh, encoding="utf-8"):
        self.fh = fh; self.enc = encoding
        self.buf = ""; self.eof = False

    def _fill(self):
        if self.eof: return False
        raw = self.fh.read(CHUNK)
        if not raw: self.eof = True; return False
        self.buf += raw.decode(self.enc, "replace")
        return True

    def __iter__(self):
        depth = 0; start = None; instr = False; esc = False
        i = 0
        while True:
            while i >= len(self.buf):
                if start is not None and start > 0:
                    self.buf = self.buf[start:]; i -= start; start = 0
                elif start is None and len(self.buf) > CHUNK * 4:
                    self.buf = self.buf[i:]; i = 0
                if not self._fill(): return
            ch = self.buf[i]
            if instr:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': instr = False
            else:
                if ch == '"': instr = True
                elif ch == "{":
                    if depth == 0: start = i
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and start is not None:
                        chunk = self.buf[start:i + 1]
                        try: yield json.loads(chunk)
                        except Exception: pass
                        self.buf = self.buf[i + 1:]; i = -1; start = None
            i += 1

def sha256_file(path, limit=None):
    h = hashlib.sha256(); n = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b: break
            h.update(b); n += len(b)
            if limit and n >= limit: break
    return h.hexdigest(), n

REDIRECT_RX = [
    ("#redirect",   re.compile(r"^\s*#redirect\s+", re.I)),
    ("#넘겨주기",    re.compile(r"^\s*#넘겨주기\s+")),
    ("#redirect(대괄호)", re.compile(r"^\s*#redirect\s*\[\[", re.I)),
]
CAT_RX = [
    ("[[분류:...]]",   re.compile(r"\[\[분류:([^\]|]+)")),
    ("[[Category:...]]", re.compile(r"\[\[Category:([^\]|]+)", re.I)),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--snapshot", default=None, help="스냅샷 날짜 YYYY-MM-DD")
    ap.add_argument("--sample", type=int, default=30, help="필드 조사용 표본 문서 수")
    ap.add_argument("--count", action="store_true", help="전체 문서 수를 끝까지 세기")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args()

    if not os.path.isfile(a.path):
        raise SystemExit("파일이 아닙니다: %s" % a.path)
    st = os.stat(a.path)
    t0 = time.time()

    with open(a.path, "rb") as f:
        head = f.read(1 << 20)

    comp = detect_compression(head, a.path)
    enc, enc_note = sniff_encoding(head if comp is None else head[:0] or b"")
    rep = {
        "snapshot_date": a.snapshot,
        "inspected_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file": {"path": os.path.abspath(a.path), "size_bytes": st.st_size,
                 "size_gib": round(st.st_size / 1024 ** 3, 3),
                 "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
                 "mode": oct(st.st_mode)},
        "compression": comp,
    }

    fh = opener(a.path, comp)
    try:
        head2 = fh.read(1 << 20)
    finally:
        if comp is not None: fh.close()
    if comp is not None:
        enc, enc_note = sniff_encoding(head2)
    rep["encoding"] = {"detected": enc, "note": enc_note}
    head_text = head2.decode(enc if enc != "unknown" else "utf-8", "replace")
    rep["container"] = detect_container(head_text)
    rep["head_preview"] = head_text[:1200]

    # 표본 문서 조사
    fh = opener(a.path, comp)
    fields = collections.Counter()
    field_types = collections.defaultdict(collections.Counter)
    samples = []
    redirect_hits = collections.Counter()
    cat_hits = collections.Counter()
    ns_hits = collections.Counter()
    n = 0
    try:
        if rep["container"] in ("json_array", "jsonl", "json_object_or_jsonl"):
            for obj in JSONObjectStream(fh, enc if enc != "unknown" else "utf-8"):
                n += 1
                if n <= a.sample:
                    for k, v in obj.items():
                        fields[k] += 1
                        field_types[k][type(v).__name__] += 1
                    samples.append({k: (v[:400] + "..." if isinstance(v, str) and len(v) > 400 else v)
                                    for k, v in obj.items()})
                txt = ""
                for key in ("text", "content", "body", "namumark", "wikitext"):
                    if isinstance(obj.get(key), str): txt = obj[key]; break
                if txt:
                    for name, rx in REDIRECT_RX:
                        if rx.search(txt[:200]): redirect_hits[name] += 1
                    for name, rx in CAT_RX:
                        c = len(rx.findall(txt))
                        if c: cat_hits[name] += c
                if isinstance(obj.get("namespace"), (str, int)):
                    ns_hits[str(obj["namespace"])] += 1
                if not a.count and n >= max(a.sample, 20000): break
        else:
            rep["note"] = "컨테이너 %s 는 아직 표본 조사 미구현. head_preview로 판단 필요." % rep["container"]
    finally:
        try: fh.close()
        except Exception: pass

    rep["documents_scanned"] = n
    rep["documents_total"] = n if a.count else None
    rep["scan_complete"] = bool(a.count)
    rep["fields"] = {k: {"count": v, "types": dict(field_types[k])} for k, v in fields.most_common()}
    rep["redirect_notation"] = dict(redirect_hits)
    rep["category_notation"] = dict(cat_hits)
    rep["namespaces"] = dict(ns_hits.most_common(30))
    rep["elapsed_sec"] = round(time.time() - t0, 1)

    os.makedirs(a.out, exist_ok=True)
    tag = a.snapshot or time.strftime("%Y%m%d", time.gmtime())
    with open(os.path.join(a.out, "dump_structure_%s.json" % tag), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "dump_samples_%s.json" % tag), "w", encoding="utf-8") as f:
        json.dump({"snapshot_date": a.snapshot, "samples": samples}, f, ensure_ascii=False, indent=1)

    # 콘솔 요약
    print("=" * 74)
    print("덤프 구조  스냅샷 %s" % (a.snapshot or "(미지정)"))
    print("=" * 74)
    print("경로        %s" % rep["file"]["path"])
    print("크기        %.2f GiB (%d bytes)" % (rep["file"]["size_gib"], rep["file"]["size_bytes"]))
    print("mtime       %s" % rep["file"]["mtime_utc"])
    print("압축        %s" % (comp or "없음(평문)"))
    print("인코딩      %s (%s)" % (enc, enc_note))
    print("컨테이너    %s" % rep["container"])
    print("스캔 문서   %d%s" % (n, "" if a.count else " (부분. --count로 전수)"))
    print("\n[필드 구성] 표본 %d건" % min(n, a.sample))
    for k, v in fields.most_common():
        print("  %-16s %4d건  타입 %s" % (k, v, dict(field_types[k])))
    print("\n[리다이렉트 표기]")
    print("  " + (str(dict(redirect_hits)) if redirect_hits else "관측 없음"))
    print("\n[분류 표기]")
    print("  " + (str(dict(cat_hits)) if cat_hits else "관측 없음"))
    if ns_hits:
        print("\n[네임스페이스 상위]")
        for k, v in ns_hits.most_common(12): print("  %-28s %d" % (k, v))
    print("\n소요 %.1fs. 보고서: %s/dump_structure_%s.json" % (rep["elapsed_sec"], a.out, tag))

if __name__ == "__main__":
    main()
