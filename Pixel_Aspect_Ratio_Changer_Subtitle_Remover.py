# Pixel Aspect Ratio Changer + Subtitle Remover

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from fractions import Fraction
import subprocess
import sys
import os
import re
import math
import json
import threading

# ─── Windows DND support (pywin32 + ctypes for DragQueryFile) ──────────────
import ctypes
from ctypes import wintypes

WM_DROPFILES = 0x0233

_CallWindowProcW = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM
)(ctypes.windll.user32.CallWindowProcW)

# Correct ctypes signatures so large handle values don't overflow as int
_shell32 = ctypes.windll.shell32
_DragQueryFileW = _shell32.DragQueryFileW
_DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(wintypes.WCHAR), wintypes.UINT]
_DragQueryFileW.restype = wintypes.UINT
_DragFinish = _shell32.DragFinish
_DragFinish.argtypes = [ctypes.c_void_p]
_DragFinish.restype = ctypes.c_int


# ─── MP4Box helpers ──────────────────────────────────────────────────────

def get_mp4box_path():
    """Find mp4box.exe — bundled with PyInstaller or alongside the script."""
    candidates = []
    if hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, 'mp4box.exe'))
    base_dir = os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, 'frozen', False) else __file__
    ))
    candidates.append(os.path.join(base_dir, 'mp4box.exe'))
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def run_mp4box(args, timeout=60):
    """Run mp4box; returns (returncode, combined_text).

    mp4box writes info to stderr on Windows — merge stdout+stderr.
    """
    mp4box = get_mp4box_path()
    if mp4box is None:
        raise RuntimeError("mp4box.exe not found.")
    try:
        r = subprocess.run(
            [mp4box] + args,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=timeout
        )
        return r.returncode, r.stdout
    except subprocess.TimeoutExpired:
        return -1, "Timeout"


def extract_video_info(mp4_path):
    """Return (info_dict | None, error_msg | None)."""
    rc, text = run_mp4box(['-info', mp4_path], timeout=30)
    if rc != 0:
        return None, f"mp4box -info failed: {text}"

    # Dimensions
    m = re.search(r'Visual Size\s+(\d+)\s+x\s+(\d+)', text)
    if not m:
        m = re.search(r'width=(\d+)\s+height=(\d+)', text)
    if not m:
        return None, "Could not parse video dimensions"
    width, height = int(m.group(1)), int(m.group(2))

    # Track IDs
    video_track_id = None
    subtitle_track_ids = []
    lines = text.splitlines()
    cur_id = None
    for line in lines:
        tm = re.search(r'TrackID\s+(\d+)', line)
        if tm:
            cur_id = int(tm.group(1))
        if cur_id is not None:
            typ = re.search(r'Type\s+"(\w+):', line)
            if typ:
                pfx = typ.group(1)
                if pfx == 'vide' and video_track_id is None:
                    video_track_id = cur_id
                elif pfx in ('subt', 'text'):
                    subtitle_track_ids.append(cur_id)

    if video_track_id is None:
        return None, "Could not find video track ID"

    return {
        'width': width,
        'height': height,
        'video_track_id': video_track_id,
        'subtitle_track_ids': subtitle_track_ids,
    }, None



# ─── Settings persistence ──────────────────────────────────────────────

def _settings_path():
    """Return a path for a JSON settings file next to the script/executable."""
    base = os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, 'frozen', False) else __file__
    ))
    return os.path.join(base, 'settings.json')


def _load_output_dir():
    """Load the previously saved output directory, or None."""
    try:
        with open(_settings_path(), 'r') as f:
            data = json.load(f)
        return data.get('output_dir')
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_output_dir(path):
    """Save the output directory to the settings file."""
    try:
        with open(_settings_path(), 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data['output_dir'] = path
    with open(_settings_path(), 'w') as f:
        json.dump(data, f, indent=2)


def _ensure_default_output_dir():
    """Ensure a default output directory exists.

    Returns the output directory path:
    - previously saved one if available;
    - otherwise creates (if missing) and returns a 'Processed Files' folder
      next to the script/executable.
    """
    saved = _load_output_dir()
    if saved and os.path.isdir(saved):
        return saved

    base = os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, 'frozen', False) else __file__
    ))
    default = os.path.join(base, 'Processed Files')
    os.makedirs(default, exist_ok=True)
    return default


