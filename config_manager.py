import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"sites": []}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"sites": []}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_sites():
    return load_config().get("sites", [])


def get_site_by_name(name):
    for site in get_sites():
        if site["name"] == name:
            return site
    return None


def add_site(name, url, username, app_password):
    config = load_config()
    url = url.rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    config["sites"].append({
        "name": name,
        "url": url,
        "username": username,
        "app_password": app_password,
    })
    save_config(config)


def remove_site(name):
    config = load_config()
    config["sites"] = [s for s in config["sites"] if s["name"] != name]
    save_config(config)


def get_gemini_key():
    return load_config().get("gemini_api_key", "")


def set_gemini_key(key):
    config = load_config()
    config["gemini_api_key"] = key
    save_config(config)
