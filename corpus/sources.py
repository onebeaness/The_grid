"""소스 어댑터. 레이트리밋, 백오프, 예산 소진 감지, DOI 검증을 여기서 처리한다."""
import json, re, time, html, urllib.parse, urllib.request, urllib.error, difflib, sys, threading

UA = {"User-Agent": "the-grid-corpus/1.0 (academic literature collection)"}
UNPAYWALL_EMAIL = "unpaywall@impactstory.org"   # Unpaywall 문서상의 공개 테스트 주소

# 호스트별 최소 간격(초)
RATE = {
    "export.arxiv.org": 3.0,
    "api.crossref.org": 1.0,
    "api.openalex.org": 1.0,
    "api.semanticscholar.org": 4.0,
    "dblp.org": 2.0,
    "eutils.ncbi.nlm.nih.gov": 0.4,
    "api.unpaywall.org": 0.25,
    "www.openproceedings.org": 2.0,
    "openproceedings.org": 2.0,
}
_last = {}
_lock = threading.Lock()

# 소스 상태. 예산 소진이나 지속 장애 시 여기서 꺼진다.
STATE = {
    "openalex": {"ok": True, "reason": None},
    "semanticscholar": {"ok": True, "reason": None, "consecutive_429": 0},
    "dblp": {"ok": True, "reason": None, "fail": 0},
    "openproceedings": {"ok": True, "reason": None, "fail": 0},
}

def log(msg):
    sys.stderr.write(msg + "\n"); sys.stderr.flush()

def _throttle(host):
    with _lock:
        gap = RATE.get(host, 1.0)
        now = time.time()
        wait = _last.get(host, 0) + gap - now
        if wait > 0: time.sleep(wait)
        _last[host] = time.time()

def get(url, tries=5, timeout=60, accept_json=False):
    """(body, status). 429/5xx는 Retry-After를 존중하며 지수 백오프."""
    host = urllib.parse.urlparse(url).netloc
    headers = dict(UA)
    if accept_json: headers["Accept"] = "application/json"
    delay = 2.0
    for attempt in range(tries):
        _throttle(host)
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)
            return r.read().decode("utf-8", "replace"), 200
        except urllib.error.HTTPError as e:
            body = ""
            try: body = e.read().decode("utf-8", "replace")[:400]
            except Exception: pass
            if e.code == 429:
                ra = e.headers.get("Retry-After")
                # OpenAlex 예산 소진은 재시도해도 소용없다. 즉시 끈다.
                if "openalex" in host and "budget" in body.lower():
                    STATE["openalex"].update(ok=False, reason="일일 예산 소진: " + body[:120])
                    return None, 429
                if "semanticscholar" in host:
                    STATE["semanticscholar"]["consecutive_429"] += 1
                    if STATE["semanticscholar"]["consecutive_429"] >= 12:
                        STATE["semanticscholar"].update(ok=False,
                            reason="429 연속 12회. 무인증 공용 풀 포화. 전용 패스에서 재시도")
                        return None, 429
                try: sleep = float(ra) if ra else delay
                except Exception: sleep = delay
                time.sleep(min(sleep, 90)); delay = min(delay * 2, 90); continue
            if e.code in (500, 502, 503, 504):
                if "dblp" in host:
                    STATE["dblp"]["fail"] += 1
                    if STATE["dblp"]["fail"] >= 6:
                        STATE["dblp"].update(ok=False, reason="5xx 연속 6회. 서버 이용 불가")
                        return None, e.code
                time.sleep(delay); delay = min(delay * 2, 60); continue
            return None, e.code
        except Exception:
            time.sleep(delay); delay = min(delay * 2, 60)
    return None, 0

def jget(url, **kw):
    b, code = get(url, accept_json=True, **kw)
    if not b: return None, code
    try: return json.loads(b), code
    except Exception: return None, code

# ---------- 제목 정규화와 유사도 ----------
_STOP = {"a","an","the","of","for","and","on","in","to","with","via","using","towards","toward"}

