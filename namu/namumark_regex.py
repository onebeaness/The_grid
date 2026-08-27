#!/usr/bin/env python3
"""정규식 기준선 나무마크 파서.

외부 파서 없이 어디까지 되는지 재기 위한 기준선.
각주, 표, 분류, 링크를 본문에서 분리해 별도로 반환.

반환 dict:
  redirect      리다이렉트 대상 또는 None
  plain         평문
  sections      [{level, number, title, text}]  계층은 number로 표현
  categories    [분류명]
  links         [{target, display, anchor, external}]
  footnotes     [{mark, text}]
  tables        [{raw, rows}]
  stripped      제거한 구성요소 카운터
"""
import re, collections

# ---------- 리다이렉트 ----------
RX_REDIRECT = re.compile(r"^\s*#\s*(?:redirect|넘겨주기)\s*\[\[([^\]|#]+)", re.I)
RX_REDIRECT_BARE = re.compile(r"^\s*#\s*(?:redirect|넘겨주기)\s+([^\n\[\]]+)", re.I)

# ---------- 주석 ----------
RX_COMMENT = re.compile(r"^##[^\n]*$", re.M)

# ---------- 분류 ----------
RX_CATEGORY = re.compile(r"\[\[(?:분류|Category)\s*:\s*([^\]|]+?)\s*(?:\|[^\]]*)?\]\]", re.I)

# ---------- 절 ----------
RX_HEADING = re.compile(r"^(={1,6})(#?)\s*(.+?)\s*\2\1\s*$", re.M)

# ---------- 링크 ----------
RX_LINK = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]*?))?\]\]")

# ---------- 매크로 ----------
RX_MACRO = re.compile(r"\[(?:br|목차|tableofcontents|각주|footnote|clearfix|pagecount)\]", re.I)
RX_MACRO_ARG = re.compile(
    r"\[(?:age|dday|include|youtube|nicovideo|kakaotv|navertv|vimeo|ruby|anchor|pagecount|math|"
    r"date|datetime|목차|tableofcontents)\((?:[^()]|\([^()]*\))*\)\]", re.I)

# ---------- 장식 ----------
DECOR = [
    (re.compile(r"'''(.+?)'''", re.S), r"\1"),      # 볼드
    (re.compile(r"''(.+?)''", re.S), r"\1"),        # 이탤릭
    (re.compile(r"__(.+?)__", re.S), r"\1"),        # 밑줄
    (re.compile(r"~~(.+?)~~", re.S), r"\1"),        # 취소선
    (re.compile(r"--(.+?)--", re.S), r"\1"),        # 취소선(구)
    (re.compile(r"\^\^(.+?)\^\^", re.S), r"\1"),    # 위첨자
    (re.compile(r",,(.+?),,", re.S), r"\1"),        # 아래첨자
]
RX_HR = re.compile(r"^\s*-{4,}\s*$", re.M)
RX_LIST = re.compile(r"^(\s+)(\*|\d+\.|[aAiI]\.)\s+", re.M)
RX_QUOTE = re.compile(r"^\s*>+\s?", re.M)
RX_INDENT = re.compile(r"^ +", re.M)

def _match_braces(s, i):
    """s[i:]가 {{{ 로 시작할 때 대응하는 }}} 의 끝 인덱스를 반환. 중첩 처리."""
    depth = 0; n = len(s); j = i
    while j < n:
        if s.startswith("{{{", j): depth += 1; j += 3
        elif s.startswith("}}}", j):
            depth -= 1; j += 3
            if depth == 0: return j
        else: j += 1
    return -1

def extract_braced(text, counter):
    """{{{ }}} 블록을 제거하고 내용만 남긴다. #!html #!wiki #!folding 등은 유형별 처리."""
    out = []; i = 0
    while True:
        k = text.find("{{{", i)
        if k < 0: out.append(text[i:]); break
        out.append(text[i:k]); out.append(" ")
        e = _match_braces(text, k)
        if e < 0:
            counter["unclosed_brace"] += 1
            out.append(text[k + 3:]); break
        body = text[k + 3:e - 3]
        m = re.match(r"\s*#!(\w+)([^\n]*)\n?", body)
        if m:
            kind = m.group(1).lower(); inner = body[m.end():]
            if kind == "html":
                counter["html_block"] += 1
                inner = re.sub(r"<[^>]+>", " ", inner)
            elif kind in ("wiki", "folding"):
                counter[kind + "_block"] += 1
            elif kind in ("syntax", "code"):
                counter["code_block"] += 1; inner = " "
            else:
                counter["brace_" + kind] += 1
            out.append(inner)
        else:
            m2 = re.match(r"\s*(#[0-9a-fA-F]{3,6}|#\w+|\+[1-5]|-[1-5])\s", body)
            if m2:
                counter["styled_text"] += 1
                out.append(body[m2.end():])
            else:
                counter["literal_block"] += 1
                out.append(" " + body + " ")   # nowiki. 산문일 수 있어 보존
        i = e
    return "".join(out)

RX_FOOTNOTE_OPEN = re.compile(r"\[\*([^\s\]]*)\s*")