# ─── PAR calculation ─────────────────────────────────────────────────────

def calculate_par(width, height, dar_w=16, dar_h=9):
    """Return (fraction_str like "256:81", float_value)."""
    dar = dar_w / dar_h
    calculated_dar = width / height
    par = dar / calculated_dar
    frac = Fraction(par).limit_denominator(1000)
    return f"{frac.numerator}:{frac.denominator}", float(frac)


def parse_dar(dar_str):
    """Parse a DAR string like '16:9', '4/3', '2.35:1' → (dar_w, dar_h) ints.

    Raises ValueError on bad input.
    """
    dar_str = dar_str.strip()
    sep = re.search(r'[/:]', dar_str)
    if not sep:
        raise ValueError(f"Invalid DAR format: {dar_str!r}. Use 'W:H' or 'W/H'.")
    left, right = dar_str[:sep.start()], dar_str[sep.end():]
    left_f, right_f = float(left), float(right)
    if right_f == 0:
        raise ValueError("DAR denominator cannot be zero.")

    # Determine scale needed to convert both sides to integers.
    # We look at the raw text — each decimal digit means *10.
    scale = 1
    for token in (left, right):
        token = token.strip()
        dot = token.find('.')
        if dot != -1:
            digits = len(token[dot + 1:])
            scale *= (10 ** digits)

    left_i = int(round(left_f * scale))
    right_i = int(round(right_f * scale))
    g = math.gcd(left_i, right_i)
    return left_i // g, right_i // g


# ─── File processing ─────────────────────────────────────────────────────

def process_file(mp4_path, output_dir, dar_str="16:9", remove_subs=True):
    """Process one MP4 — set PAR + optionally remove subtitles.  Returns (ok, msg)."""
    info, err = extract_video_info(mp4_path)
    if info is None:
        return False, f"Extract info failed: {err}"

    try:
        dar_w, dar_h = parse_dar(dar_str)
    except ValueError as e:
        return False, f"Invalid DAR: {e}"

    par_str, _ = calculate_par(info['width'], info['height'], dar_w, dar_h)
    basename = os.path.splitext(os.path.basename(mp4_path))[0]
    output_path = os.path.join(output_dir, f"{basename}.mp4")

    cmd = ['-add', mp4_path]
    cmd.extend(['-par', f"{info['video_track_id']}={par_str}"])
    if remove_subs:
        for sid in info['subtitle_track_ids']:
            cmd.extend(['-rem', str(sid)])
    cmd.extend(['-new', output_path])

    rc, out_text = run_mp4box(cmd, timeout=300)
    if rc != 0:
        return False, f"mp4box failed (rc={rc}):\n{out_text}"

    if os.path.exists(output_path):
        msg = f"{info['width']}x{info['height']}  →  PAR {par_str}"
        if remove_subs:
            subs = info['subtitle_track_ids'] if info['subtitle_track_ids'] else "none"
            msg += f"  subs removed: {subs}"
        else:
            msg += "  subs kept"
        return True, msg
    return False, "mp4box ran but output file was not created"