def norm_title(t):
    if not t: return ""
    t = html.unescape(t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    toks = [w for w in t.split() if w and w not in _STOP]
    return " ".join(toks)

def title_sim(a, b):
    return difflib.SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()

def clean_abs(a):
    if not a: return None
    a = re.sub(r"<[^>]+>", " ", html.unescape(a))
    a = re.sub(r"\s+", " ", a).strip()
    return a or None

def rec(**kw):
    r = {"doi": None, "arxiv_id": None, "title": None, "authors": [], "year": None,
         "venue": None, "citations": None, "abstract": None, "abstract_source": None,
         "pmid": None, "s2_id": None, "openalex_id": None, "dblp_key": None,
         "oa_url": None, "sources": [], "families": [], "queries": [], "round": 0}
    r.update(kw)
    if r.get("doi"): r["doi"] = r["doi"].lower().strip()
    r["norm_title"] = norm_title(r.get("title"))
    return r

# ---------- arXiv ----------
def arxiv_search(query, limit=200):
    out = []
    step = min(100, limit)
    for start in range(0, limit, step):
        u = ("https://export.arxiv.org/api/query?search_query=all:%22"
             + urllib.parse.quote(query) + "%%22&start=%d&max_results=%d" % (start, step)
             + "&sortBy=relevance")
        b, code = get(u)
        if not b: break
        entries = re.findall(r"<entry>(.*?)</entry>", b, re.S)
        if not entries: break
        for e in entries:
            t = re.search(r"<title>(.*?)</title>", e, re.S)
            i = re.search(r"<id>(.*?)</id>", e, re.S)
            s = re.search(r"<summary>(.*?)</summary>", e, re.S)
            p = re.search(r"<published>(.*?)</published>", e, re.S)
            d = re.search(r'<arxiv:doi[^>]*>(.*?)</arxiv:doi>', e, re.S)
            j = re.search(r'<arxiv:journal_ref[^>]*>(.*?)</arxiv:journal_ref>', e, re.S)
            if not t or not i: continue
            aid = i.group(1).strip().split("/abs/")[-1]
            out.append(rec(
                arxiv_id=aid,
                doi=d.group(1).strip() if d else None,
                title=re.sub(r"\s+", " ", html.unescape(t.group(1))).strip(),
                authors=[re.sub(r"\s+", " ", html.unescape(x)).strip()
                         for x in re.findall(r"<name>(.*?)</name>", e, re.S)],
                year=int(p.group(1)[:4]) if p else None,
                venue=re.sub(r"\s+", " ", j.group(1)).strip() if j else "arXiv",
                abstract=clean_abs(s.group(1)) if s else None,
                abstract_source="arxiv",
                sources=["arxiv"]))
        if len(entries) < step: break
    return out

# ---------- Crossref ----------
def crossref_search(query, limit=200):
    """커서 페이징은 관련도 정렬을 끄고 DOI 순으로 훑는다. offset 페이징을 쓴다."""
    out = []
    off = 0
    while off < limit:
        rows = min(100, limit - off)
        u = ("https://api.crossref.org/works?query.bibliographic="
             + urllib.parse.quote(query) + "&rows=%d&offset=%d" % (rows, off)
             + "&select=DOI,title,author,issued,container-title,is-referenced-by-count,abstract,type")
        d, code = jget(u)
        if not d: break
        msg = d.get("message", {})
        items = msg.get("items", [])
        if not items: break
        for it in items:
            ti = (it.get("title") or [""])[0]
            if not ti: continue
            yr = None
            try: yr = int(it["issued"]["date-parts"][0][0])
            except Exception: pass
            au = []
            for a in (it.get("author") or [])[:30]:
                nm = " ".join(x for x in [a.get("given"), a.get("family")] if x)
                if nm: au.append(nm)
            out.append(rec(
                doi=it.get("DOI"), title=ti, authors=au, year=yr,
                venue=(it.get("container-title") or [None])[0],
                citations=it.get("is-referenced-by-count"),
                abstract=clean_abs(it.get("abstract")),
                abstract_source="crossref" if it.get("abstract") else None,
                sources=["crossref"]))
        off += len(items)
        if len(items) < rows or off >= 1000: break   # 관련도는 1000건 이후 무의미
    return out

# ---------- OpenAlex ----------
def openalex_search(query, limit=200):
    if not STATE["openalex"]["ok"]: return []
    out = []
    page = 1
    while len(out) < limit:
        u = ("https://api.openalex.org/works?search=" + urllib.parse.quote(query)
             + "&per-page=%d&page=%d" % (min(100, limit - len(out)), page))
        d, code = jget(u)
        if not STATE["openalex"]["ok"]: break
        if not d or "results" not in d: break
        res = d["results"]
        if not res: break
        for it in res:
            inv = it.get("abstract_inverted_index")
            ab = None
            if inv:
                pos = {}
                for w, ids in inv.items():
                    for i in ids: pos[i] = w
                ab = " ".join(pos[k] for k in sorted(pos))
            host = (it.get("primary_location") or {}).get("source") or {}
            out.append(rec(
                doi=(it.get("doi") or "").replace("https://doi.org/", "") or None,
                openalex_id=it.get("id"), title=it.get("title"),
                authors=[(a.get("author") or {}).get("display_name")
                         for a in (it.get("authorships") or [])[:30] if a.get("author")],
                year=it.get("publication_year"), venue=host.get("display_name"),
                citations=it.get("cited_by_count"), abstract=clean_abs(ab),
                abstract_source="openalex" if ab else None,
                oa_url=(it.get("open_access") or {}).get("oa_url"),
                sources=["openalex"]))
        page += 1
        if len(res) < 100: break
    return out

# ---------- Semantic Scholar ----------
S2_FIELDS = "title,year,venue,abstract,externalIds,citationCount,authors,openAccessPdf,publicationVenue"

def s2_search(query, limit=200):
    if not STATE["semanticscholar"]["ok"]: return []
    out = []
    offset = 0
    while len(out) < limit:
        u = ("https://api.semanticscholar.org/graph/v1/paper/search?query="
             + urllib.parse.quote(query) + "&limit=%d&offset=%d&fields=%s"
             % (min(100, limit - len(out)), offset, S2_FIELDS))
        d, code = jget(u)
        if not STATE["semanticscholar"]["ok"]: break
        if not d: break
        STATE["semanticscholar"]["consecutive_429"] = 0
        data = d.get("data") or []
        if not data: break
        for it in data:
            ex = it.get("externalIds") or {}
            out.append(_s2_rec(it, ex))
        offset += len(data)
        if offset >= (d.get("total") or 0) or len(data) < 100: break
        if offset >= 1000: break   # S2 search offset 상한
    return out

def _s2_rec(it, ex=None):
    ex = ex if ex is not None else (it.get("externalIds") or {})
    pv = it.get("publicationVenue") or {}
    return rec(
        doi=ex.get("DOI"), arxiv_id=ex.get("ArXiv"), pmid=ex.get("PubMed"),
        s2_id=it.get("paperId"), title=it.get("title"),
        authors=[a.get("name") for a in (it.get("authors") or [])[:30] if a.get("name")],
        year=it.get("year"), venue=it.get("venue") or pv.get("name"),
        citations=it.get("citationCount"), abstract=clean_abs(it.get("abstract")),
        abstract_source="semanticscholar" if it.get("abstract") else None,
        oa_url=(it.get("openAccessPdf") or {}).get("url"),
        sources=["semanticscholar"])

def s2_refs_cites(s2_id_or_doi, kind="references", limit=500):
    """kind: references | citations"""
    if not STATE["semanticscholar"]["ok"]: return []
    out = []
    offset = 0
    key = "citedPaper" if kind == "references" else "citingPaper"
    while len(out) < limit:
        u = ("https://api.semanticscholar.org/graph/v1/paper/" + urllib.parse.quote(s2_id_or_doi)
             + "/" + kind + "?limit=%d&offset=%d&fields=%s" % (min(100, limit - len(out)), offset, S2_FIELDS))
        d, code = jget(u)
        if not STATE["semanticscholar"]["ok"] or not d: break
        STATE["semanticscholar"]["consecutive_429"] = 0
        data = d.get("data") or []
        if not data: break
        for it in data:
            p = it.get(key)
            if p and p.get("title"): out.append(_s2_rec(p))
        offset += len(data)
        if len(data) < 100: break
    return out

# ---------- DBLP ----------
def dblp_search(query, limit=200):
    if not STATE["dblp"]["ok"]: return []
    out = []
    f = 0
    while len(out) < limit:
        u = ("https://dblp.org/search/publ/api?q=" + urllib.parse.quote(query)
             + "&format=json&h=%d&f=%d" % (min(100, limit - len(out)), f))
        d, code = jget(u)
        if not STATE["dblp"]["ok"] or not d: break
        STATE["dblp"]["fail"] = 0
        hits = ((d.get("result") or {}).get("hits") or {})
        arr = hits.get("hit") or []
        if not arr: break
        for h in arr:
            i = h.get("info") or {}
            au = i.get("authors") or {}
            a = au.get("author") or []
            if isinstance(a, dict): a = [a]
            names = [x.get("text") if isinstance(x, dict) else str(x) for x in a]
            yr = None
            try: yr = int(i.get("year"))
            except Exception: pass
            ven = i.get("venue")
            if isinstance(ven, (list, tuple)): ven = ", ".join(str(v) for v in ven)
            ti = i.get("title")
            if isinstance(ti, (list, tuple)): ti = " ".join(str(v) for v in ti)
            out.append(rec(
                doi=i.get("doi"), dblp_key=i.get("key"), title=ti,
                authors=[n for n in names if n], year=yr, venue=ven,
                sources=["dblp"]))
        f += len(arr)
        total = int(hits.get("@total", 0) or 0)
        if f >= total or len(arr) < 100: break
    return out

# ---------- PubMed (DOI 대조 검증 필수) ----------
def pubmed_search(query, limit=200):
    out = []
    u = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term="
         + urllib.parse.quote(query) + "&retmax=%d&retmode=json&sort=relevance" % limit)
    d, code = jget(u)
    if not d: return out
    ids = ((d.get("esearchresult") or {}).get("idlist") or [])
    for i in range(0, len(ids), 100):
        chunk = ids[i:i+100]
        b, code = get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id="
                      + ",".join(chunk) + "&rettype=abstract&retmode=xml")
        if not b: continue
        for art in re.findall(r"<PubmedArticle>(.*?)</PubmedArticle>", b, re.S):
            ti = re.search(r"<ArticleTitle[^>]*>(.*?)</ArticleTitle>", art, re.S)
            if not ti: continue
            doi = re.search(r'<ArticleId IdType="doi">(.*?)</ArticleId>', art, re.S)
            pmid = re.search(r"<PMID[^>]*>(\d+)</PMID>", art)
            jr = re.search(r"<Title>(.*?)</Title>", art, re.S)
            yr = re.search(r"<PubDate>.*?<Year>(\d{4})</Year>", art, re.S) or re.search(r"<Year>(\d{4})</Year>", art)
            parts = re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", art, re.S)
            names = []
            for a in re.findall(r"<Author[^>]*>(.*?)</Author>", art, re.S)[:30]:
                ln = re.search(r"<LastName>(.*?)</LastName>", a)
                fn = re.search(r"<ForeName>(.*?)</ForeName>", a)
                if ln: names.append(((fn.group(1) + " ") if fn else "") + ln.group(1))
            out.append(rec(
                doi=doi.group(1) if doi else None,
                pmid=pmid.group(1) if pmid else None,
                title=clean_abs(ti.group(1)),
                authors=names, year=int(yr.group(1)) if yr else None,
                venue=clean_abs(jr.group(1)) if jr else None,
                abstract=clean_abs(" ".join(parts)) if parts else None,
                abstract_source="pubmed" if parts else None,
                sources=["pubmed"]))
    return out

