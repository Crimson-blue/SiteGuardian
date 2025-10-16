from urllib.parse import urlparse, urljoin
from pathlib import Path
from hashlib import sha256
from datetime import datetime
import re
from bs4 import BeautifulSoup

def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower()

def is_internal_link(base_domain: str, url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.lower() == base_domain)

def timestamp_str() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")

def file_sha256(data: bytes) -> str:
    h = sha256()
    h.update(data)
    return h.hexdigest()

def ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

def sanitize_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", name)

def url_to_relpath(base_url: str, full_url: str) -> Path:
    """
    Map URL to a relative path within snapshot.
    - Directories => index.html
    - No extension => index.html
    - Assets stored as given (respect extension)
    """
    parsed = urlparse(full_url)
    p = parsed.path
    if p.endswith("/"):
        p = p + "index.html"
    elif "." not in Path(p).name:
        # Likely no extension, treat as directory page
        p = Path(p) / "index.html"
        p = str(p)
    # Remove leading slash
    if p.startswith("/"):
        p = p[1:]
    # Query string hashed into filename for uniqueness
    if parsed.query:
        stem = Path(p).stem
        suffix = Path(p).suffix
        qhash = sanitize_filename(parsed.query)[:32]
        p = str(Path(Path(p).parent) / f"{stem}__{qhash}{suffix or '.html'}")
    return Path(p)

def rewrite_html_links(soup: BeautifulSoup, url_map: dict[str, Path], base_url: str):
    """
    Rewrite href/src to local rel paths for downloaded files.
    """
    for tag, attr in [("a", "href"), ("img", "src"), ("link", "href"), ("script", "src")]:
        for el in soup.find_all(tag):
            link = el.get(attr)
            if not link:
                continue
            abs_url = urljoin(base_url, link)
            if abs_url in url_map:
                el[attr] = str(url_map[abs_url])
    return soup