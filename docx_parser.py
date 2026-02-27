import os
import re
import mammoth


def parse_docx(file_path):
    try:
        with open(file_path, "rb") as f:
            result = mammoth.convert_to_html(f)

        html = result.value
        warnings = [str(m) for m in result.messages]

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


def _extract_title_and_body(html):
    match = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL)
    if match:
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        body = (html[: match.start()] + html[match.end() :]).strip()
        return title, body
    return "", html.strip()