def pubmed_abstract_by_doi(doi, expect_title=None):
    """DOI로 조회하되 반환 레코드의 DOI가 실제 일치할 때만 초록을 준다.
    일치해도 expect_title이 주어지면 제목 유사도 0.85 미만은 버린다."""
    u = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=%22"
         + urllib.parse.quote(doi) + "%22[AID]&retmode=json")
    d, code = jget(u)
    if not d: return None
    ids = ((d.get("esearchresult") or {}).get("idlist") or [])
    if not ids: return None
    b, code = get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id="
                  + ids[0] + "&rettype=abstract&retmode=xml")
    if not b: return None
    got = re.findall(r'<ArticleId IdType="doi">(.*?)</ArticleId>', b)
    if not any(g.lower() == doi.lower() for g in got): return None
    if expect_title:
        ti = re.search(r"<ArticleTitle[^>]*>(.*?)</ArticleTitle>", b, re.S)
        if ti and title_sim(clean_abs(ti.group(1)), expect_title) < 0.85: return None
    parts = re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", b, re.S)
    return clean_abs(" ".join(parts)) if parts else None

# ---------- OpenProceedings (EDBT/ICDT) ----------
def openproceedings_search(query, limit=200):
    """볼륨 색인을 받아 제목으로 필터링한다. 검색 API가 없어 색인 스크레이프."""
    if not STATE["openproceedings"]["ok"]: return []
    global _OP_CACHE
    if _OP_CACHE is None:
        _OP_CACHE = _openproceedings_index()
    q = set(norm_title(query).split())
    if not q: return []
    out = []
    for r in _OP_CACHE:
        toks = set(r["norm_title"].split())
        if len(q & toks) >= max(2, len(q) - 1):
            rr = dict(r); rr["sources"] = ["openproceedings"]; out.append(rr)
        if len(out) >= limit: break
    return out