def extract_footnotes(text, counter):
    """[* 내용] 과 [*이름 내용] 을 본문에서 떼어낸다. 중첩 대괄호 처리."""
    notes = []; out = []; i = 0
    while True:
        m = RX_FOOTNOTE_OPEN.search(text, i)
        if not m: out.append(text[i:]); break
        out.append(text[i:m.start()])
        j = m.end(); depth = 1; n = len(text)
        while j < n and depth:
            if text[j] == "[": depth += 1
            elif text[j] == "]": depth -= 1
            j += 1
        if depth:
            counter["unclosed_footnote"] += 1
            out.append(text[m.start():]); break
        notes.append({"mark": m.group(1) or None, "text": text[m.end():j - 1].strip()})
        # 각주는 앞 단어에 붙고 뒤에 조사가 이어짐. 공백을 넣으면 원문과 달라짐.
        # 예) "각주 하나[* 내용]와" -> "각주 하나와". 다른 요소는 공백을 유지한다.
        i = j
    return "".join(out), notes

RX_TABLE_LINE = re.compile(r"^\s*\|\|.*\|\|\s*$", re.M)
RX_CELL_OPT = re.compile(r"<[^<>]*>")

def extract_tables(text, counter):
    """|| 로 시작하는 연속 행을 표로 묶어 본문에서 분리."""
    lines = text.split("\n")
    tables = []; keep = []; buf = []
    def flush():
        if not buf: return
        rows = []
        for ln in buf:
            cells = [RX_CELL_OPT.sub("", c).strip() for c in ln.strip().strip("|").split("||")]
            rows.append([c for c in cells])
        tables.append({"raw": "\n".join(buf), "rows": rows})
        counter["table"] += 1
        buf.clear()
    for ln in lines:
        if RX_TABLE_LINE.match(ln): buf.append(ln)
        else: flush(); keep.append(ln)
    flush()
    return "\n".join(keep), tables

RX_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:)\]}%’”」』])")
RX_SPACE_AFTER_OPEN = re.compile(r"([(\[{‘“「『])\s+")

def normalize(t):
    """요소 제거로 생긴 잉여 공백을 정리하되 단어는 붙이지 않는다."""
    t = RX_INDENT.sub("", t)
    t = re.sub(r"[ \t\u00a0]+", " ", t)
    t = RX_SPACE_BEFORE_PUNCT.sub(r"\1", t)
    t = RX_SPACE_AFTER_OPEN.sub(r"\1", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def parse(text, collect_links=True):
    c = collections.Counter()
    orig = text

    redirect = None
    m = RX_REDIRECT.match(text) or RX_REDIRECT_BARE.match(text)
    if m: redirect = m.group(1).strip()

    text = RX_COMMENT.sub(" ", text)
    
    cats = [x.strip() for x in RX_CATEGORY.findall(text)]
    c["category"] = len(cats)
    text = RX_CATEGORY.sub(" ", text)

    text, footnotes = extract_footnotes(text, c)
    c["footnote"] = len(footnotes)

    text = extract_braced(text, c)
    text, tables = extract_tables(text, c)

    links = []
    if collect_links:
        for mm in RX_LINK.finditer(text):
            tgt = mm.group(1).strip(); disp = (mm.group(2) or "").strip()
            anchor = None
            if "#" in tgt: tgt, anchor = tgt.split("#", 1)
            links.append({"target": tgt, "display": disp or tgt, "anchor": anchor,
                          "external": bool(re.match(r"https?://", tgt, re.I))})
    c["link"] = len(links)
    text = RX_LINK.sub(lambda mm: (mm.group(2) or mm.group(1)).strip(), text)

    n0 = len(RX_MACRO_ARG.findall(text)) + len(RX_MACRO.findall(text))
    c["macro"] = n0
    text = RX_MACRO_ARG.sub(" ", text)
    text = RX_MACRO.sub("\n", text)

    for rx, rep in DECOR: text = rx.sub(rep, text)
    text = RX_HR.sub(" ", text)
    text = RX_LIST.sub("", text)
    text = RX_QUOTE.sub("", text)

    sections = split_sections(text, norm=normalize)
    text = normalize(RX_HEADING.sub(" ", text))

    return {"redirect": redirect, "plain": text, "sections": sections,
            "categories": cats, "links": links, "footnotes": footnotes,
            "tables": tables, "stripped": dict(c),
            "len_raw": len(orig), "len_plain": len(text)}

def split_sections(text, norm=None):
    """절 계층을 number(1, 1.1, 1.1.1)로 표현. 관측된 깊이 기준."""
    hs = list(RX_HEADING.finditer(text))
    nz = norm or (lambda x: x)
    out = []
    if not hs:
        body = nz(text)
        if body: out.append({"level": 0, "number": "0", "title": None,
                             "hidden": False, "text": body})
        return out
    head = nz(text[:hs[0].start()])
    if head: out.append({"level": 0, "number": "0", "title": None,
                         "hidden": False, "text": head})
    path = []
    for i, h in enumerate(hs):
        lv = len(h.group(1))
        while path and path[-1][0] > lv: path.pop()
        if path and path[-1][0] == lv: path[-1][1] += 1
        else: path.append([lv, 1])
        body = text[h.end(): hs[i + 1].start() if i + 1 < len(hs) else len(text)]
        out.append({"level": lv, "number": ".".join(str(p[1]) for p in path),
                    "title": nz(h.group(3)) or None, "hidden": bool(h.group(2)),
                    "text": nz(RX_HEADING.sub(" ", body))})
    return out

if __name__ == "__main__":
    import sys, json
    src = open(sys.argv[1], encoding="utf-8").read()
    r = parse(src)
    r2 = dict(r); r2["plain"] = r["plain"][:1500]
    print(json.dumps(r2, ensure_ascii=False, indent=1))
