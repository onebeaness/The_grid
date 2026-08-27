"""records.jsonl의 각 항목에 대해 원문을 확보한다.
우선순위: arXiv PDF > Unpaywall OA PDF > 레코드의 oa_url > 초록만.
차단된 것은 사유를 manifest에 남긴다."""
import json, os, re, sys, time, urllib.parse, urllib.request, urllib.error, argparse
import sources as S

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDS = os.path.join(HERE, "records.jsonl")
MANIFEST = os.path.join(HERE, "manifest.jsonl")
PDFDIR = os.path.join(HERE, "pdf")
ABSDIR = os.path.join(HERE, "abstracts")
DISK_GUARD_BYTES = 8 * 1024 ** 3     # 총 8GB 넘으면 PDF 수집 중단, 초록만

BLOCK_SIGNS = [
    (re.compile(r"Just a moment|cf-browser-verification|challenge-platform", re.I), "cloudflare_challenge"),
    (re.compile(r"dl\.acm\.org", re.I), "acm_dl_block"),
    (re.compile(r"<html", re.I), "html_not_pdf"),
]

def safe_name(key):
    return re.sub(r"[^A-Za-z0-9._-]", "_", key)[:150]

def dirsize(p):
    t = 0
    for root, _, fs in os.walk(p):
        for f in fs:
            try: t += os.path.getsize(os.path.join(root, f))
            except OSError: pass
    return t

def try_pdf(url, dest, timeout=90):
    """(bytes_written, error_reason)"""
    host = urllib.parse.urlparse(url).netloc
    S._throttle(host)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122 Safari/537.36",
            "Accept": "application/pdf,*/*"})
        r = urllib.request.urlopen(req, timeout=timeout)
        data = r.read()
    except urllib.error.HTTPError as e:
        return None, "http_%d" % e.code
    except Exception as e:
        return None, "neterr_" + type(e).__name__
    if data[:5].startswith(b"%PDF"):
        if len(data) < 8000: return None, "pdf_too_small_%d" % len(data)
        open(dest, "wb").write(data)
        return len(data), None
    head = data[:4000].decode("utf-8", "replace")
    for rx, tag in BLOCK_SIGNS:
        if rx.search(head) or rx.search(url): return None, tag
    return None, "not_pdf_%d_bytes" % len(data)

