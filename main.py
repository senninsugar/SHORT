from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urlparse, parse_qs

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
        "Chrome/139.0.0.0 Safari/537.36"
    )
}


def extract_youtube_url(url):
    try:
        parsed = urlparse(url)

        if parsed.hostname in [
            "www.youtube.com",
            "youtube.com",
            "m.youtube.com"
        ]:
            return url

        if parsed.hostname == "duckduckgo.com":
            query = parse_qs(parsed.query)

            if "uddg" in query:
                decoded_url = query["uddg"][0]
                decoded_parsed = urlparse(decoded_url)

                if decoded_parsed.hostname in [
                    "www.youtube.com",
                    "youtube.com",
                    "m.youtube.com"
                ]:
                    return decoded_url

    except Exception:
        pass

    return None


def is_youtube_shorts(url):
    if not url:
        return False

    parsed = urlparse(url)

    if parsed.hostname not in [
        "www.youtube.com",
        "youtube.com",
        "m.youtube.com"
    ]:
        return False

    return parsed.path.startswith("/shorts/")


def search_duckduckgo_shorts(query, max_results=20):
    search_query = f"{query} site:youtube.com/shorts"

    url = (
        "https://html.duckduckgo.com/html/"
        f"?q={quote(search_query)}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=15
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    results = []
    used_video_ids = set()

    for result in soup.select(".result"):
        title_element = result.select_one(
            ".result__title a"
        )

        snippet_element = result.select_one(
            ".result__snippet"
        )

        if not title_element:
            continue

        title = title_element.get_text(
            " ",
            strip=True
        )

        raw_url = title_element.get(
            "href",
            ""
        )

        youtube_url = extract_youtube_url(
            raw_url
        )

        if not youtube_url:
            continue

        if not is_youtube_shorts(
            youtube_url
        ):
            continue

        parsed = urlparse(youtube_url)

        video_id = parsed.path.split(
            "/shorts/",
            1
        )[-1].split("/")[0]

        if not video_id:
            continue

        if video_id in used_video_ids:
            continue

        used_video_ids.add(video_id)

        snippet = ""

        if snippet_element:
            snippet = snippet_element.get_text(
                " ",
                strip=True
            )

        results.append({
            "title": title,
            "url": youtube_url,
            "video_id": video_id,
            "thumbnail": (
                "https://i.ytimg.com/vi/"
                f"{video_id}/hqdefault.jpg"
            ),
            "snippet": snippet,
            "type": "youtube_short"
        })

        if len(results) >= max_results:
            break

    return results


@app.get("/")
def index():
    return {
        "name": "YouTube Shorts Search API",
        "status": "online",
        "endpoint": "/api/search?q=検索ワード"
    }


@app.get("/api/search")
def api_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(
        20,
        ge=1,
        le=50
    )
):
    try:
        results = search_duckduckgo_shorts(
            q,
            limit
        )

        return {
            "success": True,
            "query": q,
            "type": "youtube_shorts",
            "count": len(results),
            "results": results
        }

    except requests.RequestException as e:
        return {
            "success": False,
            "query": q,
            "type": "youtube_shorts",
            "count": 0,
            "results": [],
            "error": str(e)
        }

    except Exception as e:
        return {
            "success": False,
            "query": q,
            "type": "youtube_shorts",
            "count": 0,
            "results": [],
            "error": str(e)
        }
