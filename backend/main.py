import asyncio
import os
import re
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MAX_PAGES = int(os.getenv("MAX_PAGES", "12"))
MAX_CHARS = int(os.getenv("MAX_CHARS", "30000"))
CRAWL_TIMEOUT = float(os.getenv("CRAWL_TIMEOUT", "8"))
MAX_DEPTH = int(os.getenv("MAX_DEPTH", "3"))
MAX_QUEUE = int(os.getenv("MAX_QUEUE", "100"))
FOCUSED_PAGES = int(os.getenv("FOCUSED_PAGES", "4"))
MIN_TEXT_LEN = int(os.getenv("MIN_TEXT_LEN", "200"))
PARALLEL_FETCHES = int(os.getenv("PARALLEL_FETCHES", "4"))

app = FastAPI(title="Deep Website Learner")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SummarizeRequest(BaseModel):
    url: HttpUrl


class SummarizeResponse(BaseModel):
    session_id: str
    summary: str
    pages_crawled: int


class AskRequest(BaseModel):
    session_id: str
    question: str


class AskResponse(BaseModel):
    answer: str


@dataclass
class PageData:
    url: str
    title: str
    text: str


@dataclass
class SessionData:
    url: str
    pages: List[PageData]
    visited: Set[str] = field(default_factory=set)
    link_index: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def content(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


SESSIONS: Dict[str, SessionData] = {}


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _same_domain(root: str, candidate: str) -> bool:
    return urlparse(root).netloc == urlparse(candidate).netloc


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    normalized = parsed._replace(fragment="")
    return urlunparse(normalized)


def _should_skip_url(url: str) -> bool:
    lowered = url.lower()
    return any(
        lowered.endswith(ext)
        for ext in (
            ".pdf",
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".svg",
            ".zip",
            ".mp4",
            ".mp3",
            ".avi",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
        )
    )


async def _fetch_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    response = await client.get(url, timeout=CRAWL_TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return None
    return response.text


def _extract_links(base_url: str, soup: BeautifulSoup) -> List[Tuple[str, str]]:
    links: List[Tuple[str, str]] = []
    for tag in soup.find_all("a", href=True):
        href = urljoin(base_url, tag["href"])
        if href.startswith("http"):
            links.append((_normalize_url(href), _clean_text(tag.get_text(" "))))
    return links


def _extract_main_text(soup: BeautifulSoup) -> Tuple[str, str]:
    title = soup.title.get_text(strip=True) if soup.title else ""
    for element in soup(
        ["script", "style", "noscript", "header", "footer", "nav", "aside"]
    ):
        element.decompose()
    text = _clean_text(soup.get_text(separator=" "))
    return title, text


async def _fetch_sitemap_links(client: httpx.AsyncClient, base_url: str) -> List[str]:
    sitemap_url = urljoin(base_url, "/sitemap.xml")
    try:
        response = await client.get(sitemap_url, timeout=CRAWL_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    soup = BeautifulSoup(response.text, "xml")
    links = []
    for loc in soup.find_all("loc"):
        if loc.text:
            links.append(_normalize_url(loc.text.strip()))
    return links


async def _process_page(
    client: httpx.AsyncClient,
    url: str,
    session: SessionData,
) -> Optional[PageData]:
    try:
        html = await _fetch_html(client, url)
    except httpx.HTTPError:
        return None
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    title, text = _extract_main_text(soup)
    if len(text) < MIN_TEXT_LEN:
        return None

    for link, label in _extract_links(url, soup):
        if _same_domain(session.url, link):
            session.link_index.append((link, label))

    return PageData(url=url, title=title, text=text)


def _score_link(link: Tuple[str, str], keywords: Iterable[str]) -> int:
    href, label = link
    score = 0
    for keyword in keywords:
        if keyword in href.lower():
            score += 2
        if keyword in label.lower():
            score += 1
    return score


async def _crawl_site(start_url: str) -> SessionData:
    session = SessionData(url=start_url, pages=[], visited=set())
    queue: Deque[Tuple[str, int]] = deque()
    queue.append((_normalize_url(start_url), 0))

    async with httpx.AsyncClient(headers={"User-Agent": "DWL/0.1"}) as client:
        sitemap_links = await _fetch_sitemap_links(client, start_url)
        for link in sitemap_links:
            if _same_domain(start_url, link):
                queue.append((link, 1))

        semaphore = asyncio.Semaphore(PARALLEL_FETCHES)

        async def bound_fetch(target_url: str) -> Optional[PageData]:
            async with semaphore:
                return await _process_page(client, target_url, session)

        while queue and len(session.pages) < MAX_PAGES and len(queue) <= MAX_QUEUE:
            current, depth = queue.popleft()
            if current in session.visited or depth > MAX_DEPTH or _should_skip_url(current):
                continue
            session.visited.add(current)

            page = await bound_fetch(current)
            if page:
                session.pages.append(page)

            if len(session.pages) < MAX_PAGES:
                for link, _label in session.link_index[-30:]:
                    if (
                        _same_domain(start_url, link)
                        and link not in session.visited
                        and not _should_skip_url(link)
                    ):
                        queue.append((link, depth + 1))

            if len(session.content) >= MAX_CHARS:
                break

    return session


async def _focused_crawl(session: SessionData, question: str) -> None:
    keywords = {word.lower() for word in re.findall(r"\w+", question) if len(word) > 3}
    if not keywords:
        return

    ranked_links = sorted(
        session.link_index, key=lambda link: _score_link(link, keywords), reverse=True
    )
    candidates = [
        link for link, _label in ranked_links if link not in session.visited
    ][:FOCUSED_PAGES]

    async with httpx.AsyncClient(headers={"User-Agent": "DWL/0.1"}) as client:
        for link in candidates:
            page = await _process_page(client, link, session)
            if page:
                session.pages.append(page)
                session.visited.add(link)
            if len(session.content) >= MAX_CHARS:
                break


async def _call_ollama(prompt: str) -> str:
    payload = {
        "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        "prompt": prompt,
        "stream": False,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()


@app.post("/api/summarize", response_model=SummarizeResponse)
async def summarize(request: SummarizeRequest) -> SummarizeResponse:
    session_data = await _crawl_site(str(request.url))
    if not session_data.content:
        raise HTTPException(status_code=400, detail="No readable content found for this URL.")

    prompt = (
        "You are a helpful assistant summarizing a website for a user. "
        "Respond in a structured format with headings.\n\n"
        "Format:\n"
        "Overview: <2-3 sentences>\n"
        "Key Sections:\n"
        "- Bullet list of major sections or services.\n"
        "Important Details:\n"
        "- Bullet list of policies, contacts, hours, or deadlines.\n"
        "Suggested Questions:\n"
        "- Bullet list of 3 follow-up questions.\n\n"
        f"Website URL: {session_data.url}\n"
        f"Content:\n{session_data.content[:MAX_CHARS]}\n\nSummary:"
    )

    try:
        summary = await _call_ollama(prompt)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {exc}") from exc

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = session_data

    return SummarizeResponse(
        session_id=session_id, summary=summary, pages_crawled=len(session_data.pages)
    )


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    session = SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session. Please summarize a site first.")

    if request.question.lower() not in session.content.lower():
        await _focused_crawl(session, request.question)

    prompt = (
        "You are a helpful assistant answering questions about a website. "
        "Use the provided content. If the answer is not in the content, say you are not sure. "
        "Respond in a structured format with headings.\n\n"
        "Format:\n"
        "Answer: <clear response>\n"
        "Evidence:\n"
        "- Bullet list of supporting details from the site content.\n"
        "Confidence: <High/Medium/Low>\n\n"
        f"Website URL: {session.url}\n"
        f"Content:\n{session.content[:MAX_CHARS]}\n\n"
        f"Question: {request.question}\nAnswer:"
    )

    try:
        answer = await _call_ollama(prompt)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {exc}") from exc

    return AskResponse(answer=answer)


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
async def warmup() -> None:
    await asyncio.sleep(0.01)