def candidates(r):
    """(라벨, URL) 순서대로 시도한다."""
    out = []
    if r.get("arxiv_id"):
        aid = r["arxiv_id"].split("v")[0]
        out.append(("arxiv", "https://arxiv.org/pdf/" + aid))
    up = r.get("_unpaywall") or {}
    if up.get("oa_pdf"): out.append(("unpaywall_" + str(up.get("oa_status")), up["oa_pdf"]))
    if r.get("oa_url") and r["oa_url"] not in [u for _, u in out]:
        out.append(("record_oa_url", r["oa_url"]))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-year", type=int, default=0)
    ap.add_argument("--target", type=int, default=0,
                    help="원문 시도 총량. 계열 라운드로빈으로 배분한다")
    args = ap.parse_args()
    os.makedirs(PDFDIR, exist_ok=True); os.makedirs(ABSDIR, exist_ok=True)

    done = {}
    if os.path.exists(MANIFEST):
        for line in open(MANIFEST, encoding="utf-8"):
            try: o = json.loads(line)
            except Exception: continue
            done[o["key"]] = o
    S.log("[fetch] manifest 기존 %d건" % len(done))

    recs = []
    for line in open(RECORDS, encoding="utf-8"):
        try: r = json.loads(line)
        except Exception: continue
        if r["key"] in done: continue
        if r.get("junk"): continue          # 비논문 항목은 원문을 받지 않는다
        if r.get("rep") is False: continue  # 근접중복 비대표는 건너뛴다
        if args.min_year and (r.get("year") or 0) < args.min_year: continue
        recs.append(r)
    # 계열 라운드로빈. 계열 안에서는 arXiv 보유 -> 인용수 순.
    # 어느 계열도 굶지 않게 하고, 총량 상한 도달분은 skipped.jsonl에 남긴다.
    buckets = {}
    for r in recs:
        for fam in (r.get("families") or ["_none"]):
            buckets.setdefault(fam, []).append(r)
    for fam in buckets:
        buckets[fam].sort(key=lambda r: (0 if r.get("arxiv_id") else 1,
                                         -(r.get("citations") or 0)))
    ordered, taken = [], set()
    idx = {f: 0 for f in buckets}
    while True:
        progressed = False
        for fam in sorted(buckets):
            i = idx[fam]
            while i < len(buckets[fam]) and buckets[fam][i]["key"] in taken:
                i += 1
            idx[fam] = i
            if i < len(buckets[fam]):
                r = buckets[fam][i]; idx[fam] = i + 1
                taken.add(r["key"]); ordered.append(r); progressed = True
        if not progressed: break
    recs = ordered
    total_avail = len(recs)
    cap = args.target or args.limit or 0
    skipped = []
    if cap and len(recs) > cap:
        skipped = recs[cap:]; recs = recs[:cap]
    if skipped:
        with open(os.path.join(HERE, "skipped_fetch.jsonl"), "w", encoding="utf-8") as sf:
            for r in skipped:
                sf.write(json.dumps({"key": r["key"], "title": r.get("title"),
                                     "families": r.get("families"),
                                     "citations": r.get("citations"),
                                     "reason": "원문 시도 총량 상한(%d) 초과. 메타데이터는 보유"
                                               % cap}, ensure_ascii=False) + "\n")
    S.log("[fetch] 대상 %d건 중 %d건 시도, %d건은 상한 초과로 메타데이터만 보유"
          % (total_avail, len(recs), len(skipped)))

    mf = open(MANIFEST, "a", encoding="utf-8")
    used = dirsize(PDFDIR)
    n_pdf = n_abs = n_none = 0
    t0 = time.time()

    for i, r in enumerate(recs):
        key = r["key"]; name = safe_name(key)
        entry = {"key": key, "doi": r.get("doi"), "arxiv_id": r.get("arxiv_id"),
                 "title": r.get("title"), "year": r.get("year"), "venue": r.get("venue"),
                 "families": r.get("families"), "citations": r.get("citations"),
                 "status": None, "pdf": None, "abstract_file": None,
                 "oa": None, "attempts": [], "blocked_reason": None,
                 "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

        # Unpaywall로 OA 경로 조회
        if r.get("doi"):
            up = S.unpaywall(r["doi"])
            if up:
                r["_unpaywall"] = up
                entry["oa"] = {"is_oa": up["is_oa"], "status": up["oa_status"],
                               "host": up["host_type"], "license": up["license"]}

        guard_hit = used >= DISK_GUARD_BYTES
        if not guard_hit:
            for label, url in candidates(r):
                n, err = try_pdf(url, os.path.join(PDFDIR, name + ".pdf"))
                entry["attempts"].append({"via": label, "url": url,
                                          "ok": bool(n), "error": err, "bytes": n})
                if n:
                    entry["status"] = "pdf"; entry["pdf"] = "pdf/" + name + ".pdf"
                    used += n; n_pdf += 1
                    break
        else:
            entry["attempts"].append({"via": "disk_guard", "ok": False,
                                      "error": "총 %dGB 상한 도달" % (DISK_GUARD_BYTES // 1024 ** 3)})

        if entry["status"] != "pdf":
            reasons = [a.get("error") for a in entry["attempts"] if a.get("error")]
            entry["blocked_reason"] = (reasons[0] if reasons else
                                       ("no_oa_location" if not entry["attempts"] else None))
            ab = r.get("abstract")
            if not ab and r.get("doi"):
                ab = S.pubmed_abstract_by_doi(r["doi"], expect_title=r.get("title"))
                if ab: r["abstract_source"] = "pubmed(DOI검증)"
            if ab:
                p = os.path.join(ABSDIR, name + ".txt")
                with open(p, "w", encoding="utf-8") as f:
                    f.write((r.get("title") or "") + "\n\n" + ab + "\n")
                entry["status"] = "abstract"; entry["abstract_file"] = "abstracts/" + name + ".txt"
                entry["abstract_source"] = r.get("abstract_source")
                n_abs += 1
            else:
                entry["status"] = "none"; n_none += 1

        mf.write(json.dumps(entry, ensure_ascii=False) + "\n"); mf.flush()
        if (i + 1) % 50 == 0:
            S.log("  %d/%d  pdf %d / abs %d / none %d  디스크 %.1fGB  %.0f분"
                  % (i + 1, len(recs), n_pdf, n_abs, n_none, used / 1024 ** 3,
                     (time.time() - t0) / 60))
    mf.close()
    S.log("[fetch] 완료. pdf %d / abstract %d / none %d. 디스크 %.1fGB"
          % (n_pdf, n_abs, n_none, used / 1024 ** 3))

if __name__ == "__main__":
    main()
