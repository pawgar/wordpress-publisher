import os
import re
import mammoth


def parse_docx(file_path):
    try:
        with open(file_path, "rb") as f:
            result = mammoth.convert_to_html(f)

        html = result.value
        warnings = [str(m) for m in result.messages]

        html = _clean_html(html)
        title, body = _extract_title_and_body(html)

        if not title:
            title = os.path.splitext(os.path.basename(file_path))[0]

        return {
            "success": True,
            "title": title,
            "html_body": body,
            "warnings": warnings,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Cannot parse {os.path.basename(file_path)}: {e}",
        }


def _clean_html(html):
    """Remove class, id, style and data-* attributes from all HTML tags."""
    html = re.sub(r'\s+class="[^"]*"', "", html)
    html = re.sub(r"\s+class='[^']*'", "", html)
    html = re.sub(r'\s+id="[^"]*"', "", html)
    html = re.sub(r"\s+id='[^']*'", "", html)
    html = re.sub(r'\s+style="[^"]*"', "", html)
    html = re.sub(r"\s+style='[^']*'", "", html)
    html = re.sub(r'\s+data-[a-z-]+="[^"]*"', "", html)
    html = re.sub(r"\s+data-[a-z-]+'[^']*'", "", html)

    # Remove empty span tags left after stripping attributes
    html = re.sub(r"<span>(.*?)</span>", r"\1", html)

    # Collapse multiple whitespace
    html = re.sub(r"\n\s*\n", "\n", html)

    return html.strip()


def _extract_title_and_body(html):
    match = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL)
    if match:
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        body = (html[: match.start()] + html[match.end() :]).strip()
        return title, body
    return "", html.strip()
