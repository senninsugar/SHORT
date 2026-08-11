from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urlparse, parse_qs, unquote
import time
import re

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
        "*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://duckduckgo.com/"
}

MAX_RETRIES = 4
REQUEST_TIMEOUT = 25
RESULTS_PER_PAGE = 20
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
        "html.duckduckgo.com"
    ]


def clean_url(url):
    if not url:
        return ""

    url = url.strip()

    for _ in range(5):
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

            if "uddg" not in query:
                return None

            next_url = None

            for encoded_url in query["uddg"]:
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

    seen_elements = set()

    for element in elements:
        element_id = id(element)

        if element_id in seen_elements:
            continue

        seen_elements.add(
            element_id
        )

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
        "short動画"
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

    return re.fullmatch(
        r"[A-Za-z0-9_-]+",
        video_id
    ) is not None


def request_duckduckgo(url):
    last_response = None
    last_error = None

    for attempt in range(
        MAX_RETRIES
    ):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )

            last_response = response

            if response.status_code in [
                200,
                202
            ]:
                if response.text:
                    return response

            last_error = (
                f"HTTP {response.status_code}"
            )

        except requests.RequestException as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            time.sleep(
                1.5 * (attempt + 1)
            )

    if last_response is not None:
        if last_response.text:
            return last_response

    raise RuntimeError(
        "DuckDuckGoへのアクセスに失敗しました"
    )


def build_search_url(
    search_query,
    page
):
    encoded_query = quote(
        search_query
    )

    offset = (
        (page - 1)
        * DUCKDUCKGO_PAGE_SIZE
    )

    return (
        "https://html.duckduckgo.com/html/"
        f"?q={encoded_query}"
        f"&s={offset}"
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

    parsed_results = []

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

        parsed_results.append({
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

    return parsed_results


def search_duckduckgo(
    query,
    page=1,
    max_results=20
):
    primary_query = (
        f"site:youtube.com/shorts {query}"
    )

    search_queries = [
        primary_query,
        f"site:youtube.com/shorts {query} shorts"
    ]

    all_results = []
    used_video_ids = set()

    for search_index, search_query in enumerate(
        search_queries
    ):
        if search_index == 0:
            current_page = page
        else:
            current_page = page

        url = build_search_url(
            search_query,
            current_page
        )

        try:
            response = request_duckduckgo(
                url
            )
        except Exception:
            continue

        page_results = parse_duckduckgo_results(
            response.text,
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

            all_results.append(
                item
            )

            if len(all_results) >= max_results:
                return all_results

    return all_results


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

    url = build_search_url(
        search_query,
        page
    )

    try:
        response = request_duckduckgo(
            url
        )

        results = parse_duckduckgo_results(
            response.text,
            query
        )

        return {
            "success": True,
            "query": query,
            "page": page,
            "duckduckgo_query": search_query,
            "result_count": len(results),
            "results": results
        }

    except Exception:
        return {
            "success": False,
            "query": query,
            "page": page,
            "results": []
        }
