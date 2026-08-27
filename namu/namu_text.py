#!/usr/bin/env python3
"""theseed-bot 출력의 공백 복원과 조작된 인접 검출.

theseed-bot은 노드 사이 구분자를 넣지 않아 요소 제거 자리에서 단어가 붙는다.
종결부호 뒤로만 한정하면 URL 끝이나 닫는 괄호 뒤를 놓친다.
"""
import re

# 한글은 URL 문자에서 제외한다. 포함하면 뒤 문장을 통째로 삼킨다
URL_RX = re.compile(r"https?://[^\s<>\[\]{}|\"'가-힣]+")
# 맨 도메인. 종결부호 규칙이 example.com 의 점을 쪼개지 않게 가린다
BARE_DOMAIN_RX = re.compile(
    r"\b(?:[a-zA-Z0-9][a-zA-Z0-9-]*\.)+(?:com|net|org|edu|gov|io|ai|gg|tv|me|info|biz|"
    r"kr|jp|cn|us|uk|de|fr|ru|co\.kr|or\.kr|ne\.kr|go\.kr|ac\.kr)"
    r"(?:/[^\s<>\[\]{}|\"']*)?", re.I)
# URL 끝이 TLD인데 곧바로 숫자가 오면 URL이 아니라 뒤 토큰이 붙은 것
TLD_DIGIT_RX = re.compile(r"(\.[a-z]{2,6})(?=\d)", re.I)
# URL 뒤 한글이 조사면 원문에서도 붙어 쓰인다. 띄우지 않는다
PARTICLE_RX = re.compile(
    r"(?:에서|에게서|에게|께서|께|으로부터|로부터|으로써|로써|으로서|로서|으로|로|"
    r"까지|부터|처럼|만큼|보다|한테|더러|랑|이랑|와|과|은|는|이|가|을|를|의|도|만|"
    r"조차|마저|밖에|뿐|이나|나|든지|라도|이라도|라고|이라고|고|며|이며)\b")

# 종결부호 뒤. URL을 먼저 가려야 example.com 의 점에 걸리지 않는다
RX_SENT   = re.compile(r"([.!?…])(?=[가-힣A-Za-z])")
# 닫는 괄호와 닫는 따옴표 뒤
RX_CLOSE  = re.compile(r"([)\]}»›」』”’])(?=[가-힣A-Za-z0-9(\[{])")
# 여는 괄호 앞
RX_OPEN   = re.compile(r"(?<=[가-힣A-Za-z0-9)\]}])(?=[(\[{«‹「『“‘])")
# 쉼표 세미콜론 콜론 뒤
RX_PUNCT  = re.compile(r"([,;:])(?=[가-힣A-Za-z])")

def _mask_urls(t):
    urls = []          # (문자열, http여부)
    def mk(is_http):
      def sub(m):
        u = m.group(0)
        tail = ""
        d = TLD_DIGIT_RX.search(u)
        if d:                      # danbee.ai2018 -> danbee.ai + " " + 2018
            cut = d.end(1); u, tail = u[:cut], " " + u[cut:]
        urls.append((u, is_http))
        return "\x00U%d\x00" % (len(urls) - 1) + tail
      return sub
    t = URL_RX.sub(mk(True), t)
    t = BARE_DOMAIN_RX.sub(mk(False), t)
    return t, urls

def _unmask_urls(t, urls):
    def sub(m):
        return urls[int(m.group(1))][0]
    # http URL 뒤에 한글이 바로 붙는 것은 문법 제거가 만든 인접이므로 띄운다.
    # 맨 도메인은 원문에서도 조사가 붙어 쓰이므로(example.com에서) 건드리지 않는다.
    def sp(m):
        i = int(m.group(1))
        if not urls[i][1]: return m.group(0)          # 맨 도메인은 건드리지 않음
        if PARTICLE_RX.match(t, m.end()): return m.group(0)   # 조사면 원문에서도 붙음
        return m.group(0) + " "
    t = re.sub(r"\x00U(\d+)\x00(?=[가-힣])", sp, t)
    t = re.sub(r"\x00U(\d+)\x00", sub, t)
    return t

def respace(t):
    if not t: return t
    t, urls = _mask_urls(t)
    t = RX_SENT.sub(r"\1 ", t)
    t = RX_CLOSE.sub(r"\1 ", t)
    t = RX_OPEN.sub(" ", t)
    t = RX_PUNCT.sub(r"\1 ", t)
    t = _unmask_urls(t, urls)
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

# ---------- 조작된 인접 검출 ----------
# 창 단위 대조는 못 쓴다. 링크 [[A|B]] -> B 처럼 문법 제거가 원문 텍스트를
# 정당하게 바꾸므로 링크 근처가 전부 오탐이 된다.
# 대신 경계를 걸치는 토큰 하나를 뽑아 그 토큰이 원문에 존재하는지 본다.
WS = re.compile(r"\s+")
WORD = re.compile(r"[가-힣A-Za-z0-9]")
GLUE_BOUNDARY = re.compile(r"(?<=[가-힣])(?=[A-Za-z])|(?<=[A-Za-z])(?=[가-힣])"
                           r"|(?<=[가-힣A-Za-z0-9])(?=[(\[])|(?<=[)\]])(?=[가-힣A-Za-z0-9])")

def _token_around(t, i):
    a = i
    while a > 0 and WORD.match(t[a - 1]): a -= 1
    b = i
    while b < len(t) and WORD.match(t[b]): b += 1
    return t[a:b], a, b

def fabricated_adjacency(plain, raw, limit=400):
    """경계를 걸쳐 만들어진 토큰이 원문에 없으면 조작된 인접으로 센다."""
    if not plain or not raw: return [], 0
    raw_flat = WS.sub("", raw)
    out, n, seen = [], 0, set()
    for m in GLUE_BOUNDARY.finditer(plain):
        i = m.start()
        tok, a, b = _token_around(plain, i)
        if len(tok) < 4 or a >= i or b <= i: continue
        if tok in seen: continue
        seen.add(tok)
        if tok in raw_flat: continue
        n += 1
        if len(out) < 12: out.append(plain[max(0, a - 18):b + 14].replace("\n", " "))
        if n >= limit: break
    return out, n

# 종결부호 직후 공백 누락. 후처리가 남긴 것을 재는 보조 지표
SENT_GLUE = re.compile(r"[.!?][가-힣A-Za-z]")
