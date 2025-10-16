import difflib
from pathlib import Path
import html

def generate_html_diff(old_path: Path, new_path: Path, title: str = "HTML Diff") -> str:
    """
    Generate color-coded HTML diff using difflib.HtmlDiff
    """
    old_text = old_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    new_text = new_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    diff = difflib.HtmlDiff(wrapcolumn=120).make_file(old_text, new_text, fromdesc=str(old_path.name), todesc=str(new_path.name))
    # Add a minimal style for readability
    return f"""
<!doctype html>
<html><head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
table.diff {{font-family: monospace; font-size: 12px; border: 1px solid #ccc;}}
.diff_add {{background: #e6ffe6;}}
.diff_chg {{background: #fff7cc;}}
.diff_sub {{background: #ffe6e6;}}
</style>
</head><body>
{diff}
</body></html>
"""