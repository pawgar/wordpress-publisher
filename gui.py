import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time

import config_manager
import wp_api
import docx_parser


class WordPressPublisherApp:
    def __init__(self, root):
        self.root = root
        self.articles = []
        self.categories = []
        self.users = []
        self.selected_site = None

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
        ttk.Button(row, text="- Remove Site", command=self._remove_site).pack(side="left", padx=2)
        ttk.Button(row, text="Test Connection", command=self._test_connection).pack(side="left", padx=2)

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

        # Draft / Published
        status_row = ttk.Frame(frame)
        status_row.pack(fill="x", pady=(0, 6))
        ttk.Label(status_row, text="Publish as:").pack(side="left")
        self.status_var = tk.StringVar(value="draft")
        ttk.Radiobutton(status_row, text="Draft", variable=self.status_var, value="draft").pack(side="left", padx=(8, 4))
        ttk.Radiobutton(status_row, text="Published", variable=self.status_var, value="publish").pack(side="left")

        # Scrollable table
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(table_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.canvas.yview)
        self.table_inner = ttk.Frame(self.canvas)

        self.table_inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.table_inner, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Bulk assign row
        bulk_row = ttk.Frame(frame)
        bulk_row.pack(fill="x", pady=(6, 0))

        ttk.Label(bulk_row, text="Set all categories:").pack(side="left")
        self.bulk_cat_var = tk.StringVar()
        self.bulk_cat_combo = ttk.Combobox(bulk_row, textvariable=self.bulk_cat_var, state="readonly", width=20)
        self.bulk_cat_combo.pack(side="left", padx=(4, 12))
        self.bulk_cat_combo.bind("<<ComboboxSelected>>", self._bulk_set_categories)

        ttk.Label(bulk_row, text="Set all authors:").pack(side="left")
        self.bulk_author_var = tk.StringVar()
        self.bulk_author_combo = ttk.Combobox(bulk_row, textvariable=self.bulk_author_var, state="readonly", width=20)
        self.bulk_author_combo.pack(side="left", padx=4)
        self.bulk_author_combo.bind("<<ComboboxSelected>>", self._bulk_set_authors)

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

        for row in self._article_rows:
            row["cat_combo"]["values"] = cat_names
            row["author_combo"]["values"] = user_names
            if cat_names and not row["cat_var"].get():
                row["cat_combo"].current(0)
            if user_names and not row["author_var"].get():
                row["author_combo"].current(0)

    def _add_site_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Add WordPress Site")
        dlg.geometry("400x220")
        dlg.resizable(False, False)
        dlg.grab_set()

        fields = {}
        for i, (label, show) in enumerate([
            ("Name:", None),
            ("URL:", None),
            ("Username:", None),
            ("App Password:", "*"),
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
    @property
    def _article_rows(self):
        return getattr(self, "_rows", [])

    def _select_files(self):
        paths = filedialog.askopenfilenames(
            title="Select DOCX files",
            filetypes=[("Word Documents", "*.docx")],
        )
        if not paths:
            return

        self.articles = []
        errors = []
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
            else:
                errors.append(result["error"])

        self.load_status.config(text=f"{len(self.articles)} files loaded")
        if errors:
            messagebox.showwarning("Parse errors", "\n".join(errors))

        self._rebuild_article_table()

    def _rebuild_article_table(self):
        for w in self.table_inner.winfo_children():
            w.destroy()

        # Header
        for col, (text, width) in enumerate([("#", 3), ("Title", 40), ("Category", 20), ("Author", 20)]):
            ttk.Label(self.table_inner, text=text, font=("", 9, "bold"), width=width, anchor="w").grid(
                row=0, column=col, padx=2, pady=2, sticky="w"
            )

        self._rows = []
        cat_names = [c["name"] for c in self.categories]
        user_names = [u["name"] for u in self.users]

        for i, art in enumerate(self.articles):
            row_num = i + 1
            ttk.Label(self.table_inner, text=str(row_num), width=3).grid(row=row_num, column=0, padx=2, pady=1, sticky="w")
            ttk.Label(self.table_inner, text=art["title"], width=40, anchor="w").grid(row=row_num, column=1, padx=2, pady=1, sticky="w")

            cat_var = tk.StringVar()
            cat_combo = ttk.Combobox(self.table_inner, textvariable=cat_var, state="readonly", width=18, values=cat_names)
            cat_combo.grid(row=row_num, column=2, padx=2, pady=1)
            if cat_names:
                cat_combo.current(0)

            author_var = tk.StringVar()
            author_combo = ttk.Combobox(self.table_inner, textvariable=author_var, state="readonly", width=18, values=user_names)
            author_combo.grid(row=row_num, column=3, padx=2, pady=1)
            if user_names:
                author_combo.current(0)

            self._rows.append({
                "cat_var": cat_var,
                "cat_combo": cat_combo,
                "author_var": author_var,
                "author_combo": author_combo,
            })

    # -------------------------------------------------------- Bulk assign
    def _bulk_set_categories(self, _event):
        val = self.bulk_cat_var.get()
        for row in self._article_rows:
            row["cat_var"].set(val)

    def _bulk_set_authors(self, _event):
        val = self.bulk_author_var.get()
        for row in self._article_rows:
            row["author_var"].set(val)

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

        # Resolve category & author IDs
        for i, art in enumerate(self.articles):
            row = self._article_rows[i]
            art["category_id"] = self._resolve_id(self.categories, "name", row["cat_var"].get())
            art["author_id"] = self._resolve_id(self.users, "name", row["author_var"].get())

        self.btn_publish.config(state="disabled")
        self.progress["maximum"] = len(self.articles)
        self.progress["value"] = 0
        self.progress_label.config(text="Starting...")

        threading.Thread(target=self._publish_worker, daemon=True).start()

    def _publish_worker(self):
        results = []
        for i, art in enumerate(self.articles):
            result = wp_api.create_post(
                site=self.selected_site,
                title=art["title"],
                content=art["html_body"],
                status=self.status_var.get(),
                category_id=art["category_id"],
                author_id=art["author_id"],
            )
            results.append({"title": art["title"], **result})
            self.root.after(0, self._update_progress, i + 1)
            time.sleep(0.5)

        self.root.after(0, self._show_report, results)

    def _update_progress(self, value):
        self.progress["value"] = value
        self.progress_label.config(text=f"Publishing {value}/{len(self.articles)}...")

    def _show_report(self, results):
        self.btn_publish.config(state="normal")
        self.progress_label.config(text="Done!")

        self.report_text.config(state="normal")
        self.report_text.delete("1.0", "end")

        self._result_urls = []
        for r in results:
            if r.get("success"):
                url = r.get("url", "")
                self.report_text.insert("end", f"[OK] {r['title']} -> {url}\n")
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
