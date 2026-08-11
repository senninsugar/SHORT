from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urlparse, parse_qs, unquote
import time
import re
import random

app = FastAPI(
    title="YouTube Shorts Search API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Referer": "https://html.duckduckgo.com/"
}

MAX_RETRIES = 5
REQUEST_TIMEOUT = 25
DUCKDUCKGO_PAGE_SIZE = 30


def normalize_hostname(hostname):
    if not hostname:
        return ""

    hostname = hostname.lower().strip()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def is_youtube_hostname(hostname):
    hostname = normalize_hostname(hostname)

    return hostname in [
        "youtube.com",
        "m.youtube.com"
    ]


def is_duckduckgo_hostname(hostname):
    hostname = normalize_hostname(hostname)

    return hostname in [
        "duckduckgo.com",
        "html.duckduckgo.com",
        "lite.duckduckgo.com"
    ]


def clean_url(url):
    if not url:
        return ""

    url = url.strip()

    for _ in range(8):
        decoded_url = unquote(url)

        if decoded_url == url:
            break

        url = decoded_url

    return url


def extract_youtube_url(url):
    if not url:
        return None

    try:
        current_url = clean_url(url)

        for _ in range(10):
            parsed = urlparse(current_url)

            if is_youtube_hostname(
                parsed.hostname
            ):
                return current_url

            if not is_duckduckgo_hostname(
                parsed.hostname
            ):
                return None

            query = parse_qs(
                parsed.query
            )

            possible_keys = [
                "uddg",
                "u"
            ]

            next_url = None

            for key in possible_keys:
                if key not in query:
                    continue

                for encoded_url in query[key]:
                    decoded_url = clean_url(
                        encoded_url
                    )

                    decoded_parsed = urlparse(
                        decoded_url
                    )

                    if is_youtube_hostname(
                        decoded_parsed.hostname
                    ):
                        return decoded_url

                    next_url = decoded_url

            if not next_url:
                return None

            current_url = next_url

        return None

    except Exception:
        return None


def extract_video_id(url):
    if not url:
        return None

    try:
        parsed = urlparse(url)

        if not is_youtube_hostname(
            parsed.hostname
        ):
            return None

        path = parsed.path or ""

        if path.startswith("/shorts/"):
            video_id = path.split(
                "/shorts/",
                1
            )[1]

            video_id = video_id.split(
                "/",
                1
            )[0]

            video_id = video_id.split(
                "?",
                1
            )[0]

            video_id = video_id.split(
                "#",
                1
            )[0]

            video_id = video_id.strip()

            if video_id:
                return video_id

        if path == "/watch":
            params = parse_qs(
                parsed.query
            )

            if "v" in params:
                video_id = params["v"][0]

                if video_id:
                    return video_id.strip()

        if path.startswith("/embed/"):
            video_id = path.split(
                "/embed/",
                1
            )[1]

            video_id = video_id.split(
                "/",
                1
            )[0]

            video_id = video_id.split(
                "?",
                1
            )[0]

            video_id = video_id.split(
                "#",
                1
            )[0]

            video_id = video_id.strip()

            if video_id:
                return video_id

        return None

    except Exception:
        return None


def is_explicit_shorts_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(url)

        if not is_youtube_hostname(
            parsed.hostname
        ):
            return False

        path = parsed.path or ""

        return path.startswith(
            "/shorts/"
        )

    except Exception:
        return False


def build_shorts_url(video_id):
    return (
        "https://www.youtube.com/shorts/"
        f"{video_id}"
    )


def build_thumbnail_url(video_id):
    return (
        "https://i.ytimg.com/vi/"
        f"{video_id}/hqdefault.jpg"
    )


def get_result_title(result):
    selectors = [
        ".result__title a",
        ".result__a",
        "a.result__a",
        "h2 a",
        "h3 a"
    ]

    for selector in selectors:
        element = result.select_one(
            selector
        )

        if element:
            title = element.get_text(
                " ",
                strip=True
            )

            if title:
                return title

    return ""


