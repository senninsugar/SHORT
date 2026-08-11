from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urlparse, parse_qs, unquote
import time
import random

app = FastAPI(
    title="YouTube Shorts Search API",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

HEADERS_LIST = [
    {
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
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) "
            "Gecko/20100101 Firefox/142.0"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
        "Referer": "https://duckduckgo.com/"
    }
]

MAX_RETRIES = 3
REQUEST_TIMEOUT = 20


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
    url = unquote(url)

    return url


def extract_youtube_url(url):
    if not url:
        return None

    try:
        current_url = clean_url(url)

        for _ in range(3):
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

            for value in query["uddg"]:
                decoded = clean_url(value)

                decoded_parsed = urlparse(
                    decoded
                )

                if is_youtube_hostname(
                    decoded_parsed.hostname
                ):
                    return decoded

                next_url = decoded

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
                    return video_id

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

            video_id = video_id.strip()

            if video_id:
                return video_id

        if path.startswith("/v/"):
            video_id = path.split(
                "/v/",
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

        return parsed.path.startswith(
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
        "article.result",
        ".nrn-react-div"
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

    seen_ids = set()

    for element in elements:
        element_id = id(element)

        if element_id in seen_ids:
            continue

        seen_ids.add(
            element_id
        )

        unique_elements.append(
            element
        )

    return unique_elements


def request_duckduckgo(url):
    last_error = None

    for attempt in range(
        MAX_RETRIES
    ):
        try:
            headers = random.choice(
                HEADERS_LIST
            )

            response = requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )

            if response.status_code == 200:
                if response.text:
                    return response

            last_error = (
                f"HTTP {response.status_code}"
            )

        except requests.RequestException as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            time.sleep(
                1.5 + random.random() * 1.5
            )

    raise RuntimeError(
        "DuckDuckGoへのアクセスに失敗しました: "
        f"{last_error}"
    )


def build_search_queries(
    query
):
    return [
        f"{query} site:youtube.com/shorts",
        f"{query} YouTube Shorts",
        f"{query} youtube shorts",
        f"site:youtube.com/shorts {query}"
    ]


def fetch_duckduckgo_results(
    search_query,
    page
):
    encoded_query = quote(
        search_query
    )

    offset = (
        (page - 1) * 30
    )

    url = (
        "https://html.duckduckgo.com/html/"
        f"?q={encoded_query}"
        f"&s={offset}"
    )

    response = request_duckduckgo(
        url
    )

    soup = BeautifulSoup(
        response.text,
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

        results.append({
            "title": title,
            "raw_url": raw_url,
            "youtube_url": youtube_url,
            "snippet": snippet
        })

    return results


def convert_to_shorts_result(
    item
):
    youtube_url = item.get(
        "youtube_url",
        ""
    )

    video_id = extract_video_id(
        youtube_url
    )

    if not video_id:
        return None

    explicit_shorts = (
        is_explicit_shorts_url(
            youtube_url
        )
    )

    title = item.get(
        "title",
        ""
    )

    snippet = item.get(
        "snippet",
        ""
    )

    combined_text = (
        f"{title} "
        f"{snippet} "
        f"{youtube_url}"
    ).lower()

    shorts_keywords = [
        "shorts",
        "youtube shorts",
        "short",
        "ショート",
        "short動画",
        "shorts動画"
    ]

    has_shorts_keyword = any(
        keyword in combined_text
        for keyword in shorts_keywords
    )

    if not explicit_shorts:
        if not has_shorts_keyword:
            return None

    return {
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
    }


def search_shorts(
    query,
    page,
    limit
):
    search_queries = build_search_queries(
        query
    )

    collected = []

    used_video_ids = set()

    errors = []

    for search_query in search_queries:
        try:
            raw_results = fetch_duckduckgo_results(
                search_query,
                page
            )

            for item in raw_results:
                result = convert_to_shorts_result(
                    item
                )

                if not result:
                    continue

                video_id = result[
                    "video_id"
                ]

                if video_id in used_video_ids:
                    continue

                used_video_ids.add(
                    video_id
                )

                collected.append(
                    result
                )

                if len(collected) >= limit:
                    return {
                        "results": collected,
                        "errors": errors,
                        "queries_used": (
                            search_queries[
                                :search_queries.index(
                                    search_query
                                ) + 1
                            ]
                        )
                    }

        except Exception as e:
            errors.append({
                "query": search_query,
                "error": str(e)
            })

            continue

        time.sleep(
            0.5 + random.random() * 0.8
        )

    return {
        "results": collected,
        "errors": errors,
        "queries_used": search_queries
    }


@app.get("/")
def index():
    return {
        "success": True,
        "name": "YouTube Shorts Search API",
        "version": "2.0.0",
        "status": "online",
        "type": "youtube_shorts",
        "endpoint": "/api/search?q=検索ワード&page=1&limit=20"
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
            "limit": limit,
            "count": 0,
            "results": [],
            "has_next": False,
            "has_previous": page > 1,
            "next_page": None,
            "previous_page": (
                page - 1
                if page > 1
                else None
            ),
            "error": "検索ワードが空です"
        }

    try:
        search_data = search_shorts(
            query,
            page,
            limit
        )

        results = search_data[
            "results"
        ]

        errors = search_data[
            "errors"
        ]

        has_next = (
            len(results) >= limit
        )

        has_previous = (
            page > 1
        )

        return {
            "success": True,
            "query": query,
            "type": "youtube_shorts",
            "page": page,
            "limit": limit,
            "count": len(results),
            "results": results,
            "has_next": has_next,
            "has_previous": has_previous,
            "next_page": (
                page + 1
                if has_next
                else None
            ),
            "previous_page": (
                page - 1
                if has_previous
                else None
            ),
            "search_status": (
                "ok"
                if len(results) > 0
                else "no_results"
            ),
            "warnings": errors
        }

    except Exception as e:
        return {
            "success": False,
            "query": query,
            "type": "youtube_shorts",
            "page": page,
            "limit": limit,
            "count": 0,
            "results": [],
            "has_next": False,
            "has_previous": page > 1,
            "next_page": None,
            "previous_page": (
                page - 1
                if page > 1
                else None
            ),
            "error": str(e)
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
            "results": [],
            "error": "検索ワードが空です"
        }

    search_queries = build_search_queries(
        query
    )

    debug_results = []

    errors = []

    for search_query in search_queries:
        try:
            raw_results = fetch_duckduckgo_results(
                search_query,
                page
            )

            query_results = []

            for item in raw_results:
                youtube_url = item.get(
                    "youtube_url"
                )

                video_id = extract_video_id(
                    youtube_url
                )

                query_results.append({
                    "title": item.get(
                        "title",
                        ""
                    ),
                    "raw_url": item.get(
                        "raw_url",
                        ""
                    ),
                    "youtube_url": youtube_url,
                    "video_id": video_id,
                    "is_shorts": (
                        is_explicit_shorts_url(
                            youtube_url
                        )
                    ),
                    "snippet": item.get(
                        "snippet",
                        ""
                    )
                })

            debug_results.append({
                "search_query": search_query,
                "count": len(
                    query_results
                ),
                "results": query_results
            })

        except Exception as e:
            errors.append({
                "search_query": search_query,
                "error": str(e)
            })

    return {
        "success": True,
        "query": query,
        "page": page,
        "search_queries": search_queries,
        "results": debug_results,
        "errors": errors
    }


@app.get("/api/health")
def health():
    return {
        "success": True,
        "status": "healthy"
    }
