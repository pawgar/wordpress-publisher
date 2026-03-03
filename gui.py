import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
import re
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from PIL import Image, ImageTk

import config_manager
import wp_api
import docx_parser
import gemini_api
import image_optimizer

# Try to import drag-and-drop support
try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _title_to_slug(title):
    """Generate a URL-friendly slug from a title."""
    slug = title.lower().strip()
    # Transliterate common Polish characters
    pl_map = {
        "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n",
        "ó": "o", "ś": "s", "ź": "z", "ż": "z",
        "Ą": "a", "Ć": "c", "Ę": "e", "Ł": "l", "Ń": "n",
        "Ó": "o", "Ś": "s", "Ź": "z", "Ż": "z",
    }
    for src, dst in pl_map.items():
        slug = slug.replace(src, dst)
    # Replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def _generate_random_dates(count, date_from_str, date_to_str):
    """Generate `count` random datetimes between date_from and date_to.

    Input format: 'YYYY-MM-DD' for dates.
    Returns sorted list of 'YYYY-MM-DD HH:MM' strings.
    """
    try:
        dt_from = datetime.strptime(date_from_str, "%Y-%m-%d")
        dt_to = datetime.strptime(date_to_str, "%Y-%m-%d").replace(hour=23, minute=59)
    except ValueError:
        return []

    if dt_to <= dt_from:
        return []

    total_minutes = int((dt_to - dt_from).total_seconds() / 60)
    dates = []
    for _ in range(count):
        rand_minutes = random.randint(0, total_minutes)
        dt = dt_from + timedelta(minutes=rand_minutes)
        # Clamp to 6:00 - 23:00 range for realistic publishing hours
        if dt.hour < 6:
            dt = dt.replace(hour=random.randint(6, 22), minute=random.randint(0, 59))
        elif dt.hour > 22:
            dt = dt.replace(hour=random.randint(6, 22), minute=random.randint(0, 59))
        dates.append(dt)

    dates.sort()
    return [d.strftime("%Y-%m-%d %H:%M") for d in dates]