def get_result_url(result):
    selectors = [
        ".result__title a",
        ".result__a",
        "a.result__a",
        "h2 a",
        "h3 a"
    ]

    for selector in selectors:
        element = result.select_one(
            selector
        )

        if element:
            url = element.get(
                "href",
                ""
            )

            if url:
                return url

    return ""


def get_result_snippet(result):
    selectors = [
        ".result__snippet",
        ".result__body",
        ".result__description"
    ]

    for selector in selectors:
        element = result.select_one(
            selector
        )

        if element:
            snippet = element.get_text(
                " ",
                strip=True
            )

            if snippet:
                return snippet

    return ""


def extract_result_elements(soup):
    selectors = [
        ".result",
        ".results .result",
        "article.result"
    ]

    elements = []

    for selector in selectors:
        found = soup.select(
            selector
        )

        if found:
            elements.extend(
                found
            )

    unique_elements = []

    seen = set()

    for element in elements:
        key = str(element)

        if key in seen:
            continue

        seen.add(key)

        unique_elements.append(
            element
        )

    return unique_elements


def contains_shorts_keyword(
    title,
    snippet,
    url,
    query
):
    text = (
        f"{title} "
        f"{snippet} "
        f"{url} "
        f"{query}"
    ).lower()

    keywords = [
        "youtube shorts",
        "youtube short",
        "shorts",
        "/shorts/",
        "ショート",
        "short video",
        "short動画",
        "#shorts"
    ]

    for keyword in keywords:
        if keyword.lower() in text:
            return True

    return False


def is_valid_youtube_video_id(video_id):
    if not video_id:
        return False

    if len(video_id) < 5:
        return False

    if len(video_id) > 20:
        return False

    return (
        re.fullmatch(
            r"[A-Za-z0-9_-]+",
            video_id
        )
        is not None
    )


def is_valid_search_html(text):
    if not text:
        return False

    if len(text) < 1000:
        return False

    lowered = text.lower()

    block_words = [
        "captcha",
        "robot check",
        "access denied",
        "unusual traffic"
    ]

    for word in block_words:
        if word in lowered:
            return False

    if (
        ".result"
        not in lowered
        and "result__a"
        not in lowered
        and "result__title"
        not in lowered
    ):
        return False

    return True


def create_session():
    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    return session


def request_duckduckgo(
    search_query,
    page
):
    offset = (
        (page - 1)
        * DUCKDUCKGO_PAGE_SIZE
    )

    get_url = (
        "https://html.duckduckgo.com/html/"
        f"?q={quote(search_query)}"
    )

    if page > 1:
        get_url += (
            f"&s={offset}"
        )

    post_url = (
        "https://html.duckduckgo.com/html/"
    )

    lite_url = (
        "https://lite.duckduckgo.com/lite/"
    )

    session = create_session()

    last_error = None

    for attempt in range(
        MAX_RETRIES
    ):
        try:
            if attempt % 3 == 0:
                response = session.get(
                    get_url,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True
                )

            elif attempt % 3 == 1:
                payload = {
                    "q": search_query
                }

                if page > 1:
                    payload["s"] = str(
                        offset
                    )

                response = session.post(
                    post_url,
                    data=payload,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True
                )

            else:
                lite_params = {
                    "q": search_query
                }

                if page > 1:
                    lite_params["s"] = str(
                        offset
                    )

                response = session.get(
                    lite_url,
                    params=lite_params,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True
                )

            if response.status_code == 200:
                text = response.text

                if is_valid_search_html(
                    text
                ):
                    return text

            last_error = (
                f"HTTP {response.status_code}"
            )

        except requests.RequestException as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            time.sleep(
                1.0 + (
                    attempt * 1.5
                ) + random.uniform(
                    0.2,
                    0.8
                )
            )

    raise RuntimeError(
        "DuckDuckGoへのアクセスに失敗しました"
    )


