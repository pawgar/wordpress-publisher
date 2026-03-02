import base64
import os
import mimetypes
import requests
from datetime import datetime, timezone, timedelta

TIMEOUT = 30


def _auth_headers(site):
    creds = f"{site['username']}:{site['app_password']}"
    token = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _auth_header_only(site):
    """Auth header without Content-Type (for multipart uploads)."""
    creds = f"{site['username']}:{site['app_password']}"
    token = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {token}"}


def _api_url(site, endpoint):
    return f"{site['url']}/wp-json/wp/v2/{endpoint}"


def test_connection(site):
    try:
        r = requests.get(
            _api_url(site, "users/me"),
            headers=_auth_headers(site),
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            name = r.json().get("name", "Unknown")
            return True, f"Connected as: {name}"
        else:
            msg = r.json().get("message", r.text)
            return False, f"HTTP {r.status_code}: {msg}"
    except requests.exceptions.ConnectionError:
        return False, f"Cannot connect to {site['url']}. Check the URL."
    except requests.exceptions.Timeout:
        return False, "Connection timed out."
    except Exception as e:
        return False, str(e)


def _fetch_paginated(site, endpoint):
    items = []
    page = 1
    while True:
        r = requests.get(
            _api_url(site, endpoint),
            headers=_auth_headers(site),
            params={"per_page": 100, "page": page},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            break
        data = r.json()
        if not data:
            break
        items.extend(data)
        total_pages = int(r.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1
    return items


def fetch_categories(site):
    raw = _fetch_paginated(site, "categories")
    return [{"id": c["id"], "name": c["name"]} for c in raw]


def fetch_users(site):
    raw = _fetch_paginated(site, "users")
    return [{"id": u["id"], "name": u["name"]} for u in raw]


def upload_media(site, file_path):
    """Upload an image to WP Media Library. Returns media ID or error."""
    filename = os.path.basename(file_path)
    mime_type = mimetypes.guess_type(file_path)[0] or "image/jpeg"

    try:
        with open(file_path, "rb") as f:
            file_data = f.read()

        headers = _auth_header_only(site)
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        headers["Content-Type"] = mime_type

        r = requests.post(
            _api_url(site, "media"),
            headers=headers,
            data=file_data,
            timeout=60,
        )
        if r.status_code == 201:
            return {"success": True, "media_id": r.json().get("id")}
        else:
            msg = r.json().get("message", r.text)
            return {"success": False, "error": f"HTTP {r.status_code}: {msg}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_wp_gmt_offset(site):
    """Fetch the GMT offset configured in WordPress settings."""
    try:
        r = requests.get(f"{site['url']}/wp-json/", timeout=TIMEOUT)
        if r.status_code == 200:
            return float(r.json().get("gmt_offset", 0))
    except Exception:
        pass
    return 0


def _convert_to_wp_time(local_date_str, wp_gmt_offset):
    """Convert local date string to WordPress server time.

    Takes a date string from the GUI (user's local time) and adjusts it
    to match the WordPress timezone so posts publish at the expected time.
    """
    local_dt = datetime.fromisoformat(local_date_str)
    local_offset = datetime.now(timezone.utc).astimezone().utcoffset()
    local_offset_hours = local_offset.total_seconds() / 3600
    diff_hours = wp_gmt_offset - local_offset_hours
    wp_dt = local_dt + timedelta(hours=diff_hours)
    return wp_dt.isoformat()


def create_post(site, title, content, status, category_id, author_id,
                featured_media_id=None, publish_date=None, wp_gmt_offset=None,
                slug=None):
    if wp_gmt_offset is None:
        wp_gmt_offset = _get_wp_gmt_offset(site)

    if publish_date:
        date_value = _convert_to_wp_time(publish_date, wp_gmt_offset)
    else:
        date_value = _convert_to_wp_time(datetime.now().isoformat(), wp_gmt_offset)

    payload = {
        "title": title,
        "content": content,
        "status": status,
        "categories": [category_id],
        "author": author_id,
        "date": date_value,
    }
    if featured_media_id:
        payload["featured_media"] = featured_media_id
    if slug:
        payload["slug"] = slug

    try:
        r = requests.post(
            _api_url(site, "posts"),
            headers=_auth_headers(site),
            json=payload,
            timeout=TIMEOUT,
        )
        if r.status_code == 201:
            data = r.json()
            return {"success": True, "url": data.get("link", ""), "id": data.get("id")}
        else:
            msg = r.json().get("message", r.text)
            return {"success": False, "error": f"HTTP {r.status_code}: {msg}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
