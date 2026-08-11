from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urlparse, parse_qs, unquote

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


def normalize_hostname(hostname):
    if not hostname:
        return ""

    hostname = hostname.lower()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def is_youtube_hostname(hostname):
    hostname = normalize_hostname(hostname)

    return hostname in [
        "youtube.com",
        "m.youtube.com"
    ]


def extract_youtube_url(url):
    if not url:
        return None

    try:
        url = unquote(url)

        parsed = urlparse(url)

        if is_youtube_hostname(parsed.hostname):
            return url

        if normalize_hostname(parsed.hostname) == "duckduckgo.com":
            query = parse_qs(parsed.query)

            if "uddg" in query:
                for encoded_url in query["uddg"]:
                    decoded_url = unquote(encoded_url)

                    decoded_parsed = urlparse(
                        decoded_url
                    )

                    if is_youtube_hostname(
                        decoded_parsed.hostname
                    ):
                        return decoded_url

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

        if parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split(
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

        if parsed.path == "/watch":
            params = parse_qs(
                parsed.query
            )

            if "v" in params:
                video_id = params["v"][0]

                if video_id:
                    return video_id

        if parsed.path.startswith("/embed/"):
            video_id = parsed.path.split(
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


def get_snippet(result):
    snippet_element = result.select_one(
        ".result__snippet"
    )

    if not snippet_element:
        return ""

    return snippet_element.get_text(
        " ",
        strip=True
    )


def get_result_title(result):
    title_element = result.select_one(
        ".result__title a"
    )

    if not title_element:
        return ""

    return title_element.get_text(
        " ",
        strip=True
    )


def get_result_url(result):
    title_element = result.select_one(
        ".result__title a"
    )

    if not title_element:
        return ""

    return title_element.get(
        "href",
        ""
    )


def search_duckduckgo(
    query,
    max_results=20
):
    search_queries = [
        f"{query} site:youtube.com/shorts",
        f"{query} YouTube Shorts"
    ]

    all_results = []

    seen_urls = set()

    for search_query in search_queries:
        encoded_query = quote(
            search_query
        )

        url = (
            "https://html.duckduckgo.com/html/"
            f"?q={encoded_query}"
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        page_results = soup.select(
            ".result"
        )

        for result in page_results:
            title = get_result_title(
                result
            )

            raw_url = get_result_url(
                result
            )

            snippet = get_snippet(
                result
            )

            if not raw_url:
                continue

            youtube_url = extract_youtube_url(
                raw_url
            )

            if not youtube_url:
                continue

            normalized_url = youtube_url.strip()

            if normalized_url in seen_urls:
                continue

            seen_urls.add(
                normalized_url
            )

            video_id = extract_video_id(
                normalized_url
            )

            if not video_id:
                continue

            explicit_shorts = (
                is_explicit_shorts_url(
                    normalized_url
                )
            )

            result_data = {
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
                "source_url": normalized_url,
                "is_explicit_shorts": explicit_shorts
            }

            all_results.append(
                result_data
            )

            if len(all_results) >= max_results:
                return all_results

    return all_results


def search_duckduckgo_shorts(
    query,
    max_results=20
):
    search_queries = [
        f"{query} site:youtube.com/shorts",
        f"{query} YouTube Shorts",
        f"{query} shorts youtube"
    ]

    results = []

    used_video_ids = set()

    for search_query in search_queries:
        url = (
            "https://html.duckduckgo.com/html/"
            f"?q={quote(search_query)}"
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        result_elements = soup.select(
            ".result"
        )

        for result in result_elements:
            title = get_result_title(
                result
            )

            raw_url = get_result_url(
                result
            )

            snippet = get_snippet(
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

            if video_id in used_video_ids:
                continue

            explicit_shorts = (
                is_explicit_shorts_url(
                    youtube_url
                )
            )

            if not explicit_shorts:
                combined_text = (
                    f"{title} {snippet} "
                    f"{youtube_url}"
                ).lower()

                shorts_keywords = [
                    "shorts",
                    "short",
                    "ショート",
                    "youtube shorts"
                ]

                has_shorts_keyword = any(
                    keyword in combined_text
                    for keyword in shorts_keywords
                )

                if not has_shorts_keyword:
                    continue

            used_video_ids.add(
                video_id
            )

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
        "endpoint": "/api/search?q=検索ワード",
        "type": "youtube_shorts"
    }


@app.get("/api/search")
def api_search(
    q: str = Query(
        ...,
        min_length=1
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
            "count": 0,
            "results": [],
            "error": "検索ワードが空です"
        }

    try:
        results = search_duckduckgo_shorts(
            query,
            limit
        )

        return {
            "success": True,
            "query": query,
            "type": "youtube_shorts",
            "count": len(results),
            "results": results
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "query": query,
            "type": "youtube_shorts",
            "count": 0,
            "results": [],
            "error": "DuckDuckGoへのアクセスがタイムアウトしました"
        }

    except requests.exceptions.HTTPError as e:
        return {
            "success": False,
            "query": query,
            "type": "youtube_shorts",
            "count": 0,
            "results": [],
            "error": (
                "DuckDuckGoからHTTPエラーが返されました: "
                f"{str(e)}"
            )
        }

    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "query": query,
            "type": "youtube_shorts",
            "count": 0,
            "results": [],
            "error": (
                "DuckDuckGoへのリクエストに失敗しました: "
                f"{str(e)}"
            )
        }

    except Exception as e:
        return {
            "success": False,
            "query": query,
            "type": "youtube_shorts",
            "count": 0,
            "results": [],
            "error": str(e)
        }


@app.get("/api/debug")
def api_debug(
    q: str = Query(
        ...,
        min_length=1
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

    search_query = (
        f"{query} YouTube Shorts"
    )

    url = (
        "https://html.duckduckgo.com/html/"
        f"?q={quote(search_query)}"
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        for result in soup.select(
            ".result"
        ):
            title = get_result_title(
                result
            )

            raw_url = get_result_url(
                result
            )

            snippet = get_snippet(
                result
            )

            youtube_url = extract_youtube_url(
                raw_url
            )

            video_id = extract_video_id(
                youtube_url
            )

            results.append({
                "title": title,
                "raw_url": raw_url,
                "youtube_url": youtube_url,
                "video_id": video_id,
                "is_shorts": (
                    is_explicit_shorts_url(
                        youtube_url
                    )
                ),
                "snippet": snippet
            })

        return {
            "success": True,
            "query": query,
            "duckduckgo_query": search_query,
            "result_count": len(results),
            "results": results
        }

    except Exception as e:
        return {
            "success": False,
            "query": query,
            "results": [],
            "error": str(e)
        }