class WordPressPublisherApp:
    def __init__(self, root):
        self.root = root
        self.articles = []
        self.categories = []
        self.users = []
        self.selected_site = None
        self._rows = []
        self._last_results = []

        self._build_ui()
        self._refresh_sites_dropdown()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        self._build_sites_section(main)
        self._build_load_section(main)
        self._build_config_section(main)
        self._build_publish_section(main)
        self._build_report_section(main)

    # --- Section 1: WordPress Sites ---
    def _build_sites_section(self, parent):
        frame = ttk.LabelFrame(parent, text="1. WordPress Sites", padding=8)
        frame.pack(fill="x", pady=(0, 6))

        row = ttk.Frame(frame)
        row.pack(fill="x")

        ttk.Label(row, text="Site:").pack(side="left")
        self.site_var = tk.StringVar()
        self.site_combo = ttk.Combobox(row, textvariable=self.site_var, state="readonly", width=30)
        self.site_combo.pack(side="left", padx=(4, 8))
        self.site_combo.bind("<<ComboboxSelected>>", self._on_site_selected)

        ttk.Button(row, text="+ Add Site", command=self._add_site_dialog).pack(side="left", padx=2)
        ttk.Button(row, text="Edit Site", command=self._edit_site_dialog).pack(side="left", padx=2)
        ttk.Button(row, text="- Remove Site", command=self._remove_site).pack(side="left", padx=2)
        ttk.Button(row, text="Test Connection", command=self._test_connection).pack(side="left", padx=2)

        # Spacer
        ttk.Frame(row, width=20).pack(side="left")
        ttk.Button(row, text="Gemini API Key", command=self._gemini_key_dialog).pack(side="left", padx=2)

    # --- Section 2: Load Articles ---
    def _build_load_section(self, parent):
        frame = ttk.LabelFrame(parent, text="2. Load Articles", padding=8)
        frame.pack(fill="x", pady=(0, 6))

        row = ttk.Frame(frame)
        row.pack(fill="x")

        ttk.Button(row, text="Select DOCX Files...", command=self._select_files).pack(side="left")
        self.load_status = ttk.Label(row, text="No files loaded")
        self.load_status.pack(side="left", padx=10)

    # --- Section 3: Article Configuration ---
    def _build_config_section(self, parent):
        frame = ttk.LabelFrame(parent, text="3. Article Configuration", padding=8)
        frame.pack(fill="both", expand=True, pady=(0, 6))

        # Row 1: Status + bulk assign
        top_row = ttk.Frame(frame)
        top_row.pack(fill="x", pady=(0, 4))

        ttk.Label(top_row, text="Publish as:").pack(side="left")
        self.status_var = tk.StringVar(value="publish")
        ttk.Radiobutton(top_row, text="Draft", variable=self.status_var, value="draft").pack(side="left", padx=(8, 4))
        ttk.Radiobutton(top_row, text="Published", variable=self.status_var, value="publish").pack(side="left", padx=(0, 20))

        ttk.Label(top_row, text="Set all categories:").pack(side="left")
        self.bulk_cat_var = tk.StringVar()
        self.bulk_cat_combo = ttk.Combobox(top_row, textvariable=self.bulk_cat_var, state="readonly", width=18)
        self.bulk_cat_combo.pack(side="left", padx=(4, 12))
        self.bulk_cat_combo.bind("<<ComboboxSelected>>", self._bulk_set_categories)

        ttk.Label(top_row, text="Set all authors:").pack(side="left")
        self.bulk_author_var = tk.StringVar()
        self.bulk_author_combo = ttk.Combobox(top_row, textvariable=self.bulk_author_var, state="readonly", width=18)
        self.bulk_author_combo.pack(side="left", padx=4)
        self.bulk_author_combo.bind("<<ComboboxSelected>>", self._bulk_set_authors)

        # Row 2: Random date scheduling
        sched_row = ttk.Frame(frame)
        sched_row.pack(fill="x", pady=(0, 6))

        ttk.Label(sched_row, text="Schedule dates from:").pack(side="left")
        self.sched_from_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(sched_row, textvariable=self.sched_from_var, width=12).pack(side="left", padx=(4, 8))

        ttk.Label(sched_row, text="to:").pack(side="left")
        self.sched_to_var = tk.StringVar(value=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"))
        ttk.Entry(sched_row, textvariable=self.sched_to_var, width=12).pack(side="left", padx=(4, 8))

        ttk.Button(sched_row, text="Randomize Dates", command=self._randomize_dates).pack(side="left", padx=4)

        # Scrollable table using Treeview for resizable columns
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill="both", expand=True)

        columns = ("num", "title", "slug", "category", "author", "image", "date")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)

        self.tree.heading("num", text="#")
        self.tree.heading("title", text="Title (dbl-click edit)")
        self.tree.heading("slug", text="Slug (dbl-click edit)")
        self.tree.heading("category", text="Category")
        self.tree.heading("author", text="Author")
        self.tree.heading("image", text="Image (dbl-click / drop)")
        self.tree.heading("date", text="Date")

        self.tree.column("num", width=35, minwidth=30, stretch=False)
        self.tree.column("title", width=240, minwidth=120)
        self.tree.column("slug", width=200, minwidth=100)
        self.tree.column("category", width=120, minwidth=70)
        self.tree.column("author", width=120, minwidth=70)
        self.tree.column("image", width=220, minwidth=100)
        self.tree.column("date", width=130, minwidth=100)

        scrollbar_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        # Enable drag-and-drop for images
        if HAS_DND:
            self.tree.drop_target_register(DND_FILES)
            self.tree.dnd_bind("<<Drop>>", self._on_tree_drop)

        # Bulk image generation row
        img_row = ttk.Frame(frame)
        img_row.pack(fill="x", pady=(4, 0))
        ttk.Button(img_row, text="Generate All Images (Gemini)",
                   command=self._generate_all_images).pack(side="left")

    # --- Section 4: Publish ---
    def _build_publish_section(self, parent):
        frame = ttk.LabelFrame(parent, text="4. Publish", padding=8)
        frame.pack(fill="x", pady=(0, 6))

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 4))

        row = ttk.Frame(frame)
        row.pack(fill="x")

        self.btn_publish = ttk.Button(row, text="Publish All", command=self._publish_all)
        self.btn_publish.pack(side="left")

        self.btn_clear = ttk.Button(row, text="Clear", command=self._clear_workspace)
        self.btn_clear.pack(side="left", padx=(8, 0))

        self.progress_label = ttk.Label(row, text="")
        self.progress_label.pack(side="left", padx=10)

    # --- Section 5: Report ---
    def _build_report_section(self, parent):
        frame = ttk.LabelFrame(parent, text="5. Report", padding=8)
        frame.pack(fill="both", expand=True)

        self.report_text = tk.Text(frame, height=6, state="disabled", wrap="word")
        self.report_text.pack(fill="both", expand=True, side="left")

        report_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.report_text.yview)
        report_scroll.pack(side="right", fill="y")
        self.report_text.configure(yscrollcommand=report_scroll.set)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Copy URLs", command=self._copy_urls).pack(side="right")
        self.btn_retry = ttk.Button(btn_frame, text="Retry Failed", command=self._retry_failed)
        self.btn_retry.pack(side="right", padx=(0, 8))

    # ---------------------------------------------------------- Site mgmt
    def _refresh_sites_dropdown(self):
        sites = config_manager.get_sites()
        names = [s["name"] for s in sites]
        self.site_combo["values"] = names
        if names and not self.site_var.get():
            self.site_combo.current(0)
            self._on_site_selected(None)

    def _on_site_selected(self, _event):
        name = self.site_var.get()
        self.selected_site = config_manager.get_site_by_name(name)
        if self.selected_site:
            threading.Thread(target=self._fetch_wp_data, daemon=True).start()

    def _fetch_wp_data(self):
        site = self.selected_site
        try:
            self.categories = wp_api.fetch_categories(site)
            self.users = wp_api.fetch_users(site)
        except Exception:
            self.categories = []
            self.users = []
        self.root.after(0, self._update_wp_dropdowns)

    def _update_wp_dropdowns(self):
        cat_names = [c["name"] for c in self.categories]
        user_names = [u["name"] for u in self.users]

        self.bulk_cat_combo["values"] = cat_names
        self.bulk_author_combo["values"] = user_names

        for row in self._rows:
            if not cat_names:
                row["category"] = ""
            elif row["category"] not in cat_names:
                row["category"] = cat_names[0]
            if not user_names:
                row["author"] = ""
            elif row["author"] not in user_names:
                row["author"] = user_names[0]

        self._sync_rows_to_tree()

    def _add_site_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Add WordPress Site")
        dlg.geometry("400x220")
        dlg.resizable(False, False)
        dlg.grab_set()

        fields = {}
        for i, (label, show) in enumerate([
            ("Name:", None), ("URL:", None),
            ("Username:", None), ("App Password:", "*"),
        ]):
            ttk.Label(dlg, text=label).grid(row=i, column=0, padx=10, pady=6, sticky="e")
            var = tk.StringVar()
            entry = ttk.Entry(dlg, textvariable=var, width=35, show=show or "")
            entry.grid(row=i, column=1, padx=10, pady=6)
            fields[label] = var

        def on_add():
            name = fields["Name:"].get().strip()
            url = fields["URL:"].get().strip()
            user = fields["Username:"].get().strip()
            pwd = fields["App Password:"].get().strip()
            if not all([name, url, user, pwd]):
                messagebox.showwarning("Missing fields", "All fields are required.", parent=dlg)
                return
            if config_manager.get_site_by_name(name):
                messagebox.showwarning("Duplicate", f"Site '{name}' already exists.", parent=dlg)
                return
            config_manager.add_site(name, url, user, pwd)
            self._refresh_sites_dropdown()
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.grid(row=4, column=0, columnspan=2, pady=12)
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)
        ttk.Button(btn_row, text="Add", command=on_add).pack(side="left", padx=8)

    def _edit_site_dialog(self):
        name = self.site_var.get()
        if not name:
            messagebox.showinfo("Info", "Select a site first.")
            return
        site = config_manager.get_site_by_name(name)
        if not site:
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Edit Site: {name}")
        dlg.geometry("400x220")
        dlg.resizable(False, False)
        dlg.grab_set()

        fields = {}
        defaults = [
            ("Name:", site["name"], None), ("URL:", site["url"], None),
            ("Username:", site["username"], None), ("App Password:", site["app_password"], "*"),
        ]
        for i, (label, default, show) in enumerate(defaults):
            ttk.Label(dlg, text=label).grid(row=i, column=0, padx=10, pady=6, sticky="e")
            var = tk.StringVar(value=default)
            entry = ttk.Entry(dlg, textvariable=var, width=35, show=show or "")
            entry.grid(row=i, column=1, padx=10, pady=6)
            fields[label] = var

        def on_save():
            new_name = fields["Name:"].get().strip()
            new_url = fields["URL:"].get().strip()
            new_user = fields["Username:"].get().strip()
            new_pwd = fields["App Password:"].get().strip()
            if not all([new_name, new_url, new_user, new_pwd]):
                messagebox.showwarning("Missing fields", "All fields are required.", parent=dlg)
                return
            if new_name != name and config_manager.get_site_by_name(new_name):
                messagebox.showwarning("Duplicate", f"Site '{new_name}' already exists.", parent=dlg)
                return
            config_manager.remove_site(name)
            config_manager.add_site(new_name, new_url, new_user, new_pwd)
            self.site_var.set(new_name)
            self._refresh_sites_dropdown()
            self._on_site_selected(None)
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.grid(row=4, column=0, columnspan=2, pady=12)
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)
        ttk.Button(btn_row, text="Save", command=on_save).pack(side="left", padx=8)

    def _remove_site(self):
        name = self.site_var.get()
        if not name:
            return
        if messagebox.askyesno("Remove site", f"Remove '{name}' from the list?"):
            config_manager.remove_site(name)
            self.site_var.set("")
            self.selected_site = None
            self._refresh_sites_dropdown()

    def _test_connection(self):
        if not self.selected_site:
            messagebox.showinfo("Info", "Select a site first.")
            return

        def worker():
            ok, msg = wp_api.test_connection(self.selected_site)
            self.root.after(0, lambda: (
                messagebox.showinfo("Connection OK", msg) if ok
                else messagebox.showerror("Connection Failed", msg)
            ))

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------- File loading
    def _select_files(self):
        paths = filedialog.askopenfilenames(
            title="Select DOCX files",
            filetypes=[("Word Documents", "*.docx")],
        )
        if not paths:
            return

        self.articles = []
        errors = []
        all_warnings = []
        for p in paths:
            result = docx_parser.parse_docx(p)
            if result["success"]:
                self.articles.append({
                    "file": p,
                    "title": result["title"],
                    "html_body": result["html_body"],
                    "category_id": None,
                    "author_id": None,
                })
                if result.get("warnings"):
                    all_warnings.extend(result["warnings"])
            else:
                errors.append(result["error"])

        self.load_status.config(text=f"{len(self.articles)} files loaded")

        # Show validation warnings
        if all_warnings:
            messagebox.showwarning("Validation Warnings", "\n".join(all_warnings))
        if errors:
            messagebox.showerror("Parse errors", "\n".join(errors))

        self._rebuild_article_table()

    def _rebuild_article_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        cat_names = [c["name"] for c in self.categories]
        user_names = [u["name"] for u in self.users]
        today = datetime.now().strftime("%Y-%m-%d %H:%M")

        self._rows = []
        for i, art in enumerate(self.articles):
            row_data = {
                "index": i,
                "title": art["title"],
                "slug": _title_to_slug(art["title"]),
                "category": cat_names[0] if cat_names else "",
                "author": user_names[0] if user_names else "",
                "image": "",
                "date": today,
            }
            self._rows.append(row_data)

            self.tree.insert("", "end", iid=str(i), values=(
                i + 1,
                row_data["title"],
                row_data["slug"],
                row_data["category"],
                row_data["author"],
                row_data["image"],
                row_data["date"],
            ))

    def _sync_rows_to_tree(self):
        for row in self._rows:
            i = row["index"]
            iid = str(i)
            if self.tree.exists(iid):
                self.tree.item(iid, values=(
                    i + 1,
                    row["title"],
                    row["slug"],
                    row["category"],
                    row["author"],
                    row["image"],
                    row["date"],
                ))

    # -------------------------------------------------- Tree interactions
    def _on_tree_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        col = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        if not item:
            return

        col_idx = int(col.replace("#", "")) - 1
        row_idx = int(item)
        col_names = ["num", "title", "slug", "category", "author", "image", "date"]
        col_name = col_names[col_idx] if col_idx < len(col_names) else None

        if col_name == "title":
            self._edit_cell_inline(item, col, row_idx, "title", update_slug=True)
        elif col_name == "slug":
            self._edit_cell_inline(item, col, row_idx, "slug")
        elif col_name == "category":
            self._combo_cell_inline(item, col, row_idx, "category",
                                    [c["name"] for c in self.categories])
        elif col_name == "author":
            self._combo_cell_inline(item, col, row_idx, "author",
                                    [u["name"] for u in self.users])
        elif col_name == "image":
            self._select_image_for_row(row_idx)
        elif col_name == "date":
            self._edit_cell_inline(item, col, row_idx, "date")

    def _edit_cell_inline(self, item, col, row_idx, field, update_slug=False):
        bbox = self.tree.bbox(item, col)
        if not bbox:
            return

        x, y, w, h = bbox
        current_val = self._rows[row_idx][field]

        entry = ttk.Entry(self.tree, width=w // 8)
        entry.insert(0, current_val)
        entry.select_range(0, "end")
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()

        def confirm(e=None):
            new_val = entry.get().strip()
            if new_val:
                self._rows[row_idx][field] = new_val
                if field == "title":
                    self.articles[row_idx]["title"] = new_val
                    if update_slug:
                        self._rows[row_idx]["slug"] = _title_to_slug(new_val)
                self._sync_rows_to_tree()
            entry.destroy()

        entry.bind("<Return>", confirm)
        entry.bind("<FocusOut>", confirm)
        entry.bind("<Escape>", lambda e: entry.destroy())

    def _combo_cell_inline(self, item, col, row_idx, field, values):
        bbox = self.tree.bbox(item, col)
        if not bbox:
            return

        x, y, w, h = bbox
        current_val = self._rows[row_idx][field]

        combo = ttk.Combobox(self.tree, values=values, state="readonly", width=w // 8)
        if current_val in values:
            combo.set(current_val)
        combo.place(x=x, y=y, width=w, height=h)
        combo.focus_set()

        def confirm(e=None):
            new_val = combo.get()
            if new_val:
                self._rows[row_idx][field] = new_val
                self._sync_rows_to_tree()
            combo.destroy()

        combo.bind("<<ComboboxSelected>>", confirm)
        combo.bind("<FocusOut>", confirm)
        combo.bind("<Escape>", lambda e: combo.destroy())

    def _select_image_for_row(self, row_idx):
        path = filedialog.askopenfilename(
            title="Select featured image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.gif *.webp")],
        )
        if path:
            self._rows[row_idx]["image"] = path
            self._sync_rows_to_tree()
            self._show_image_preview(path)

    def _show_image_preview(self, path):
        try:
            img = Image.open(path)
            img.thumbnail((300, 300))
            preview = tk.Toplevel(self.root)
            preview.title("Image Preview")
            preview.resizable(False, False)
            photo = ImageTk.PhotoImage(img)
            label = ttk.Label(preview, image=photo)
            label.image = photo
            label.pack(padx=5, pady=5)
            ttk.Label(preview, text=os.path.basename(path)).pack(pady=(0, 5))
            ttk.Button(preview, text="Close", command=preview.destroy).pack(pady=(0, 5))
        except Exception:
            pass

    # ------------------------------------------------- Gemini API Key
    def _gemini_key_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Gemini API Key")
        dlg.geometry("450x120")
        dlg.resizable(False, False)
        dlg.grab_set()

        ttk.Label(dlg, text="API Key:").grid(row=0, column=0, padx=10, pady=12, sticky="e")
        key_var = tk.StringVar(value=config_manager.get_gemini_key())
        ttk.Entry(dlg, textvariable=key_var, width=45, show="*").grid(row=0, column=1, padx=10, pady=12)

        def on_save():
            config_manager.set_gemini_key(key_var.get().strip())
            messagebox.showinfo("Saved", "Gemini API key saved.", parent=dlg)
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.grid(row=1, column=0, columnspan=2, pady=8)
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)
        ttk.Button(btn_row, text="Save", command=on_save).pack(side="left", padx=8)

    # -------------------------------------------- Right-click context menu
    def _on_tree_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        col = self.tree.identify_column(event.x)
        col_idx = int(col.replace("#", "")) - 1
        col_names = ["num", "title", "slug", "category", "author", "image", "date"]
        col_name = col_names[col_idx] if col_idx < len(col_names) else None

        if col_name != "image":
            return

        row_idx = int(item)
        self.tree.selection_set(item)

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Browse image...",
                         command=lambda: self._select_image_for_row(row_idx))
        menu.add_command(label="Generate with Gemini",
                         command=lambda: self._generate_image_for_row(row_idx))
        if self._rows[row_idx]["image"]:
            menu.add_command(label="Preview image",
                             command=lambda: self._show_image_preview(self._rows[row_idx]["image"]))
            menu.add_separator()
            menu.add_command(label="Clear image",
                             command=lambda: self._clear_image_for_row(row_idx))
        menu.tk_popup(event.x_root, event.y_root)

    def _clear_image_for_row(self, row_idx):
        self._rows[row_idx]["image"] = ""
        self._sync_rows_to_tree()

    # ----------------------------------------- Gemini image generation
    def _generate_image_for_row(self, row_idx):
        api_key = config_manager.get_gemini_key()
        if not api_key:
            messagebox.showwarning("No API Key",
                                   "Set your Gemini API key first (button in Sites section).")
            return

        title = self._rows[row_idx]["title"]
        self.progress_label.config(text=f"Generating image for: {title[:40]}...")
        self.btn_publish.config(state="disabled")

        def worker():
            prompt = gemini_api.build_image_prompt(title)
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_images")
            result = gemini_api.generate_image(api_key, prompt, output_dir)

            def on_done():
                self.btn_publish.config(state="normal")
                if result["success"]:
                    self._rows[row_idx]["image"] = result["path"]
                    self._sync_rows_to_tree()
                    self.progress_label.config(text=f"Image generated for: {title[:40]}")
                    self._show_image_preview(result["path"])
                else:
                    self.progress_label.config(text="")
                    messagebox.showerror("Gemini Error", result["error"])

            self.root.after(0, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _generate_all_images(self):
        if not self._rows:
            messagebox.showinfo("Info", "Load DOCX files first.")
            return

        api_key = config_manager.get_gemini_key()
        if not api_key:
            messagebox.showwarning("No API Key",
                                   "Set your Gemini API key first (button in Sites section).")
            return

        # Only generate for rows without an image
        indices = [i for i, r in enumerate(self._rows) if not r["image"].strip()]
        if not indices:
            messagebox.showinfo("Info", "All articles already have images assigned.")
            return

        self.btn_publish.config(state="disabled")
        self.progress["maximum"] = len(indices)
        self.progress["value"] = 0
        self.progress_label.config(text="Generating images...")

        def worker():
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_images")
            errors = []
            for count, idx in enumerate(indices):
                title = self._rows[idx]["title"]
                self.root.after(0, self.progress_label.config,
                                {"text": f"Generating {count + 1}/{len(indices)}: {title[:35]}..."})

                prompt = gemini_api.build_image_prompt(title)
                result = gemini_api.generate_image(api_key, prompt, output_dir)

                if result["success"]:
                    self._rows[idx]["image"] = result["path"]
                    self.root.after(0, self._sync_rows_to_tree)
                else:
                    errors.append(f"#{idx + 1} {title[:30]}: {result['error']}")

                self.root.after(0, self._update_gen_progress, count + 1, len(indices))
                time.sleep(1)  # Rate limit courtesy

            self.root.after(0, self._on_generate_all_done, len(indices), errors)

        threading.Thread(target=worker, daemon=True).start()

    def _update_gen_progress(self, value, total):
        self.progress["value"] = value
        self.progress_label.config(text=f"Generating images {value}/{total}...")

    def _on_generate_all_done(self, total, errors=None):
        self.btn_publish.config(state="normal")
        generated = sum(1 for r in self._rows if r["image"].strip())
        self.progress_label.config(text=f"Done! {generated}/{len(self._rows)} articles have images.")
        if errors:
            messagebox.showwarning("Image Generation Errors",
                                   f"{len(errors)} image(s) failed:\n\n" + "\n".join(errors))

    # ------------------------------------------------- Drag and drop
    def _on_tree_drop(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return

        row_idx = int(item)
        files = self._parse_dnd_data(event.data)

        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTS:
                self._rows[row_idx]["image"] = f
                self._sync_rows_to_tree()
                self._show_image_preview(f)
                break

    def _parse_dnd_data(self, data):
        files = []
        current = ""
        in_braces = False
        for char in data:
            if char == "{":
                in_braces = True
            elif char == "}":
                in_braces = False
                files.append(current)
                current = ""
            elif char == " " and not in_braces:
                if current:
                    files.append(current)
                    current = ""
            else:
                current += char
        if current:
            files.append(current)
        return files

    # -------------------------------------------- Bulk assign & scheduling
    def _bulk_set_categories(self, _event):
        val = self.bulk_cat_var.get()
        for row in self._rows:
            row["category"] = val
        self._sync_rows_to_tree()

    def _bulk_set_authors(self, _event):
        val = self.bulk_author_var.get()
        for row in self._rows:
            row["author"] = val
        self._sync_rows_to_tree()

    def _randomize_dates(self):
        if not self._rows:
            messagebox.showinfo("Info", "Load DOCX files first.")
            return

        date_from = self.sched_from_var.get().strip()
        date_to = self.sched_to_var.get().strip()

        dates = _generate_random_dates(len(self._rows), date_from, date_to)
        if not dates:
            messagebox.showerror("Error",
                                 "Invalid date range. Use YYYY-MM-DD format\n"
                                 "and make sure 'to' date is after 'from' date.")
            return

        for i, row in enumerate(self._rows):
            row["date"] = dates[i]
        self._sync_rows_to_tree()
        messagebox.showinfo("Done", f"Assigned {len(dates)} random dates between {date_from} and {date_to}.")

    # ------------------------------------------------------- Clear
    def _clear_workspace(self):
        self.articles = []
        self._rows = []
        self._last_results = []
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.load_status.config(text="No files loaded")
        self.progress["value"] = 0
        self.progress_label.config(text="")
        self.report_text.config(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.config(state="disabled")
        self._result_urls = []

    # --------------------------------------------------------- Publishing
    def _resolve_id(self, collection, name_key, name_val):
        for item in collection:
            if item[name_key] == name_val:
                return item["id"]
        return None

    def _publish_all(self):
        if not self.selected_site:
            messagebox.showinfo("Info", "Select a site first.")
            return
        if not self.articles:
            messagebox.showinfo("Info", "Load DOCX files first.")
            return

        for i, art in enumerate(self.articles):
            row = self._rows[i]
            art["title"] = row["title"]
            art["slug"] = row["slug"]
            art["category_id"] = self._resolve_id(self.categories, "name", row["category"])
            art["author_id"] = self._resolve_id(self.users, "name", row["author"])
            art["image_path"] = row["image"].strip()
            art["publish_date"] = row["date"].strip()

        self.btn_publish.config(state="disabled")
        self.progress["maximum"] = len(self.articles)
        self.progress["value"] = 0
        self.progress_label.config(text="Starting...")

        threading.Thread(target=self._publish_worker, daemon=True).start()

    def _publish_worker(self):
        results = []
        wp_gmt_offset = wp_api._get_wp_gmt_offset(self.selected_site)
        site = self.selected_site
        status = self.status_var.get()
        total = len(self.articles)

        # Phase 1: Optimize & upload all images in parallel
        self.root.after(0, self.progress_label.config, {"text": "Optimizing & uploading images..."})
        media_map = {}  # index -> {"media_id": ..., "warning": ...}

        articles_with_images = [
            (i, art) for i, art in enumerate(self.articles)
            if art.get("image_path") and os.path.isfile(art["image_path"])
        ]

        if articles_with_images:
            self.root.after(0, self.progress.configure,
                            {"maximum": len(articles_with_images)})

            def _upload_one(idx_art):
                idx, art = idx_art
                path = art["image_path"]
                # Optimize: compress to JPEG, strip metadata, random name
                opt = image_optimizer.optimize_for_upload(path)
                if not opt["success"]:
                    return idx, None, f"Optimization failed: {opt['error']}"
                upload_path = opt["path"]
                img_result = wp_api.upload_media(site, upload_path)
                # Clean up optimized temp file
                try:
                    if upload_path != path:
                        os.remove(upload_path)
                except OSError:
                    pass
                if img_result["success"]:
                    return idx, img_result["media_id"], ""
                else:
                    return idx, None, f"Upload failed: {img_result['error']}"

            upload_count = 0
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(_upload_one, item): item[0]
                           for item in articles_with_images}
                for future in as_completed(futures):
                    idx, media_id, warning = future.result()
                    media_map[idx] = {"media_id": media_id, "warning": warning}
                    upload_count += 1
                    self.root.after(0, self._update_upload_progress,
                                    upload_count, len(articles_with_images))

        # Mark images not found
        for i, art in enumerate(self.articles):
            if i not in media_map and art.get("image_path"):
                if not os.path.isfile(art["image_path"]):
                    media_map[i] = {"media_id": None,
                                    "warning": f"Image file not found: {art['image_path']}"}

        # Phase 2: Create posts sequentially
        self.root.after(0, self.progress.configure, {"maximum": total})
        self.root.after(0, self.progress.configure, {"value": 0})

        for i, art in enumerate(self.articles):
            featured_media_id = None
            image_warning = ""

            if i in media_map:
                featured_media_id = media_map[i]["media_id"]
                image_warning = media_map[i]["warning"]

            publish_date = None
            if art.get("publish_date"):
                try:
                    dt = datetime.strptime(art["publish_date"], "%Y-%m-%d %H:%M")
                    publish_date = dt.isoformat()
                except ValueError:
                    publish_date = None

            result = wp_api.create_post(
                site=site,
                title=art["title"],
                content=art["html_body"],
                status=status,
                category_id=art["category_id"],
                author_id=art["author_id"],
                featured_media_id=featured_media_id,
                publish_date=publish_date,
                wp_gmt_offset=wp_gmt_offset,
                slug=art.get("slug"),
            )
            result["image_warning"] = image_warning
            results.append({"title": art["title"], "index": i, **result})
            self.root.after(0, self._update_progress, i + 1)

        self.root.after(0, self._show_report, results)

    def _update_upload_progress(self, value, total):
        self.progress["value"] = value
        self.progress_label.config(text=f"Uploading images {value}/{total}...")

    def _update_progress(self, value):
        self.progress["value"] = value
        self.progress_label.config(text=f"Publishing {value}/{len(self.articles)}...")

    def _show_report(self, results):
        self.btn_publish.config(state="normal")
        self.progress_label.config(text="Done!")
        self._last_results = results

        self.report_text.config(state="normal")
        self.report_text.delete("1.0", "end")

        self._result_urls = []
        for r in results:
            if r.get("success"):
                url = r.get("url", "")
                line = f"[OK] {r['title']} -> {url}"
                if r.get("image_warning"):
                    line += f"  (IMG: {r['image_warning']})"
                self.report_text.insert("end", line + "\n")
                self._result_urls.append(url)
            else:
                self.report_text.insert("end", f"[FAIL] {r['title']} -> {r.get('error', 'Unknown error')}\n")

        self.report_text.config(state="disabled")

    # -------------------------------------------------------- Retry failed
    def _retry_failed(self):
        if not self._last_results:
            messagebox.showinfo("Info", "No previous results to retry.")
            return
        if not self.selected_site:
            messagebox.showinfo("Info", "Select a site first.")
            return

        failed_indices = [r["index"] for r in self._last_results if not r.get("success")]
        if not failed_indices:
            messagebox.showinfo("Info", "No failed posts to retry.")
            return

        self.btn_publish.config(state="disabled")
        self.btn_retry.config(state="disabled")
        self.progress["maximum"] = len(failed_indices)
        self.progress["value"] = 0
        self.progress_label.config(text="Retrying failed...")

        threading.Thread(target=self._retry_worker, args=(failed_indices,), daemon=True).start()

    def _retry_worker(self, failed_indices):
        results = []
        wp_gmt_offset = wp_api._get_wp_gmt_offset(self.selected_site)
        site = self.selected_site
        status = self.status_var.get()

        # Phase 1: Parallel image optimize & upload
        articles_with_images = [
            (i, self.articles[i]) for i in failed_indices
            if self.articles[i].get("image_path") and os.path.isfile(self.articles[i]["image_path"])
        ]

        media_map = {}

        if articles_with_images:
            def _upload_one(idx_art):
                idx, art = idx_art
                path = art["image_path"]
                opt = image_optimizer.optimize_for_upload(path)
                if not opt["success"]:
                    return idx, None, f"Optimization failed: {opt['error']}"
                upload_path = opt["path"]
                img_result = wp_api.upload_media(site, upload_path)
                try:
                    if upload_path != path:
                        os.remove(upload_path)
                except OSError:
                    pass
                if img_result["success"]:
                    return idx, img_result["media_id"], ""
                else:
                    return idx, None, f"Upload failed: {img_result['error']}"

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(_upload_one, item): item[0]
                           for item in articles_with_images}
                for future in as_completed(futures):
                    idx, media_id, warning = future.result()
                    media_map[idx] = {"media_id": media_id, "warning": warning}

        # Phase 2: Create posts
        for count, i in enumerate(failed_indices):
            art = self.articles[i]

            featured_media_id = None
            image_warning = ""

            if i in media_map:
                featured_media_id = media_map[i]["media_id"]
                image_warning = media_map[i]["warning"]
            elif art.get("image_path") and not os.path.isfile(art["image_path"]):
                image_warning = f"Image file not found: {art['image_path']}"

            publish_date = None
            if art.get("publish_date"):
                try:
                    dt = datetime.strptime(art["publish_date"], "%Y-%m-%d %H:%M")
                    publish_date = dt.isoformat()
                except ValueError:
                    publish_date = None

            result = wp_api.create_post(
                site=site,
                title=art["title"],
                content=art["html_body"],
                status=status,
                category_id=art["category_id"],
                author_id=art["author_id"],
                featured_media_id=featured_media_id,
                publish_date=publish_date,
                wp_gmt_offset=wp_gmt_offset,
                slug=art.get("slug"),
            )
            result["image_warning"] = image_warning
            results.append({"title": art["title"], "index": i, **result})
            self.root.after(0, self._update_retry_progress, count + 1, len(failed_indices))

        self.root.after(0, self._show_retry_report, results)

    def _update_retry_progress(self, value, total):
        self.progress["value"] = value
        self.progress_label.config(text=f"Retrying {value}/{total}...")

    def _show_retry_report(self, results):
        self.btn_publish.config(state="normal")
        self.btn_retry.config(state="normal")
        self.progress_label.config(text="Retry done!")

        result_map = {r["index"]: r for r in results}
        for j, lr in enumerate(self._last_results):
            if lr["index"] in result_map:
                self._last_results[j] = result_map[lr["index"]]

        self.report_text.config(state="normal")
        self.report_text.delete("1.0", "end")
        self._result_urls = []
        for r in self._last_results:
            if r.get("success"):
                url = r.get("url", "")
                line = f"[OK] {r['title']} -> {url}"
                if r.get("image_warning"):
                    line += f"  (IMG: {r['image_warning']})"
                self.report_text.insert("end", line + "\n")
                self._result_urls.append(url)
            else:
                self.report_text.insert("end", f"[FAIL] {r['title']} -> {r.get('error', 'Unknown error')}\n")
        self.report_text.config(state="disabled")

    def _copy_urls(self):
        urls = getattr(self, "_result_urls", [])
        if not urls:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(urls))
        messagebox.showinfo("Copied", f"{len(urls)} URLs copied to clipboard.")