_OP_CACHE = None

def _openproceedings_index():
    recs = []
    for year in range(2014, 2027):
        for conf in ("edbt", "icdt"):
            b, code = get("https://openproceedings.org/html/pages/%d_%s" % (year, conf))
            if not b: continue
            block = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", b, flags=re.S)
            for m in re.finditer(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', block, re.S):
                url, txt = m.group(1), clean_abs(m.group(2))
                if not txt or len(txt) < 15: continue
                if not url.startswith("http"):
                    url = "https://openproceedings.org/" + url.lstrip("/")
                recs.append(rec(title=txt, year=year, venue=conf.upper() + " " + str(year),
                                oa_url=url, sources=["openproceedings"]))
    STATE["openproceedings"]["ok"] = bool(recs)
    if not recs: STATE["openproceedings"]["reason"] = "볼륨 색인 파싱 결과 0건"
    log("[openproceedings] 색인 %d건" % len(recs))
    return recs

# ---------- Unpaywall ----------
def unpaywall(doi):
    d, code = jget("https://api.unpaywall.org/v2/" + urllib.parse.quote(doi)
                   + "?email=" + UNPAYWALL_EMAIL)
    if not d: return None
    loc = d.get("best_oa_location") or {}
    return {"is_oa": bool(d.get("is_oa")), "oa_status": d.get("oa_status"),
            "oa_pdf": loc.get("url_for_pdf") or loc.get("url"),
            "host_type": loc.get("host_type"), "license": loc.get("license")}

SEARCHERS = {
    "arxiv": arxiv_search, "crossref": crossref_search, "openalex": openalex_search,
    "semanticscholar": s2_search, "dblp": dblp_search, "pubmed": pubmed_search,
    "openproceedings": openproceedings_search,
}


# ---------- 관련성 게이트 ----------
def relevant(query, r, min_ratio=0.6):
    """키워드 검색은 느슨하게 매칭된다. 질의어 토큰이 실제로 본문 메타에
    나타나는지 확인해 무관한 레코드를 걷어낸다."""
    q = [w for w in norm_title(query).split()]
    if not q: return True
    def _s(v):
        if v is None: return ""
        if isinstance(v, (list, tuple)): return " ".join(_s(i) for i in v)
        return v if isinstance(v, str) else str(v)
    text = norm_title(" ".join(x for x in [_s(r.get("title")), _s(r.get("venue")),
                                           _s(r.get("abstract"))[:3000]] if x))
    toks = set(text.split())
    hit = sum(1 for w in q if w in toks)
    if len(q) == 1: return hit >= 1
    if len(q) == 2: return hit >= 2
    import math
    return hit >= max(2, math.ceil(min_ratio * len(q)))