# ─── GUI ─────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Pixel Aspect Ratio Changer + Subtitle Remover")
        self.root.geometry("640x450")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1b26")

        self.file_list = []
        self.processing = False
        # Auto-determine output directory: saved choice or default 'Processed Files'
        self.output_dir = _ensure_default_output_dir()

        # Colours
        BG      = "#1a1b26"
        CARD    = "#24283b"
        FG      = "#c0caf5"
        ACCENT  = "#7aa2f7"
        GREEN   = "#9ece6a"
        RED     = "#f7768e"
        MUTED   = "#565f89"

        # ── Drop zone ────────────────────────────────────────────────
        self.drop_frame = tk.Frame(root, bg=CARD, height=100,
                                   highlightbackground="#414868", highlightthickness=2)
        self.drop_frame.pack(fill="x", padx=14, pady=10)
        self.drop_frame.pack_propagate(False)

        self.drop_icon = tk.Label(self.drop_frame, text="📂", font=("Segoe UI Emoji", 28),
                                  bg=CARD, fg=FG)
        self.drop_icon.place(relx=0.15, rely=0.4, anchor="center")

        self.drop_label = tk.Label(self.drop_frame,
                                   text="Drag & Drop MP4 Files or Folders here\nor click Browse",
                                   font=("Segoe UI", 10), bg=CARD, fg=MUTED, justify="center")
        self.drop_label.place(relx=0.55, rely=0.4, anchor="center")

        self.drop_frame.bind("<Button-1>", self._browse)
        self.drop_frame.configure(cursor="hand2")

        # Hover effect
        def on_enter(_e):
            self.drop_frame.configure(highlightbackground=ACCENT)
        def on_leave(_e):
            self.drop_frame.configure(highlightbackground="#414868")
        self.drop_frame.bind("<Enter>", on_enter)
        self.drop_frame.bind("<Leave>", on_leave)

        # ── File list ────────────────────────────────────────────────
        list_frame = tk.Frame(root, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        hdr = tk.Label(list_frame, text="Files & Status", font=("Segoe UI", 9, "bold"),
                       bg=BG, fg=MUTED)
        hdr.pack(anchor="nw")

        self.txt = tk.Text(list_frame, height=12,
                           font=("Consolas", 9), bg="#16171a", fg=FG,
                           insertbackground=ACCENT, state="disabled",
                           highlightthickness=0, wrap="word")
        vsb = ttk.Scrollbar(list_frame, command=self.txt.yview)
        self.txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True)

        # ── Info bar ─────────────────────────────────────────────────
        self.info_var = tk.StringVar(value=None)
        self.info_lbl = tk.Label(root, textvariable=self.info_var,
                                 font=("Segoe UI", 9), bg=BG, fg=MUTED, anchor="w")
        self.info_lbl.pack(fill="x", padx=16, pady=(0, 4))

        # ── DAR input ────────────────────────────────────────────────
        dar_row = tk.Frame(root, bg=BG)
        dar_row.pack(fill="x", padx=16, pady=(0, 2))

        tk.Label(dar_row, text="Desired Aspect Ratio:", font=("Segoe UI", 9),
                 bg=BG, fg=MUTED, anchor="e").pack(side="left")

        # Use ttk.Entry with themed styling — avoids the Windows Tk bug where
        # custom bg on tk.Entry blocks keyboard events (select_range in <FocusIn>).
        self.style = ttk.Style()
        self.style.theme_use('clam')  # 'clam' theme respects fieldbackground on Windows
        self.style.configure(
            "DAR.TEntry",
            fieldbackground="#16171a",
            foreground=FG,
            font=("Consolas", 9),
            padding=3
        )
        # ttk.Entry doesn't support justify directly; we'll center via width/padding
        self.dar_entry = ttk.Entry(dar_row, style="DAR.TEntry", width=8)
        self.dar_entry.insert(0, "16:9")
        self.dar_entry.pack(side="left", padx=(6, 0))

        # Input validation — only digits and ':' allowed; editing keys pass through
        _dar_edit_keys = frozenset(
            ('BackSpace', 'Delete', 'Home', 'End', 'Left', 'Right',
             'SelectAll', 'Key_A', 'Key_C', 'Key_V', 'Key_X')
        )
        def _dar_valid(_event):
            if _event.keysym in _dar_edit_keys:
                return  # editing / navigation keys always allowed
            ch = _event.char
            if ch and not (ch.isdigit() or ch == ":"):
                return "break"
        self.dar_entry.bind("<KeyPress>", _dar_valid)

        # Select all text on focus so user can type immediately to replace it.
        def _select_dar(_event=None):
            self.dar_entry.selection_range(0, "end")
        self.dar_entry.bind("<FocusIn>", _select_dar)

        # ── Remove Subtitles checkbox ────────────────────────────────
        tk.Label(dar_row, text="", bg=BG, width=2).pack(side="left")
        self.remove_subs_var = tk.BooleanVar(value=False)
        subs_cb = tk.Checkbutton(
            dar_row, text="Remove Subtitles", variable=self.remove_subs_var,
            font=("Segoe UI", 9), bg=BG, fg=FG,
            activebackground=BG, selectcolor=CARD, anchor="w", cursor="hand2"
        )
        subs_cb.pack(side="left")

        # ── Progress ─────────────────────────────────────────────────
        self.style = ttk.Style()
        self.style.configure("custom.Horizontal.TProgressbar",
                             background=ACCENT, troughcolor="#16171a", thickness=8)
        self.pbar = ttk.Progressbar(root, style="custom.Horizontal.TProgressbar",
                                    mode="determinate", length=600)
        self.pbar.pack(padx=16, pady=(0, 6))

        # ── Buttons ──────────────────────────────────────────────────
        btn_row = tk.Frame(root, bg=BG)
        btn_row.pack(fill="x", padx=14, pady=6)

        self._btn("📁 Browse", self._browse, btn_row, side="left")
        self._btn("🗑 Clear",  self._clear,  btn_row, side="left")
        tk.Label(btn_row, text="", bg=BG, width=2).pack(side="left")
        self._btn("📂 Output Dir",  self._pick_output, btn_row, side="right")
        self.proc_btn = self._btn("▶  Process", self._start_process, btn_row,
                                  side="right", bg=GREEN, state="disabled")

        # ── CLI args ─────────────────────────────────────────────────
        for arg in sys.argv[1:]:
            for mp4 in self._collect_mp4s(arg):
                self.add_file(mp4)

        # ── Windows drag-and-drop hook ───────────────────────────────
        self._setup_win_dnd()

    def _btn(self, text, cmd, master, side="left", bg="#3b4261", **kw):
        b = tk.Button(master, text=text, command=cmd, font=("Segoe UI", 9),
                      width=10, bg=bg, fg="#e1e5ee", padx=6, pady=3,
                      activebackground="#474c68", activeforeground="white",
                      relief="flat", cursor="hand2")
        b.config(**kw)
        b.pack(side=side, padx=3)
        return b

    def _dnd_log(self, msg):
        """Append a DND diagnostic message to the app text area."""
        self._append_text(msg + "\n", color="#7aa2f7")

    # -- Windows DND via pywin32 --
    def _setup_win_dnd(self):
        try:
            import win32gui  # ensures pywin32 is available
            self.root.after(200, self._enable_dnd_delayed)
        except ImportError as e:
            self._dnd_log(f"pywin32 not available ({e}), DND disabled")
        except Exception as e:
            self._dnd_log(f"Setup failed: {e}")

    def _enable_dnd_delayed(self):
        import win32gui

        try:
            # Apply DND to the drop frame window, NOT the root Tk window.
            # Subclassing the root's WNDPROC breaks Tk's message pump for
            # keyboard input on child widgets (see: DAR entry box issue).
            target = self.drop_frame
            hwnd = int(target.winfo_id())

            # --- DragAcceptFiles (shell32) ---
            result = ctypes.windll.shell32.DragAcceptFiles(hwnd, True)
            if not result:
                self._dnd_log(f"DragAcceptFiles returned FALSE (hwnd=0x{hwnd:x})")
                return

            # --- Subclass WNDPROC on drop frame only ---
            GWLP_WNDPROC = -4
            original_proc = win32gui.GetWindowLong(hwnd, GWLP_WNDPROC)
            self._dnd_original_proc = original_proc  # keep alive (no GC)

            def wnd_callback(h, msg, wp, lp):
                if msg == WM_DROPFILES:
                    try:
                        count = _DragQueryFileW(wp, -1, None, 0)
                        dropped_paths = []
                        for i in range(count):
                            buf = ctypes.create_unicode_buffer(260)
                            _DragQueryFileW(wp, i, buf, 260)
                            dropped_paths.append(buf.value)
                        _DragFinish(wp)
                        mp4s = []
                        for dp in dropped_paths:
                            mp4s.extend(self._collect_mp4s(dp))
                        added = sum(1 for f in mp4s if self.add_file(f))
                        self._dnd_log(f"Added {added} mp4(s).")
                    except Exception as e:
                        self._dnd_log(f"error querying drop: {e}")
                    return 0
                # Forward to original proc
                return _CallWindowProcW(self._dnd_original_proc, h, msg, wp, lp)

            win32gui.SetWindowLong(hwnd, GWLP_WNDPROC, wnd_callback)



        except Exception as e:
            self._dnd_log(f"enable failed: {type(e).__name__}: {e}")

    @staticmethod
    def _collect_mp4s(path):
        """Return a list of .mp4 paths from *path*.

        If *path* is a file → return it (if .mp4).
        If *path* is a directory  → walk the tree and return all .mp4 files.
        """
        if os.path.isfile(path) and path.lower().endswith(".mp4"):
            return [path]
        if os.path.isdir(path):
            mp4s = []
            for root, _dirs, files in os.walk(path):
                for fname in files:
                    if fname.lower().endswith(".mp4"):
                        mp4s.append(os.path.join(root, fname))
            return mp4s
        return []

    # -- file management --
    def _browse(self, event=None):
        files = filedialog.askopenfilenames(
            title="Select MP4 Files", filetypes=[("MP4 Files", "*.mp4")]
        )
        for f in files:
            self.add_file(f)

    def add_file(self, path):
        if path not in self.file_list and os.path.isfile(path):
            self.file_list.append(path)
            self._append_text(os.path.basename(path) + "\n", color="#c0caf5")
            self._update_info()
            if not self.processing and self.output_dir:
                self.proc_btn.config(state="normal")
            return True
        return False

    def _clear(self):
        self.file_list.clear()
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.config(state="disabled")
        self.pbar['value'] = 0
        self._update_info()
        if not self.processing:
            self.proc_btn.config(state="disabled")

    def _update_info(self):
        """Update the info bar — shows file count and output directory."""
        if self.output_dir:
            self.info_var.set(f"Files: {len(self.file_list)}   |   Output: {self.output_dir}")
        else:
            self.info_var.set('Output folder not set')

    def _pick_output(self):
        d = filedialog.askdirectory(title="Choose Output Directory")
        if d:
            self.output_dir = d
            _save_output_dir(d)
            self._update_info()
            # Enable Process button now that we have a destination
            if not self.processing and self.file_list:
                self.proc_btn.config(state="normal", bg="#9ece6a")

    # -- processing --
    def _start_process(self):
        if not self.file_list or self.processing:
            return
        # Require output folder before processing
        if not self.output_dir:
            messagebox.showwarning("No Output Folder",
                                  "Please select an output folder first.\n\nClick 📂 Output Dir to choose a destination.")
            return
        # Validate DAR before starting
        try:
            parse_dar(self.dar_entry.get())
        except ValueError as e:
            messagebox.showerror("Invalid DAR", str(e))
            return
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        dar_str = self.dar_entry.get()
        self.processing = True
        self._tk(lambda: self.proc_btn.config(state="disabled", bg="#3b4261"))
        self._tk(lambda: self.info_var.set("Processing…"))
        self._tk(lambda: self._append_text("\n── processing ──\n", color="#565f89"))

        total = len(self.file_list)
        ok = fail = 0

        for i, fp in enumerate(self.file_list, 1):
            if not os.path.isfile(fp):
                self._tk(lambda fn=os.path.basename(fp):
                         self._append_text(f"⊘ SKIP {fn} (not found)\n", color="#f7768e"))
                fail += 1
                continue

            self._tk(lambda n=os.path.basename(fp), ix=i, t=total:
                     self._append_text(f"[{ix}/{t}] {n} …\n", color="#c0caf5"))
            self._tk(lambda prog=i * 100 // total: self._set_prog(prog))

            s, msg = process_file(fp, self.output_dir, dar_str, remove_subs=self.remove_subs_var.get())
            if s:
                ok += 1
                self._tk(lambda m=msg: self._append_text(f"  ✓ {m}\n", color="#9ece6a"))
            else:
                fail += 1
                self._tk(lambda m=msg: self._append_text(f"  ✗ {m}\n", color="#f7768e"))

        self._tk(lambda: self._set_prog(100))
        self._tk(lambda: self.info_var.set(f"Done — ✓ {ok}   ✗ {fail}"))
        self._tk(lambda: self._append_text(
            f"\n═══ complete: {ok} ok, {fail} failed ═══\n", color="#7aa2f7"))

        self.processing = False
        self._tk(lambda: self.proc_btn.config(state="normal", bg="#9ece6a"))

    # -- Tk threading helpers --
    def _tk(self, fn):
        self.root.after(0, fn)

    def _set_prog(self, v):
        self.pbar['value'] = v

    def _append_text(self, msg, color=None):
        self.txt.config(state="normal")
        if color:
            self.txt.tag_configure(color, foreground=color)
            self.txt.insert("end", msg, color)
        else:
            self.txt.insert("end", msg)
        self.txt.config(state="disabled")
        self.txt.see("end")


# ─── Entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
