# WordPress Publisher

Desktop application for bulk publishing blog posts to WordPress sites from DOCX files.

## Features

- Manage multiple WordPress sites (add / remove / test connection)
- Bulk upload DOCX files — each file becomes a blog post
- H1 heading in DOCX = post title, remaining content = post body
- Assign category and author per article (fetched from WordPress)
- Choose between Draft and Published status
- Progress bar during publishing
- Report with URLs of all created posts

## Requirements

- Python 3.8+
- WordPress sites with [Application Passwords](https://make.wordpress.org/core/2020/11/05/application-passwords-integration-guide/) enabled (built-in since WP 5.6, requires HTTPS)

## Installation

```bash
git clone https://github.com/pawgar/wordpress-publisher.git
cd wordpress-publisher
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

1. **Add a WordPress site** — click "+ Add Site", enter name, URL, username, and application password
2. **Select the target site** from the dropdown
3. **Load DOCX files** — click "Select DOCX Files..." and choose one or more .docx files
4. **Configure articles** — assign category and author for each article (or use bulk assign)
5. **Choose status** — Draft or Published
6. **Click "Publish All"** — wait for the progress bar to complete
7. **Review the report** — copy URLs of published posts

## How to generate a WordPress Application Password

1. Log in to your WordPress admin panel
2. Go to **Users → Profile**
3. Scroll down to **Application Passwords**
4. Enter a name (e.g. "WordPress Publisher") and click **Add New Application Password**
5. Copy the generated password and use it in the app

## Security note

Site credentials are stored in `config.json` in the application directory. Keep this file secure and do not share it.
