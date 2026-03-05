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
        html = _strip_bold_from_headings(html)
        title, body = _extract_title_and_body(html)

        # Validation warnings
        filename = os.path.basename(file_path)
        if not title:
            title = os.path.splitext(filename)[0]
            warnings.append(f"[{filename}] No H1 found — using filename as title.")

        plain_text = re.sub(r"<[^>]+>", "", body).strip()
        if not plain_text:
            warnings.append(f"[{filename}] Document body is empty — no text content found.")

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


def _strip_bold_from_headings(html):
    """Remove all bold/strong formatting from inside heading tags (h1-h6).

    Handles: <strong>, <b>, <span style="font-weight:bold">,
    <span style="font-weight:700">, and nested combinations.
    """
    def _remove_bold_tags(match):
        tag = match.group(1)       # e.g. "h2"
        attrs = match.group(2) or ""  # any attributes on the heading tag
        content = match.group(3)   # inner HTML
        # Remove <strong>...</strong>
        content = re.sub(r"<strong>(.*?)</strong>", r"\1", content, flags=re.DOTALL)
        # Remove <b>...</b>
        content = re.sub(r"<b>(.*?)</b>", r"\1", content, flags=re.DOTALL)
        # Remove <span style="...font-weight:bold...">...</span>
        content = re.sub(
            r'<span[^>]*style="[^"]*font-weight\s*:\s*(bold|[7-9]\d\d)[^"]*"[^>]*>(.*?)</span>',
            r"\2", content, flags=re.DOTALL,
        )
        return f"<{tag}{attrs}>{content}</{tag}>"

    html = re.sub(
        r"<(h[1-6])(\s[^>]*)?>(.+?)</\1>",
        _remove_bold_tags,
        html,
        flags=re.DOTALL,
    )
    return html


def _extract_title_and_body(html):
    match = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL)
    if match:
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        body = (html[: match.start()] + html[match.end() :]).strip()
        return title, body
    return "", html.strip()
