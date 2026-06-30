"""
app.py — SRT Subtitle Translator Desktop App
Dark-theme Tkinter GUI with parallel OpenRouter translation.

Run: python app.py
"""

import os
import sys
import json
import threading
import socket
import ctypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# ───────────────────────────────────────────────────────────────────────────
# Single Instance Lock & Windows Taskbar Icon Fix
# ───────────────────────────────────────────────────────────────────────────
try:
    # Port 54321 chosen as unique identifier for this application
    _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _lock_socket.bind(('127.0.0.1', 54321))
except socket.error:
    # Silent exit if another instance is already running
    sys.exit(0)

try:
    # Explicitly register AppUserModelID so Windows displays the correct taskbar icon
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("matrix.srt_translator.v1")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Ensure project root on sys.path
# ---------------------------------------------------------------------------
IS_FROZEN = getattr(sys, 'frozen', False)
if IS_FROZEN:
    ROOT = sys._MEIPASS
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.srt_parser import read_srt, write_srt, get_output_path, lang_to_code
from core.translator import translate_file

# ---------------------------------------------------------------------------
# Colour & font constants (dark neon theme)
# ---------------------------------------------------------------------------
BG          = "#0d0f18"
BG2         = "#111624"
BG3         = "#1a2035"
SIDEBAR_BG  = "#0b0d14"
ACCENT      = "#00e5ff"
ACCENT2     = "#4f8eff"
SUCCESS     = "#00e676"
WARN        = "#ffab40"
ERR         = "#ff4d6d"
TXT         = "#e2e8f0"
TXT_DIM     = "#64748b"
BORDER      = "#1e2d45"

FONT_MAIN   = ("Segoe UI",  11)
FONT_MONO   = ("Consolas",  10)
FONT_TITLE  = ("Segoe UI",  20, "bold")
FONT_LABEL  = ("Segoe UI",   9, "bold")
FONT_BTN    = ("Segoe UI",  11, "bold")

if IS_FROZEN:
    CONFIG_PATH = os.path.join(os.path.dirname(sys.executable), "config.json")
else:
    CONFIG_PATH = os.path.join(ROOT, "config.json")

SUPPORTED_LANGS = [
    ("Indonesian",          "indonesian"),
    ("Thai",                "thai"),
    ("Vietnamese",          "vietnamese"),
    ("Hindi",               "hindi"),
    ("Korean",              "korean"),
    ("Spanish (LATAM)",     "spanish"),
    ("French",              "french"),
    ("German",              "german"),
    ("Portuguese (BR)",     "portuguese"),
    ("English",             "english"),
    ("Turkish",             "turkish"),
    ("Filipino/Tagalog",    "filipino"),
    ("Russian",             "russian"),
    ("Japanese",            "japanese"),
    ("Chinese (Simplified)","chinese"),
    ("Arabic",              "arabic"),
]

MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
]

CONTENT_TYPES = [
    ("Tự động nhận diện", "auto"),
    ("Film / Drama",      "film"),
    ("Anime",             "anime"),
    ("Wuxia / Cổ trang",  "wuxia"),
    ("Tin tức / News",    "news"),
    ("Tài liệu",          "documentary"),
]

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    defaults = {
        "api_keys": [],
        "model": MODELS[0],
        "target_language": "indonesian",
        "content_type": "auto",
        "batch_size": 45,
    }
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        defaults.update(data)
    except Exception:
        pass
    return defaults


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Rounded rectangle canvas helper
# ---------------------------------------------------------------------------

