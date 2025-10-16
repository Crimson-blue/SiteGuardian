import logging
from urllib.parse import urljoin, urlparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from core.utils import domain_from_url, is_internal_link, url_to_relpath, ensure_dir, file_sha256, rewrite_html_links

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "SiteGuardian/1.0 (+https://example.com)"
}

@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_random_exponential(multiplier=1, max=30),
       retry=retry_if_exception_type((RequestException, Timeout, ConnectionError)))
def fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp

def extract_links(html: str, base_url: str, include_assets: dict) -> tuple[set[str], dict[str, list[str]]]:
    """
    Returns: (internal_page_links, assets_by_page)
    assets_by_page: {"images": [...], "css": [...], "js": [...]}
    """
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    assets = {"images": [], "css": [], "js": []}
    for a in soup.find_all("a", href=True):
        abs_url = urljoin(base_url, a["href"])
        links.add(abs_url)

    if include_assets.get("images", True):
        for img in soup.find_all("img", src=True):
            assets["images"].append(urljoin(base_url, img["src"]))
    if include_assets.get("css", True):
        for l in soup.find_all("link", href=True):
            if l.get("rel") and "stylesheet" in [r.lower() for r in l.get("rel")]:
                assets["css"].append(urljoin(base_url, l["href"]))
    if include_assets.get("js", True):
        for s in soup.find_all("script", src=True):
            assets["js"].append(urljoin(base_url, s["src"]))
    # Filter unique
    for k in assets:
        assets[k] = list(dict.fromkeys(assets[k]))
    return links, assets

def save_file(dest_root: Path, rel_path: Path, content: bytes) -> tuple[int, str]:
    full_path = dest_root / rel_path
    ensure_dir(full_path)
    full_path.write_bytes(content)
    return full_path.stat().st_size, file_sha256(content)

def crawl_website(base_url: str, dest_root: Path, depth: int, include_assets: dict, max_workers: int,
                  progress_cb=None) -> tuple[list[dict], dict[str, Path]]:
    """
    BFS crawl up to depth; return list of file records and url->relpath map
    """
    base_domain = domain_from_url(base_url)
    visited_pages = set()
    to_visit = deque([base_url])
    url_map: dict[str, Path] = {}
    files_meta: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for current_depth in range(depth + 1):
            if not to_visit:
                break
            batch = list({u for u in list(to_visit) if is_internal_link(base_domain, u)})
            to_visit.clear()

            futures = {executor.submit(fetch, url): url for url in batch if url not in visited_pages}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    resp = future.result()
                    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    text = resp.text if "html" in content_type or content_type == "" else ""
                    raw = resp.content

                    # Decide rel path for page
                    rel_path = url_to_relpath(base_url, url)
                    if not rel_path.suffix:
                        rel_path = rel_path.with_suffix(".html")
                    # If not html, treat as binary asset
                    if "html" not in content_type and rel_path.suffix.lower() not in (".html", ".htm"):
                        size, h = save_file(dest_root, rel_path, raw)
                        url_map[url] = rel_path
                        files_meta.append({
                            "url": url, "rel_path": str(rel_path), "size": size,
                            "sha256": h, "content_type": content_type
                        })
                        if progress_cb: progress_cb(url, 'asset', len(files_meta))
                        continue

                    # Parse page
                    links, assets = extract_links(text, url, {
                        "images": include_assets.get("images", True),
                        "css": include_assets.get("css", True),
                        "js": include_assets.get("js", True),
                    })

                    # Save page with rewritten links (only for downloaded URLs)
                    soup = BeautifulSoup(text, "html.parser")
                    # Tentatively map this url to rel_path for eventual rewrite
                    url_map[url] = rel_path

                    # Save assets (sequentially to simplify)
                    for group in ["images", "css", "js"]:
                        for asset_url in assets[group]:
                            if not is_internal_link(base_domain, asset_url):
                                continue
                            try:
                                a_resp = fetch(asset_url)
                                a_raw = a_resp.content
                                a_content_type = a_resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                                a_rel = url_to_relpath(base_url, asset_url)
                                size, h = save_file(dest_root, a_rel, a_raw)
                                url_map[asset_url] = a_rel
                                files_meta.append({
                                    "url": asset_url, "rel_path": str(a_rel), "size": size, "sha256": h, "content_type": a_content_type
                                })
                            except Exception as e:
                                logger.warning(f"Asset fetch failed: {asset_url}: {e}")

                    # Rewrite links for known URL map
                    soup = rewrite_html_links(soup, url_map, url)
                    html_bytes = soup.prettify("utf-8")
                    size, h = save_file(dest_root, rel_path, html_bytes)
                    files_meta.append({
                        "url": url, "rel_path": str(rel_path), "size": size, "sha256": h, "content_type": "text/html"
                    })
                    visited_pages.add(url)
                    if progress_cb: progress_cb(url, 'page', len(files_meta))

                    # Enqueue next-level links
                    if current_depth < depth:
                        for link in links:
                            if is_internal_link(base_domain, link) and link not in visited_pages:
                                to_visit.append(link)

                except Exception as e:
                    logger.warning(f"Fetch failed: {url}: {e}")
    return files_meta, url_map