def parse_duckduckgo_results(
    html,
    query
):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    result_elements = extract_result_elements(
        soup
    )

    results = []

    for result in result_elements:
        title = get_result_title(
            result
        )

        raw_url = get_result_url(
            result
        )

        snippet = get_result_snippet(
            result
        )

        if not raw_url:
            continue

        youtube_url = extract_youtube_url(
            raw_url
        )

        if not youtube_url:
            continue

        video_id = extract_video_id(
            youtube_url
        )

        if not video_id:
            continue

        if not is_valid_youtube_video_id(
            video_id
        ):
            continue

        explicit_shorts = (
            is_explicit_shorts_url(
                youtube_url
            )
        )

        has_shorts_keyword = (
            contains_shorts_keyword(
                title,
                snippet,
                youtube_url,
                query
            )
        )

        if not explicit_shorts:
            if not has_shorts_keyword:
                continue

        results.append({
            "title": title,
            "url": build_shorts_url(
                video_id
            ),
            "video_id": video_id,
            "thumbnail": build_thumbnail_url(
                video_id
            ),
            "snippet": snippet,
            "type": "youtube_short",
            "source_url": youtube_url,
            "is_explicit_shorts": explicit_shorts
        })

    return results


def search_one_query(
    query,
    page
):
    search_query = (
        f"site:youtube.com/shorts {query}"
    )

    html = request_duckduckgo(
        search_query,
        page
    )

    return parse_duckduckgo_results(
        html,
        query
    )


def search_duckduckgo(
    query,
    page=1,
    max_results=20
):
    search_queries = [
        f"site:youtube.com/shorts {query}",
        f"site:youtube.com/shorts {query} shorts",
        f"site:youtube.com/shorts {query} ショート"
    ]

    results = []

    used_video_ids = set()

    for search_query in search_queries:
        try:
            html = request_duckduckgo(
                search_query,
                page
            )
        except Exception:
            continue

        page_results = parse_duckduckgo_results(
            html,
            query
        )

        for item in page_results:
            video_id = item[
                "video_id"
            ]

            if video_id in used_video_ids:
                continue

            used_video_ids.add(
                video_id
            )

            results.append(
                item
            )

            if len(results) >= max_results:
                return results

    return results


@app.get("/")
def index():
    return {
        "success": True,
        "name": "YouTube Shorts Search API",
        "version": "1.0.0",
        "status": "online",
        "endpoint": "/api/search?q=検索ワード&page=1",
        "type": "youtube_shorts"
    }


@app.get("/api/search")
def api_search(
    q: str = Query(
        ...,
        min_length=1
    ),
    page: int = Query(
        1,
        ge=1,
        le=100
    ),
    limit: int = Query(
        20,
        ge=1,
        le=50
    )
):
    query = q.strip()

    if not query:
        return {
            "success": False,
            "query": q,
            "type": "youtube_shorts",
            "page": page,
            "count": 0,
            "results": []
        }

    try:
        results = search_duckduckgo(
            query,
            page,
            limit
        )

        return {
            "success": True,
            "query": query,
            "type": "youtube_shorts",
            "page": page,
            "count": len(results),
            "results": results
        }

    except Exception:
        return {
            "success": False,
            "query": query,
            "type": "youtube_shorts",
            "page": page,
            "count": 0,
            "results": []
        }


@app.get("/api/debug")
def api_debug(
    q: str = Query(
        ...,
        min_length=1
    ),
    page: int = Query(
        1,
        ge=1,
        le=100
    )
):
    query = q.strip()

    if not query:
        return {
            "success": False,
            "query": q,
            "page": page,
            "results": []
        }

    search_query = (
        f"site:youtube.com/shorts {query}"
    )

    try:
        html = request_duckduckgo(
            search_query,
            page
        )

        raw_results = parse_duckduckgo_results(
            html,
            query
        )

        return {
            "success": True,
            "query": query,
            "page": page,
            "duckduckgo_query": search_query,
            "result_count": len(raw_results),
            "results": raw_results
        }

    except Exception:
        return {
            "success": False,
            "query": query,
            "page": page,
            "results": []
        }