def rounded_rect(canvas, x1, y1, x2, y2, r=12, **kw):
    pts = [
        x1+r, y1,   x2-r, y1,
        x2,   y1,   x2,   y1+r,
        x2,   y2-r, x2,   y2,
        x2-r, y2,   x1+r, y2,
        x1,   y2,   x1,   y2-r,
        x1,   y1+r, x1,   y1,
        x1+r, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


# ---------------------------------------------------------------------------
# Main Application Window
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Matrix Tool SRT-Translator V1")
        self.geometry("1200x760")
        self.minsize(900, 600)
        self.configure(bg=BG)
        self._set_icon()

        self.cfg = load_config()
        self.files: list[dict] = []   # {path, name, size, status}
        self.is_running = False
        self._progress_vals: dict[int, int] = {}
        self._total_blocks = 0

        self._build_ui()
        self._apply_ttk_theme()
        self._restore_settings()

        # Make window resizable with minimum
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    # ------------------------------------------------------------------ icon
    def _set_icon(self):
        try:
            ico = os.path.join(ROOT, "assets", "icon.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

    # ------------------------------------------------------------------ TTK theme
    def _apply_ttk_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".",
            background=BG, foreground=TXT,
            fieldbackground=BG3, bordercolor=BORDER,
            lightcolor=BORDER, darkcolor=BORDER,
            troughcolor=BG2, insertcolor=TXT,
            selectbackground=BG3, selectforeground=ACCENT,
        )

        # Treeview
        style.configure("Files.Treeview",
            background=BG2, foreground=TXT,
            fieldbackground=BG2, rowheight=32,
            font=("Segoe UI", 10),
        )
        style.configure("Files.Treeview.Heading",
            background=BG3, foreground=TXT_DIM,
            font=("Segoe UI", 9, "bold"), relief="flat",
        )
        style.map("Files.Treeview",
            background=[("selected", BG3)],
            foreground=[("selected", ACCENT)],
        )

        # Scrollbars
        style.configure("Dark.Vertical.TScrollbar",
            background=BG3, troughcolor=BG,
            arrowcolor=TXT_DIM, bordercolor=BG,
            relief="flat", width=8,
        )
        style.map("Dark.Vertical.TScrollbar",
            background=[("active", BORDER)],
        )

        # Progressbar
        style.configure("Neon.Horizontal.TProgressbar",
            background=ACCENT, troughcolor=BG3,
            bordercolor=BG3, lightcolor=ACCENT, darkcolor=ACCENT,
        )

        # Combobox
        style.configure("Dark.TCombobox",
            fieldbackground=BG3, background=BG3,
            foreground=TXT, arrowcolor=TXT_DIM,
            bordercolor=BORDER, relief="flat",
        )
        style.map("Dark.TCombobox",
            fieldbackground=[("readonly", BG3)],
            foreground=[("readonly", TXT)],
        )

    # ================================================================== BUILD UI
    def _build_ui(self):
        root_frame = tk.Frame(self, bg=BG)
        root_frame.pack(fill="both", expand=True)

        # ---- LEFT SIDEBAR ----
        self._build_sidebar(root_frame)

        # ---- RIGHT MAIN PANEL ----
        self._build_main_panel(root_frame)

    # ================================================================== SIDEBAR
    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=SIDEBAR_BG, width=300)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        # Gradient top accent bar
        accent_bar = tk.Frame(sb, bg=ACCENT, height=3)
        accent_bar.pack(fill="x")

        inner = tk.Frame(sb, bg=SIDEBAR_BG)
        inner.pack(fill="both", expand=True, padx=18, pady=18)

        # --- App title ---
        tk.Label(inner, text="MATRIX", bg=SIDEBAR_BG,
                 fg=ACCENT, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(inner, text="SRT-Translator  V1", bg=SIDEBAR_BG,
                 fg=TXT_DIM, font=("Segoe UI", 10)).pack(anchor="w")

        self._sep(inner)

        # --- API Keys ---
        self._section_label(inner, "🔑  API KEYS  (mỗi dòng 1 key)")
        self.api_keys_txt = tk.Text(
            inner, height=6, bg=BG3, fg=TXT,
            font=FONT_MONO, insertbackground=ACCENT,
            relief="flat", bd=0, wrap="none",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self.api_keys_txt.pack(fill="x", pady=(4, 2))

        self.key_count_lbl = tk.Label(
            inner, text="0 key(s)", bg=SIDEBAR_BG,
            fg=TXT_DIM, font=("Segoe UI", 9),
        )
        self.key_count_lbl.pack(anchor="e")
        self.api_keys_txt.bind("<KeyRelease>", self._update_key_count)

        self._sep(inner)

        # --- Target Language ---
        self._section_label(inner, "🌐  NGÔN NGỮ ĐÍCH")
        self.lang_var = tk.StringVar()
        self.lang_combo = ttk.Combobox(
            inner, textvariable=self.lang_var,
            values=[l[0] for l in SUPPORTED_LANGS],
            state="readonly", style="Dark.TCombobox", font=FONT_MAIN,
        )
        self.lang_combo.pack(fill="x", pady=(4, 0))

        # --- Content Type ---
        self._section_label(inner, "🎬  LOẠI NỘI DUNG")
        self.ctype_var = tk.StringVar()
        self.ctype_combo = ttk.Combobox(
            inner, textvariable=self.ctype_var,
            values=[c[0] for c in CONTENT_TYPES],
            state="readonly", style="Dark.TCombobox", font=FONT_MAIN,
        )
        self.ctype_combo.pack(fill="x", pady=(4, 0))

        # --- Model ---
        self._section_label(inner, "🤖  MODEL")
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            inner, textvariable=self.model_var,
            values=MODELS,
            style="Dark.TCombobox", font=("Segoe UI", 9),
        )
        self.model_combo.pack(fill="x", pady=(4, 0))

        # --- Batch Size ---
        self._section_label(inner, "📦  BATCH SIZE  (blocks/lượt)")
        bs_row = tk.Frame(inner, bg=SIDEBAR_BG)
        bs_row.pack(fill="x", pady=(4, 0))

        self.batch_var = tk.IntVar(value=45)
        self.batch_scale = tk.Scale(
            bs_row, variable=self.batch_var,
            from_=10, to=100, orient="horizontal",
            bg=SIDEBAR_BG, fg=TXT, troughcolor=BG3,
            highlightthickness=0, activebackground=ACCENT,
            sliderlength=14, bd=0,
            command=lambda v: self.batch_lbl.config(text=f"{int(float(v))} blocks"),
        )
        self.batch_scale.pack(side="left", fill="x", expand=True)
        self.batch_lbl = tk.Label(
            bs_row, text="45 blocks", bg=SIDEBAR_BG,
            fg=ACCENT, font=("Segoe UI", 10, "bold"), width=10,
        )
        self.batch_lbl.pack(side="right")

        # --- Glossary ---
        self._section_label(inner, "📖  GLOSSARY  (Tên gốc = Tên dịch, mỗi dòng 1 cặp)")
        self.glossary_txt = tk.Text(
            inner, height=5, bg=BG3, fg=TXT,
            font=FONT_MONO, insertbackground=ACCENT,
            relief="flat", bd=0, wrap="none",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self.glossary_txt.pack(fill="x", pady=(4, 2))
        self._mk_placeholder(self.glossary_txt,
                             "Naruto = Naruto\nKonoha = Làng Lá\nSensei = Thầy")

        self._sep(inner)

        inner.pack_configure(expand=True)

        # --- Buttons (bottom) ---
        btn_frame = tk.Frame(inner, bg=SIDEBAR_BG)
        btn_frame.pack(side="bottom", fill="x", pady=(8, 0))

        # Save config btn
        self._mk_btn(btn_frame, "💾  Lưu cấu hình", self._save_settings,
                     bg=BG3, fg=TXT_DIM, active_bg=BORDER).pack(fill="x", pady=(0, 6))

        # Start btn
        self.start_btn = self._mk_btn(
            btn_frame, "▶   BẮT ĐẦU DỊCH", self._start_translation,
            bg=ACCENT, fg="#0a0a0a", active_bg="#33eeff",
        )
        self.start_btn.pack(fill="x", pady=(0, 4))

        # Stop btn
        self.stop_btn = self._mk_btn(
            btn_frame, "■   DỪNG", self._stop_translation,
            bg="#2a0a12", fg=ERR, active_bg="#3d1020",
        )
        self.stop_btn.pack(fill="x")
        self.stop_btn.pack_forget()

    # ================================================================== MAIN PANEL
    def _build_main_panel(self, parent):
        main = tk.Frame(parent, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        # ---- TOP HEADER ----
        header = tk.Frame(main, bg=BG, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text="Danh sách file phụ đề (.srt)",
            bg=BG, fg=TXT, font=("Segoe UI", 14, "bold"),
        ).pack(side="left", padx=20, pady=14)

        btn_row = tk.Frame(header, bg=BG)
        btn_row.pack(side="right", padx=12, pady=8)

        for lbl, cmd in [
            ("＋ Thêm file",     self._browse_files),
            ("📁 Thêm folder",   self._browse_folder),
            ("✓ Chọn tất",       self._select_all),
            ("✗ Bỏ chọn tất",    self._deselect_all),
            ("🗑 Xóa danh sách", self._clear_list),
        ]:
            self._mk_btn(btn_row, lbl, cmd, bg=BG3, fg=TXT_DIM,
                         active_bg=BORDER, padx=8, pady=4).pack(
                side="left", padx=2)

        # Thin accent line
        tk.Frame(main, bg=BORDER, height=1).pack(fill="x")

        # ---- PANED WINDOW (file list top, log bottom) ----
        paned = tk.PanedWindow(
            main, orient="vertical", bg=BG,
            sashwidth=6, sashrelief="flat",
            sashcursor="sb_v_double_arrow",
        )
        paned.pack(fill="both", expand=True, padx=12, pady=10)

        # -- File list frame
        list_frame = tk.Frame(paned, bg=BG)
        paned.add(list_frame, stretch="always", minsize=160)
        self._build_file_list(list_frame)

        # -- Log frame
        log_frame = tk.Frame(paned, bg=BG)
        paned.add(log_frame, stretch="always", minsize=120)
        self._build_log_panel(log_frame)

        paned.paneconfig(list_frame, height=380)
        paned.paneconfig(log_frame,  height=200)

    # ------------------------------------------------------------------ file list
    def _build_file_list(self, parent):
        # Drop zone (shown when empty)
        self.drop_frame = tk.Frame(parent, bg=BG2, relief="flat")
        self.drop_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(self.drop_frame, bg=BG2, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        def _draw_drop(e=None):
            canvas.delete("all")
            w, h = canvas.winfo_width(), canvas.winfo_height()
            if w < 10:
                return
            rounded_rect(canvas, 16, 16, w-16, h-16, r=18,
                         fill=BG3, outline=BORDER, width=2)
            canvas.create_text(w//2, h//2 - 28, text="📂",
                                font=("Segoe UI", 40), fill=TXT_DIM)
            canvas.create_text(w//2, h//2 + 24,
                                text="Kéo thả file .srt vào đây",
                                font=("Segoe UI", 14, "bold"), fill=TXT_DIM)
            canvas.create_text(w//2, h//2 + 52,
                                text="hoặc nhấn nút  ＋ Thêm file  bên trên",
                                font=("Segoe UI", 10), fill=TXT_DIM)

        canvas.bind("<Configure>", _draw_drop)
        canvas.bind("<Button-1>", lambda e: self._browse_files())

        # Drag & drop (Windows TkDnD-free approach via DnD events)
        self.drop_frame.bind("<Button-1>", lambda e: self._browse_files())

        # Register native drop if possible (TkinterDnD2 optional)
        try:
            import tkinterdnd2 as dnd
            canvas.drop_target_register("DND_Files")
            canvas.dnd_bind("<<Drop>>", self._on_dnd_drop)
        except Exception:
            pass

        # Treeview (hidden until files added)
        self.tree_frame = tk.Frame(parent, bg=BG2)

        cols = ("check", "name", "size", "status")
        self.tree = ttk.Treeview(
            self.tree_frame, columns=cols, show="headings",
            style="Files.Treeview", selectmode="browse",
        )
        self.tree.heading("check",  text="☑",    anchor="center")
        self.tree.heading("name",   text="Tên file SRT",   anchor="w")
        self.tree.heading("size",   text="Kích thước",     anchor="center")
        self.tree.heading("status", text="Trạng thái",     anchor="center")

        self.tree.column("check",  width=38,  stretch=False, anchor="center")
        self.tree.column("name",   width=460, stretch=True,  anchor="w")
        self.tree.column("size",   width=100, stretch=False, anchor="center")
        self.tree.column("status", width=180, stretch=False, anchor="center")

        vsb = ttk.Scrollbar(self.tree_frame, orient="vertical",
                            command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)

        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        self.tree.bind("<Button-1>", self._on_tree_click)

        # Progress bar (bottom of list)
        self.progress_frame = tk.Frame(parent, bg=BG, height=28)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, variable=self.progress_var,
            maximum=100, style="Neon.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill="x", padx=0, pady=4)
        self.progress_lbl = tk.Label(
            self.progress_frame, text="", bg=BG, fg=TXT_DIM,
            font=("Segoe UI", 9),
        )
        self.progress_lbl.pack()

    # ------------------------------------------------------------------ log panel
    def _build_log_panel(self, parent):
        header = tk.Frame(parent, bg=BG)
        header.pack(fill="x", pady=(4, 2))

        tk.Label(header, text="📋  Nhật ký dịch thuật",
                 bg=BG, fg=TXT_DIM, font=FONT_LABEL).pack(side="left")

        self._mk_btn(
            header, "Xóa log", self._clear_log,
            bg=BG2, fg=TXT_DIM, active_bg=BORDER, padx=6, pady=2,
        ).pack(side="right")

        self.log = tk.Text(
            parent, bg="#060810", fg=SUCCESS,
            font=FONT_MONO, insertbackground=ACCENT,
            relief="flat", bd=0, wrap="word",
            highlightthickness=1, highlightbackground=BORDER,
            state="disabled",
        )
        self.log.pack(fill="both", expand=True)

        # Color tags
        self.log.tag_config("info",    foreground=ACCENT)
        self.log.tag_config("ok",      foreground=SUCCESS)
        self.log.tag_config("warn",    foreground=WARN)
        self.log.tag_config("error",   foreground=ERR)
        self.log.tag_config("dim",     foreground=TXT_DIM)
        self.log.tag_config("default", foreground=TXT)

        log_sb = ttk.Scrollbar(parent, orient="vertical",
                                command=self.log.yview,
                                style="Dark.Vertical.TScrollbar")
        self.log.configure(yscrollcommand=log_sb.set)

    # ================================================================== PLACEHOLDER HELPER
    def _mk_placeholder(self, widget: tk.Text, placeholder: str):
        """Hiển thị placeholder text mờ khi widget trống."""
        widget._placeholder = placeholder
        widget._has_placeholder = False

        def _show_ph(event=None):
            if not widget.get("1.0", "end").strip():
                widget._has_placeholder = True
                widget.config(fg=TXT_DIM)
                widget.insert("1.0", placeholder)

        def _hide_ph(event=None):
            if widget._has_placeholder:
                widget._has_placeholder = False
                widget.delete("1.0", "end")
                widget.config(fg=TXT)

        widget.bind("<FocusIn>",  _hide_ph)
        widget.bind("<FocusOut>", _show_ph)
        _show_ph()  # init

    # ================================================================== UI HELPERS
    def _sep(self, parent):
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=10)

    def _section_label(self, parent, text):
        tk.Label(
            parent, text=text, bg=SIDEBAR_BG,
            fg=TXT_DIM, font=FONT_LABEL,
        ).pack(anchor="w", pady=(8, 0))

    def _mk_btn(self, parent, text, command,
                bg=BG3, fg=TXT, active_bg=BORDER,
                padx=12, pady=6):
        btn = tk.Button(
            parent, text=text, command=command,
            bg=bg, fg=fg, activebackground=active_bg, activeforeground=fg,
            font=FONT_BTN, relief="flat", bd=0,
            padx=padx, pady=pady, cursor="hand2",
        )
        return btn

    def _log(self, msg: str, level: str = "default"):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}]  {msg}\n"
        self.log.config(state="normal")
        self.log.insert("end", line, level)
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    # ================================================================== FILE LIST
    def _show_tree(self):
        self.drop_frame.pack_forget()
        self.tree_frame.pack(fill="both", expand=True)
        self.progress_frame.pack(fill="x")

    def _show_drop(self):
        self.tree_frame.pack_forget()
        self.progress_frame.pack_forget()
        self.drop_frame.pack(fill="both", expand=True)

    def _add_files(self, paths: list[str]):
        existing = {f["path"] for f in self.files}
        added = 0
        for p in paths:
            if not p.lower().endswith(".srt"):
                continue
            if p in existing:
                continue
            name = os.path.basename(p)
            size = os.path.getsize(p)
            size_str = f"{size/1024:.1f} KB"
            self.files.append({
                "path": p, "name": name, "size": size_str,
                "checked": True, "status": "Chờ dịch",
            })
            existing.add(p)
            added += 1

        self._refresh_tree()
        if self.files:
            self._show_tree()
        if added:
            self._log(f"Đã thêm {added} file(s).", "ok")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, f in enumerate(self.files):
            chk = "☑" if f["checked"] else "☐"
            tag = self._status_tag(f["status"])
            iid = self.tree.insert(
                "", "end",
                values=(chk, f["name"], f["size"], f["status"]),
                tags=(tag, f"row_{i}"),
            )

        self.tree.tag_configure("done",    foreground=SUCCESS)
        self.tree.tag_configure("running", foreground=ACCENT)
        self.tree.tag_configure("error",   foreground=ERR)
        self.tree.tag_configure("skip",    foreground=TXT_DIM)
        self.tree.tag_configure("pending", foreground=TXT)

    def _status_tag(self, status: str) -> str:
        s = status.lower()
        if "hoàn thành" in s or "done" in s: return "done"
        if "đang dịch"  in s or "dịch..."  in s: return "running"
        if "lỗi"        in s or "error"    in s: return "error"
        if "bỏ qua"     in s or "skip"     in s: return "skip"
        return "pending"

    def _update_file_status(self, idx: int, status: str):
        self.files[idx]["status"] = status
        items = self.tree.get_children()
        if idx < len(items):
            iid = items[idx]
            f = self.files[idx]
            chk = "☑" if f["checked"] else "☐"
            tag = self._status_tag(status)
            self.tree.item(iid, values=(chk, f["name"], f["size"], status), tags=(tag, f"row_{idx}"))
            self.tree.tag_configure("done",    foreground=SUCCESS)
            self.tree.tag_configure("running", foreground=ACCENT)
            self.tree.tag_configure("error",   foreground=ERR)
            self.tree.tag_configure("skip",    foreground=TXT_DIM)
            self.tree.tag_configure("pending", foreground=TXT)

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        col    = self.tree.identify_column(event.x)
        iid    = self.tree.identify_row(event.y)
        if not iid or col != "#1":
            return
        idx = self.tree.index(iid)
        if idx < len(self.files):
            self.files[idx]["checked"] = not self.files[idx]["checked"]
            self._refresh_tree()

    def _on_dnd_drop(self, event):
        paths = self.tk.splitlist(event.data)
        expanded = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(".srt"):
                            expanded.append(os.path.join(root, f))
            else:
                expanded.append(p)
        self._add_files(expanded)

    # ================================================================== CONTROLS
    def _browse_files(self):
        paths = filedialog.askopenfilenames(
            title="Chọn file SRT",
            filetypes=[("SRT Subtitles", "*.srt"), ("All files", "*.*")],
        )
        if paths:
            self._add_files(list(paths))

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục chứa file SRT")
        if folder:
            paths = []
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(".srt"):
                        paths.append(os.path.join(root, f))
            self._add_files(paths)

    def _select_all(self):
        for f in self.files:
            f["checked"] = True
        self._refresh_tree()

    def _deselect_all(self):
        for f in self.files:
            f["checked"] = False
        self._refresh_tree()

    def _clear_list(self):
        if self.is_running:
            messagebox.showwarning("Cảnh báo", "Dừng tiến trình trước khi xóa danh sách.")
            return
        self.files.clear()
        self._refresh_tree()
        self._show_drop()
        self.progress_var.set(0)

    # ================================================================== SETTINGS
    def _update_key_count(self, event=None):
        keys = [k.strip() for k in self.api_keys_txt.get("1.0", "end").splitlines() if k.strip()]
        n = len(keys)
        self.key_count_lbl.config(
            text=f"{n} key(s) — {n} worker(s) song song",
            fg=SUCCESS if n > 0 else ERR,
        )

    def _restore_settings(self):
        c = self.cfg

        # API Keys
        self.api_keys_txt.delete("1.0", "end")
        self.api_keys_txt.insert("1.0", "\n".join(c.get("api_keys", [])))
        self._update_key_count()

        # Language
        lang_key = c.get("target_language", "indonesian")
        for display, key in SUPPORTED_LANGS:
            if key == lang_key:
                self.lang_var.set(display)
                break
        if not self.lang_var.get():
            self.lang_combo.current(0)

        # Content type
        ctype_key = c.get("content_type", "auto")
        for display, key in CONTENT_TYPES:
            if key == ctype_key:
                self.ctype_var.set(display)
                break
        if not self.ctype_var.get():
            self.ctype_combo.current(0)

        # Model
        self.model_var.set(c.get("model", MODELS[0]))
        if self.model_var.get() not in MODELS:
            self.model_combo["values"] = MODELS + [self.model_var.get()]

        # Batch
        self.batch_var.set(c.get("batch_size", 40))
        self.batch_lbl.config(text=f"{c.get('batch_size', 40)} blocks")

        # Glossary
        glossary = c.get("glossary", {})
        if glossary:
            lines = [f"{k} = {v}" for k, v in glossary.items()]
            self.glossary_txt.config(fg=TXT)
            self.glossary_txt._has_placeholder = False
            self.glossary_txt.delete("1.0", "end")
            self.glossary_txt.insert("1.0", "\n".join(lines))

    def _parse_glossary(self) -> dict:
        """Parse glossary textarea into {source: target} dict."""
        if getattr(self.glossary_txt, '_has_placeholder', False):
            return {}
        raw = self.glossary_txt.get("1.0", "end").strip()
        glossary = {}
        for line in raw.splitlines():
            if "=" in line:
                parts = line.split("=", 1)
                src = parts[0].strip()
                tgt = parts[1].strip()
                if src and tgt:
                    glossary[src] = tgt
        return glossary

    def _save_settings(self):
        keys = [k.strip() for k in self.api_keys_txt.get("1.0", "end").splitlines() if k.strip()]
        lang_display = self.lang_var.get()
        lang_key = next((k for d, k in SUPPORTED_LANGS if d == lang_display), "indonesian")
        ctype_display = self.ctype_var.get()
        ctype_key = next((k for d, k in CONTENT_TYPES if d == ctype_display), "auto")

        self.cfg.update({
            "api_keys":        keys,
            "model":           self.model_var.get(),
            "target_language": lang_key,
            "content_type":    ctype_key,
            "batch_size":      self.batch_var.get(),
            "glossary":        self._parse_glossary(),
        })
        save_config(self.cfg)
        self._log("✅ Đã lưu cấu hình.", "ok")

    def _get_current_settings(self) -> dict:
        keys = [k.strip() for k in self.api_keys_txt.get("1.0", "end").splitlines() if k.strip()]
        lang_display  = self.lang_var.get()
        lang_key      = next((k for d, k in SUPPORTED_LANGS if d == lang_display), "indonesian")
        ctype_display = self.ctype_var.get()
        ctype_key     = next((k for d, k in CONTENT_TYPES if d == ctype_display), "auto")
        return {
            "api_keys":    keys,
            "model":       self.model_var.get().strip(),
            "lang":        lang_key,
            "ctype":       ctype_key,
            "batch_size":  self.batch_var.get(),
            "lang_code":   lang_to_code(lang_key),
            "glossary":    self._parse_glossary(),
        }

    # ================================================================== TRANSLATION
    def _start_translation(self):
        if self.is_running:
            return

        settings = self._get_current_settings()

        # Validation
        if not settings["api_keys"]:
            messagebox.showerror("Thiếu API Key",
                "Vui lòng nhập ít nhất 1 API Key.\n"
                "Lấy key tại: https://api.ai-box.vn/console/token")
            return

        selected = [(i, f) for i, f in enumerate(self.files) if f["checked"]]
        if not selected:
            messagebox.showinfo("Thông báo", "Vui lòng chọn ít nhất 1 file để dịch.")
            return

        # Update UI
        self.is_running = True
        self.start_btn.pack_forget()
        self.stop_btn.pack(fill="x")
        self._clear_log()

        for i, f in selected:
            self._update_file_status(i, "⏳ Đang chờ...")

        self._log(f"▶ Bắt đầu dịch {len(selected)} file(s) → {settings['lang'].title()} [{settings['lang_code']}]", "info")
        self._log(f"   Model: {settings['model']} | {len(settings['api_keys'])} key(s) | batch: {settings['batch_size']}", "dim")

        # Count total blocks for progress bar
        self._total_blocks = 0
        self._progress_done = 0
        self._progress_vals = {}

        threading.Thread(
            target=self._run_translation,
            args=(selected, settings),
            daemon=True,
        ).start()

    def _stop_translation(self):
        if not self.is_running:
            return
        if messagebox.askyesno("Xác nhận", "Dừng tiến trình đang chạy?"):
            self._stop_flag = True
            self._log("⏹ Đã yêu cầu dừng...", "warn")

    def _run_translation(self, selected_files: list, settings: dict):
        self._stop_flag = False

        def log(msg, level="default"):
            self.after(0, lambda m=msg, l=level: self._log(m, l))

        def update_status(i, status):
            self.after(0, lambda idx=i, s=status: self._update_file_status(idx, s))

        def update_progress(total_done, total):
            pct = (total_done / total * 100) if total > 0 else 0
            self.after(0, lambda p=pct, d=total_done, t=total: (
                self.progress_var.set(p),
                self.progress_lbl.config(text=f"{d}/{t} blocks  ({p:.0f}%)"),
            ))

        # Count total blocks first
        total_blocks = 0
        file_data = []
        for i, f in selected_files:
            try:
                blocks = read_srt(f["path"])
                total_blocks += len(blocks)
                file_data.append((i, f, blocks))
            except Exception as exc:
                log(f"❌ Không đọc được: {f['name']} — {exc}", "error")
                update_status(i, "❌ Lỗi đọc file")

        if not file_data:
            self.after(0, self._on_translation_done)
            return

        done_blocks = [0]

        def progress_cb(chunk_idx, n):
            done_blocks[0] += n
            update_progress(done_blocks[0], total_blocks)

        # Translate each file
        for i, f, blocks in file_data:
            if self._stop_flag:
                update_status(i, "⏹ Đã dừng")
                continue

            update_status(i, "⚡ Đang dịch...")
            log(f"\n{'─'*50}", "dim")
            log(f"📄 Đang dịch: {f['name']}  ({len(blocks)} blocks)", "info")

            try:
                translated = translate_file(
                    blocks=blocks,
                    api_keys=settings["api_keys"],
                    model=settings["model"],
                    target_lang=settings["lang"],
                    content_type=settings["ctype"],
                    batch_size=settings["batch_size"],
                    glossary=settings["glossary"],
                    progress_cb=progress_cb,
                    log_cb=log,
                )

                # Write output
                out_path = get_output_path(f["path"], settings["lang_code"])
                write_srt(translated, out_path)
                log(f"💾 Đã lưu: {out_path}", "ok")
                update_status(i, "✅ Hoàn thành")

            except Exception as exc:
                log(f"❌ Lỗi khi dịch {f['name']}: {exc}", "error")
                update_status(i, "❌ Lỗi")

        self.after(0, self._on_translation_done)

    def _on_translation_done(self):
        self.is_running = False
        self.stop_btn.pack_forget()
        self.start_btn.pack(fill="x", pady=(0, 4))

        if not getattr(self, "_stop_flag", False):
            self._log("\n✅ ĐÃ HOÀN THÀNH TOÀN BỘ!", "ok")
            self.progress_var.set(100)
            # Flash title
            self.title("✅ Dịch xong! — Matrix Tool SRT-Translator V1")
            self.after(3000, lambda: self.title("Matrix Tool SRT-Translator V1"))
        else:
            self._log("\n⏹ Đã dừng.", "warn")
            self.progress_var.set(0)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
