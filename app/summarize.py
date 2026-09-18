from __future__ import annotations

import logging
import math
import re
from collections import Counter

import httpx
from bs4 import BeautifulSoup
from janome.tokenizer import Tokenizer

from app.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT

logger = logging.getLogger("customrss.summarize")

# janomeの辞書ロードは重いのでプロセス内で1回だけ行う
_tokenizer = Tokenizer()

_KEEP_POS = ("名詞", "動詞", "形容詞")
_JA_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？])\s*")
_JA_MIN_SENTENCE_LEN = 8

_EN_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_EN_MIN_SENTENCE_LEN = 20
_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")
_EN_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "at", "for",
    "with", "is", "are", "was", "were", "be", "been", "being", "this", "that", "these",
    "those", "it", "its", "as", "by", "from", "have", "has", "had", "will", "would",
    "can", "could", "should", "we", "our", "they", "their", "i", "you", "he", "she",
    "his", "her", "them", "not", "no", "do", "does", "did", "so", "than", "then",
    "there", "here", "which", "who", "whom", "what", "when", "where", "why", "how",
    "all", "any", "some", "more", "most", "other", "into", "out", "up", "down", "over",
    "under", "again", "further", "once", "also", "just", "only", "very", "about",
    "after", "before", "such", "each", "because", "while", "s", "t",
}

_JAPANESE_CHAR_RE = re.compile(r"[぀-ヿ一-鿿]")


def _is_japanese(text: str) -> bool:
    sample = text[:500]
    return len(_JAPANESE_CHAR_RE.findall(sample)) > 5


def _text(node, selector: str) -> str | None:
    el = node.select_one(selector)
    return el.get_text(strip=True) if el else None


def _generic_main_text(soup: BeautifulSoup) -> str:
    """content_selector未指定サイト向けの簡易本文抽出。

    article/main/contentっぽいクラス名のコンテナのうち、
    直下の<p>合計文字数が最大のものを本文とみなす。
    """
    candidates = soup.select("article, main, [class*='content'], [class*='body']")
    best_text = ""
    best_len = 0
    for node in candidates:
        paragraphs = node.find_all("p")
        text = "\n".join(p.get_text(" ", strip=True) for p in paragraphs)
        if len(text) > best_len:
            best_text = text
            best_len = len(text)

    if best_len >= 200:
        return best_text

    # フォールバック: ページ全体の<p>を素朴に連結
    paragraphs = soup.find_all("p")
    return "\n".join(p.get_text(" ", strip=True) for p in paragraphs)


def fetch_article_text(url: str, content_selector: str | None) -> str | None:
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("failed to fetch article body for %s: %s", url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    if content_selector:
        text = _text(soup, content_selector)
        # セレクタ指定時は<p>単位で改行を保った方が文分割の精度が上がる
        node = soup.select_one(content_selector)
        if node is not None:
            paragraphs = node.find_all("p")
            if paragraphs:
                text = "\n".join(p.get_text(" ", strip=True) for p in paragraphs)
        if text:
            return text

    return _generic_main_text(soup) or None


def split_sentences(text: str) -> list[str]:
    flat = text.replace("\n", " ")
    if _is_japanese(text):
        raw = [s.strip() for s in _JA_SENTENCE_SPLIT_RE.split(flat) if s.strip()]
        return [s for s in raw if len(s) >= _JA_MIN_SENTENCE_LEN]

    raw = [s.strip() for s in _EN_SENTENCE_SPLIT_RE.split(flat) if s.strip()]
    return [s for s in raw if len(s) >= _EN_MIN_SENTENCE_LEN]


def _tokenize_words_ja(sentence: str) -> Counter:
    words: Counter = Counter()
    for token in _tokenizer.tokenize(sentence):
        pos = token.part_of_speech.split(",")[0]
        if pos in _KEEP_POS:
            words[token.base_form] += 1
    return words


def _tokenize_words_en(sentence: str) -> Counter:
    words = [w.lower() for w in _EN_WORD_RE.findall(sentence)]
    return Counter(w for w in words if w not in _EN_STOPWORDS and len(w) > 1)


def _tokenize_words(sentence: str, japanese: bool) -> Counter:
    return _tokenize_words_ja(sentence) if japanese else _tokenize_words_en(sentence)


def _cosine_similarity(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[w] * b[w] for w in common)
    if dot == 0:
        return 0.0
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (norm_a * norm_b)


def _textrank_scores(similarity: list[list[float]], damping: float = 0.85, iterations: int = 30) -> list[float]:
    n = len(similarity)
    if n == 0:
        return []
    scores = [1.0 / n] * n
    out_sums = [sum(row) or 1.0 for row in similarity]

    for _ in range(iterations):
        new_scores = []
        for i in range(n):
            rank_sum = sum(
                similarity[j][i] / out_sums[j] * scores[j]
                for j in range(n)
                if j != i and similarity[j][i] > 0
            )
            new_scores.append((1 - damping) / n + damping * rank_sum)
        if sum(abs(new - old) for new, old in zip(new_scores, scores)) < 1e-4:
            scores = new_scores
            break
        scores = new_scores
    return scores


def top_sentences(text: str, top_n: int = 3) -> list[str]:
    sentences = split_sentences(text)
    if len(sentences) <= top_n:
        return sentences

    japanese = _is_japanese(text)
    word_counters = [_tokenize_words(s, japanese) for s in sentences]
    n = len(sentences)
    similarity = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_similarity(word_counters[i], word_counters[j])
            similarity[i][j] = sim
            similarity[j][i] = sim

    scores = _textrank_scores(similarity)
    ranked_indices = sorted(range(n), key=lambda i: scores[i], reverse=True)[:top_n]
    ranked_indices.sort()  # 元の文章順に並べ直す
    return [sentences[i] for i in ranked_indices]


def summarize_article(url: str, content_selector: str | None, top_n: int = 3) -> list[str]:
    text = fetch_article_text(url, content_selector)
    if not text:
        return []
    return top_sentences(text, top_n=top_n)
