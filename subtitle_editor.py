from __future__ import annotations

import json
import math
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = ImageTk = ImageDraw = ImageFont = None


@dataclass
class Cue:
    index: int
    start: float
    end: float
    text: str


@dataclass
class SubtitleStyle:
    font: str = "Microsoft JhengHei UI"
    size: int = 30
    bold: bool = False
    italic: bool = False
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline: int = 3
    shadow: int = 1
    position: str = "bottom"
    margin_v: int = 40
    opacity: int = 100


def parse_ts(value: str) -> float:
    value = value.strip().replace('.', ',')
    hms, ms = value.split(',')
    h, m, s = [int(x) for x in hms.split(':')]
    return h * 3600 + m * 60 + s + int(ms.ljust(3, '0')[:3]) / 1000.0


def format_ts(seconds: float) -> str:
    total = max(0, int(round(seconds * 1000)))
    h, rem = divmod(total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(path: Path) -> list[Cue]:
    raw = path.read_text(encoding='utf-8-sig', errors='replace').replace('\r\n', '\n')
    cues: list[Cue] = []
    for block in raw.split('\n\n'):
        lines = [x for x in block.split('\n') if x.strip()]
        if len(lines) < 3 or '-->' not in lines[1]:
            continue
        try:
            idx = int(lines[0].strip())
            start_s, end_s = [x.strip().split(' ')[0] for x in lines[1].split('-->', 1)]
            cues.append(Cue(idx, parse_ts(start_s), parse_ts(end_s), '\n'.join(lines[2:])))
        except Exception:
            continue
    return cues


def write_srt(path: Path, cues: list[Cue]) -> None:
    blocks = []
    for n, cue in enumerate(cues, 1):
        cue.index = n
        end = max(cue.start + 0.05, cue.end)
        blocks.append(f"{n}\n{format_ts(cue.start)} --> {format_ts(end)}\n{cue.text.strip()}\n")
    path.write_text('\n'.join(blocks), encoding='utf-8-sig')


def load_json_cues(path: Path) -> list[Cue]:
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    return [Cue(i + 1, float(x.get('start', 0)), float(x.get('end', 0)), str(x.get('text', ''))) for i, x in enumerate(data.get('segments', []))]


def copy_cues(cues: list[Cue]) -> list[Cue]:
    return [Cue(c.index, c.start, c.end, c.text) for c in cues]


def find_ffmpeg() -> str | None:
    roots = [Path(__file__).resolve().parent / 'runtime' / 'ffmpeg', Path(__file__).resolve().parent]
    for root in roots:
        for name in ('ffmpeg.exe', 'ffmpeg'):
            p = root / name
            if p.exists():
                return str(p)
    import shutil
    return shutil.which('ffmpeg')


def preview_font(style: SubtitleStyle):
    if ImageFont is None:
        return None
    candidates = []
    windir = Path(os.environ.get('WINDIR', r'C:\\Windows'))
    names = {
        'Microsoft JhengHei UI': ['msjh.ttc', 'msjhl.ttc'],
        'Microsoft JhengHei': ['msjh.ttc'],
        'PMingLiU': ['mingliu.ttc'],
        'MingLiU': ['mingliu.ttc'],
        'Arial': ['arial.ttf'],
    }
    for name in names.get(style.font, ['msjh.ttc', 'mingliu.ttc']):
        candidates.append(windir / 'Fonts' / name)
    candidates += [Path(__file__).resolve().parent / 'resources' / 'fonts' / 'NotoSansCJKtc-Regular.otf']
    for p in candidates:
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), max(10, int(style.size * 0.78)))
            except Exception:
                pass
    return ImageFont.load_default()


def hex_to_ass(color: str, alpha: int = 0) -> str:
    value = color.lstrip('#')
    if len(value) != 6:
        value = 'FFFFFF'
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    a = max(0, min(255, int(alpha)))
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


def ass_escape(text: str) -> str:
    return text.replace('\\', r'\\').replace('{', r'\\{').replace('}', r'\\}')


class SubtitleEditor(ttk.Frame):
    def __init__(self, master, on_status=None):
        super().__init__(master)
        self.on_status = on_status or (lambda _x: None)
        self.cues: list[Cue] = []
        self.srt_path: Path | None = None
        self.video_path: Path | None = None
        self.cap = None
        self.fps = 25.0
        self.duration = 0.0
        self.playing = False
        self.preview_t = 0.0
        self._photo = None
        self._play_thread = None
        self._stop_play = threading.Event()
        self._wave_thread = None
        self._wave_id = 0
        self.waveform: list[float] = []
        self.current_index = -1
        self.undo_stack: list[list[Cue]] = []
        self.redo_stack: list[list[Cue]] = []
        self.style = SubtitleStyle()
        self._timeline_drag = None
        self._style_preview_dirty = True
        self._build()
        self.after(60, self._tick)

    # ---------- UI ----------
    def _build(self):
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=0)
        self.columnconfigure(0, weight=1)

        main = ttk.Frame(self, padding=8)
        main.grid(row=0, column=0, sticky='nsew')
        main.rowconfigure(0, weight=3)
        main.rowconfigure(1, weight=2)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)

        # Preview
        preview_wrap = ttk.LabelFrame(main, text='影片預覽', padding=6)
        preview_wrap.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        preview_wrap.rowconfigure(0, weight=1)
        preview_wrap.columnconfigure(0, weight=1)
        self.preview = tk.Label(preview_wrap, text='載入影片後顯示預覽', bg='#111318', fg='#d0d5dd', anchor='center')
        self.preview.grid(row=0, column=0, sticky='nsew')
        self.preview.bind('<Button-1>', lambda _e: self.toggle_play())
        self.preview.bind('<Configure>', lambda _e: self._show_frame(self.preview_t))

        controls = ttk.Frame(preview_wrap)
        controls.grid(row=1, column=0, sticky='ew', pady=(6, 0))
        ttk.Button(controls, text='⏮ 5s', command=lambda: self.seek(self.preview_t - 5)).pack(side='left')
        ttk.Button(controls, text='▶ / ❚❚', command=self.toggle_play).pack(side='left', padx=4)
        ttk.Button(controls, text='5s ⏭', command=lambda: self.seek(self.preview_t + 5)).pack(side='left')
        self.time_label = ttk.Label(controls, text='00:00:00.000 / 00:00:00.000')
        self.time_label.pack(side='left', padx=10)

        self.seek_var = tk.DoubleVar(value=0)
        ttk.Scale(preview_wrap, from_=0, to=100, variable=self.seek_var, command=self._on_seekbar).grid(row=2, column=0, sticky='ew', pady=(5, 0))

        # Editor side
        side = ttk.Notebook(main)
        side.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        cues_tab = ttk.Frame(side, padding=4)
        style_tab = ttk.Frame(side, padding=8)
        side.add(cues_tab, text='字幕')
        side.add(style_tab, text='樣式')

        cues_tab.rowconfigure(1, weight=1); cues_tab.columnconfigure(0, weight=1)
        top = ttk.Frame(cues_tab)
        top.grid(row=0, column=0, sticky='ew')
        ttk.Button(top, text='載入 SRT', command=self.load_srt_dialog).pack(side='left')
        ttk.Button(top, text='儲存 SRT', command=self.save_srt).pack(side='left', padx=4)
        ttk.Button(top, text='另存', command=self.save_srt_as).pack(side='left')
        ttk.Button(top, text='Undo', command=self.undo).pack(side='right')
        ttk.Button(top, text='Redo', command=self.redo).pack(side='right', padx=4)

        tree_frame = ttk.Frame(cues_tab)
        tree_frame.grid(row=1, column=0, sticky='nsew', pady=(6, 6))
        tree_frame.rowconfigure(0, weight=1); tree_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_frame, columns=('start', 'end', 'text'), show='headings', selectmode='browse')
        for col, heading, width in [('start','開始',95), ('end','結束',95), ('text','字幕',280)]:
            self.tree.heading(col, text=heading); self.tree.column(col, width=width, anchor='w' if col == 'text' else 'center')
        self.tree.grid(row=0, column=0, sticky='nsew')
        sy = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tree.yview); sy.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.bind('<<TreeviewSelect>>', self._select_cue)

        edit = ttk.LabelFrame(cues_tab, text='選取字幕', padding=7)
        edit.grid(row=2, column=0, sticky='ew')
        edit.columnconfigure(3, weight=1)
        ttk.Label(edit, text='開始').grid(row=0, column=0, sticky='w')
        self.start_var = tk.StringVar(value='00:00:00.000')
        ttk.Entry(edit, textvariable=self.start_var, width=14).grid(row=0, column=1, padx=4)
        ttk.Label(edit, text='結束').grid(row=0, column=2, sticky='w')
        self.end_var = tk.StringVar(value='00:00:00.000')
        ttk.Entry(edit, textvariable=self.end_var, width=14).grid(row=0, column=3, padx=4, sticky='w')
        ttk.Button(edit, text='套用', command=self.apply_times).grid(row=0, column=4)
        ttk.Label(edit, text='文字').grid(row=1, column=0, sticky='nw', pady=(5,0))
        self.text = tk.Text(edit, height=4, wrap='word', font=('Microsoft JhengHei UI', 10))
        self.text.grid(row=1, column=1, columnspan=4, sticky='ew', pady=(5,0))
        ttk.Button(edit, text='套用文字', command=self.apply_text).grid(row=2, column=4, sticky='e', pady=(5,0))

        # Style tab
        style_tab.columnconfigure(1, weight=1)
        style_tab.columnconfigure(3, weight=1)
        self._add_style_controls(style_tab)

        # Timeline
        timeline = ttk.LabelFrame(main, text='時間軸 / 波形', padding=5)
        timeline.grid(row=1, column=0, columnspan=2, sticky='nsew', pady=(8,0))
        timeline.rowconfigure(1, weight=1); timeline.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(timeline, height=120, bg='#11141b', highlightthickness=0)
        self.canvas.grid(row=0, column=0, rowspan=2, sticky='nsew')
        self.canvas.bind('<Configure>', lambda _e: self.draw_timeline())
        self.canvas.bind('<Button-1>', self._timeline_mouse_down)
        self.canvas.bind('<B1-Motion>', self._timeline_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self._timeline_mouse_up)
        legend = ttk.Label(timeline, text='拖曳字幕區塊移動；拖曳區塊左右邊緣調整長度', foreground='#667085')
        legend.grid(row=2, column=0, sticky='w', pady=(3,0))

        # Actions
        bottom = ttk.Frame(self, padding=(8, 6))
        bottom.grid(row=1, column=0, sticky='ew')
        for text, cmd in [
            ('新增', self.add_cue), ('刪除', self.delete_cue), ('合併下一句', self.merge_next),
            ('切兩句', self.split_current), ('目前設開始', self.set_start_now), ('目前設結束', self.set_end_now),
            ('載入影片', self.load_media_dialog),
        ]:
            ttk.Button(bottom, text=text, command=cmd).pack(side='left', padx=(0,4))
        ttk.Button(bottom, text='🔥 燒字輸出 MP4', command=self.burn_subtitles, style='Accent.TButton').pack(side='left', padx=(12,0))
        self.status = ttk.Label(bottom, text='尚未載入字幕')
        self.status.pack(side='right')

    def _add_style_controls(self, box):
        ttk.Label(box, text='字型').grid(row=0, column=0, sticky='w', pady=5)
        self.font_var = tk.StringVar(value=self.style.font)
        fonts = ['Microsoft JhengHei UI', 'Microsoft JhengHei', 'PMingLiU', 'MingLiU', 'Arial']
        ttk.Combobox(box, textvariable=self.font_var, values=fonts, state='readonly').grid(row=0, column=1, columnspan=3, sticky='ew', padx=5)
        ttk.Label(box, text='大小').grid(row=1, column=0, sticky='w', pady=5)
        self.size_var = tk.IntVar(value=self.style.size)
        ttk.Spinbox(box, from_=12, to=96, textvariable=self.size_var, width=8).grid(row=1, column=1, sticky='w', padx=5)
        self.bold_var = tk.BooleanVar(value=self.style.bold)
        self.italic_var = tk.BooleanVar(value=self.style.italic)
        ttk.Checkbutton(box, text='粗體', variable=self.bold_var, command=self._style_changed).grid(row=1, column=2, sticky='w')
        ttk.Checkbutton(box, text='斜體', variable=self.italic_var, command=self._style_changed).grid(row=1, column=3, sticky='w')
        ttk.Label(box, text='位置').grid(row=2, column=0, sticky='w', pady=5)
        self.pos_var = tk.StringVar(value=self.style.position)
        ttk.Combobox(box, textvariable=self.pos_var, values=('bottom','middle','top'), state='readonly', width=12).grid(row=2, column=1, sticky='w', padx=5)
        ttk.Label(box, text='垂直邊距').grid(row=2, column=2, sticky='w')
        self.margin_var = tk.IntVar(value=self.style.margin_v)
        ttk.Spinbox(box, from_=0, to=300, textvariable=self.margin_var, width=8).grid(row=2, column=3, sticky='w', padx=5)
        ttk.Label(box, text='外框').grid(row=3, column=0, sticky='w', pady=5)
        self.outline_var = tk.IntVar(value=self.style.outline)
        ttk.Spinbox(box, from_=0, to=12, textvariable=self.outline_var, width=8).grid(row=3, column=1, sticky='w', padx=5)
        ttk.Label(box, text='陰影').grid(row=3, column=2, sticky='w')
        self.shadow_var = tk.IntVar(value=self.style.shadow)
        ttk.Spinbox(box, from_=0, to=8, textvariable=self.shadow_var, width=8).grid(row=3, column=3, sticky='w', padx=5)
        self.color_btn = ttk.Button(box, text='文字顏色', command=lambda: self._pick_color('color'))
        self.color_btn.grid(row=4, column=0, columnspan=2, sticky='ew', pady=5)
        self.outline_color_btn = ttk.Button(box, text='外框顏色', command=lambda: self._pick_color('outline'))
        self.outline_color_btn.grid(row=4, column=2, columnspan=2, sticky='ew', pady=5)
        self.style_info = ttk.Label(box, text='樣式會同步到預覽，燒字輸出使用同樣設定。', foreground='#667085', wraplength=320)
        self.style_info.grid(row=5, column=0, columnspan=4, sticky='w', pady=(10,0))
        for var in (self.font_var, self.size_var, self.pos_var, self.margin_var, self.outline_var, self.shadow_var):
            try: var.trace_add('write', lambda *_a: self._style_changed())
            except Exception: pass

    # ---------- style ----------
    def _style_changed(self):
        try:
            self.style.font = self.font_var.get()
            self.style.size = int(self.size_var.get())
            self.style.bold = bool(self.bold_var.get())
            self.style.italic = bool(self.italic_var.get())
            self.style.position = self.pos_var.get()
            self.style.margin_v = int(self.margin_var.get())
            self.style.outline = int(self.outline_var.get())
            self.style.shadow = int(self.shadow_var.get())
        except Exception:
            return
        self._show_frame(self.preview_t)

    def _pick_color(self, which):
        initial = self.style.color if which == 'color' else self.style.outline_color
        value = colorchooser.askcolor(color=initial, parent=self.winfo_toplevel())[1]
        if value:
            if which == 'color': self.style.color = value
            else: self.style.outline_color = value
            self._show_frame(self.preview_t)

    # ---------- file/media ----------
    def load_media(self, path: str | Path):
        p = Path(path)
        self.video_path = p
        self._release_video()
        if cv2 is None:
            self._set_status('缺少 OpenCV')
            return
        self.cap = cv2.VideoCapture(str(p))
        if not self.cap.isOpened():
            self._set_status(f'無法開啟影片：{p.name}')
            return
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 25.0)
        frames = float(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.duration = frames / self.fps if self.fps else 0.0
        self.seekbar = next((w for w in self.winfo_children() if False), None)  # compatibility no-op
        # Reconfigure the first Scale child under the preview wrapper.
        try:
            for child in self.winfo_children():
                pass
        except Exception:
            pass
        self._configure_seekbar(self.duration)
        self._set_status(f'影片：{p.name}')
        self.seek(0)
        self._start_waveform_job(p)

    def _configure_seekbar(self, duration):
        # Scale is nested in preview_wrap; find recursively.
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, ttk.Scale):
                    return c
                hit = walk(c)
                if hit: return hit
        scale = walk(self)
        if scale:
            scale.configure(to=max(0.001, duration))
            self.seekbar_widget = scale

    def _release_video(self):
        self.playing = False
        self._stop_play.set()
        if self.cap is not None:
            try: self.cap.release()
            except Exception: pass
        self.cap = None

    def load_srt(self, path: str | Path):
        p = Path(path)
        self.cues = parse_srt(p); self.srt_path = p
        self.undo_stack.clear(); self.redo_stack.clear()
        self.refresh_tree()
        if self.cues: self.select_index(0)
        self._set_status(f'已載入 {len(self.cues)} 個字幕')

    def load_json(self, path: str | Path):
        p = Path(path)
        self.cues = load_json_cues(p); self.srt_path = p.with_suffix('.srt')
        self.undo_stack.clear(); self.redo_stack.clear(); self.refresh_tree()
        if self.cues: self.select_index(0)
        self._set_status(f'已載入 JSON：{len(self.cues)} 個字幕')

    def load_media_dialog(self):
        p = filedialog.askopenfilename(filetypes=[('Video', '*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.ts'), ('All files', '*.*')])
        if p: self.load_media(p)

    def load_srt_dialog(self):
        p = filedialog.askopenfilename(filetypes=[('SRT', '*.srt'), ('All files', '*.*')])
        if p: self.load_srt(p)

    def save_srt(self):
        if not self.cues:
            messagebox.showwarning('沒有字幕', '目前沒有可儲存的字幕。'); return
        if self.srt_path is None or self.srt_path.suffix.lower() != '.srt': return self.save_srt_as()
        write_srt(self.srt_path, self.cues); self._set_status(f'已儲存：{self.srt_path.name}')

    def save_srt_as(self):
        if not self.cues: return
        p = filedialog.asksaveasfilename(defaultextension='.srt', filetypes=[('SRT', '*.srt')], initialfile=(self.srt_path.name if self.srt_path else 'subtitles.srt'))
        if p:
            self.srt_path = Path(p); write_srt(self.srt_path, self.cues); self._set_status(f'已儲存：{self.srt_path.name}')

    # ---------- editing ----------
    def _set_status(self, text): self.status.configure(text=text); self.on_status(text)
    def snapshot(self): return copy_cues(self.cues)
    def push_undo(self):
        self.undo_stack.append(self.snapshot()); self.redo_stack.clear()
        if len(self.undo_stack) > 100: self.undo_stack.pop(0)
    def undo(self):
        if self.undo_stack: self.redo_stack.append(self.snapshot()); self.cues = self.undo_stack.pop(); self.refresh_tree()
    def redo(self):
        if self.redo_stack: self.undo_stack.append(self.snapshot()); self.cues = self.redo_stack.pop(); self.refresh_tree()

    def refresh_tree(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for i, cue in enumerate(self.cues):
            cue.index = i + 1
            self.tree.insert('', 'end', iid=str(i), values=(format_ts(cue.start), format_ts(cue.end), cue.text.replace('\n', ' / ')))
        self.draw_timeline(); self._show_frame(self.preview_t)

    def select_index(self, index):
        if 0 <= index < len(self.cues):
            self.tree.selection_set(str(index)); self.tree.focus(str(index)); self.tree.see(str(index)); self._select_index(index)

    def _select_cue(self, _event=None):
        sel = self.tree.selection()
        if sel: self._select_index(int(sel[0]))

    def _select_index(self, index):
        if not 0 <= index < len(self.cues): return
        self.current_index = index; cue = self.cues[index]
        self.start_var.set(format_ts(cue.start)); self.end_var.set(format_ts(cue.end))
        self.text.delete('1.0', 'end'); self.text.insert('1.0', cue.text)
        self.seek(cue.start)

    def apply_times(self):
        if self.current_index < 0: return
        try: start, end = parse_ts(self.start_var.get()), parse_ts(self.end_var.get())
        except Exception: messagebox.showerror('時間格式錯誤', '請使用 HH:MM:SS,mmm'); return
        if end <= start: messagebox.showerror('時間錯誤', '結束時間必須晚於開始時間。'); return
        self.push_undo(); self.cues[self.current_index].start = start; self.cues[self.current_index].end = end
        self.refresh_tree(); self.select_index(self.current_index)

    def apply_text(self):
        if self.current_index < 0: return
        self.push_undo(); self.cues[self.current_index].text = self.text.get('1.0', 'end').strip(); self.refresh_tree(); self.select_index(self.current_index)

    def add_cue(self):
        self.push_undo(); start = self.preview_t; end = min(self.duration if self.duration else start + 2, start + 2)
        idx = self.current_index + 1 if self.current_index >= 0 else len(self.cues)
        self.cues.insert(idx, Cue(0, start, max(start + .2, end), ''))
        self.refresh_tree(); self.select_index(idx); self.text.focus_set()

    def delete_cue(self):
        if self.current_index < 0: return
        idx = self.current_index; self.push_undo(); del self.cues[idx]; self.current_index = -1; self.refresh_tree()
        if self.cues: self.select_index(min(idx, len(self.cues)-1))

    def merge_next(self):
        i = self.current_index
        if i < 0 or i + 1 >= len(self.cues): return
        self.push_undo(); a, b = self.cues[i], self.cues[i+1]; a.end = max(a.end,b.end); a.text = (a.text.rstrip()+' '+b.text.lstrip()).strip(); del self.cues[i+1]
        self.refresh_tree(); self.select_index(i)

    def split_current(self):
        i = self.current_index
        if i < 0: return
        cue = self.cues[i]; parts = cue.text.split() if '\n' not in cue.text else cue.text.split('\n')
        if len(parts) < 2 or cue.end - cue.start < .4: return
        mid=(cue.start+cue.end)/2; half=max(1,len(parts)//2); self.push_undo(); old_end=cue.end; cue.end=mid; cue.text=' '.join(parts[:half]); self.cues.insert(i+1,Cue(0,mid,old_end,' '.join(parts[half:])))
        self.refresh_tree(); self.select_index(i+1)

    def set_start_now(self):
        if self.current_index >= 0: self.start_var.set(format_ts(self.preview_t)); self.apply_times()
    def set_end_now(self):
        if self.current_index >= 0: self.end_var.set(format_ts(max(self.preview_t, self.cues[self.current_index].start+.05))); self.apply_times()

    # ---------- playback ----------
    def seek(self, seconds):
        self.preview_t = max(0, min(float(seconds), self.duration if self.duration else float(seconds)))
        if hasattr(self,'seekbar_widget'): self.seekbar_widget.set(self.preview_t)
        self._show_frame(self.preview_t); self._select_timeline_cue(); self.draw_timeline()

    def _on_seekbar(self, value): self.seek(float(value))
    def toggle_play(self):
        if self.cap is None or self.duration <= 0: return
        self.playing = not self.playing
        if self.playing:
            self._stop_play.clear()
            if self._play_thread is None or not self._play_thread.is_alive(): self._play_thread=threading.Thread(target=self._play_loop,daemon=True); self._play_thread.start()
    def _play_loop(self):
        last=time.perf_counter()
        while not self._stop_play.is_set() and self.playing:
            now=time.perf_counter(); dt=max(0,now-last); last=now; next_t=self.preview_t+dt
            if next_t >= self.duration: self.playing=False; next_t=self.duration
            self.after(0, lambda t=next_t: self.seek(t)); time.sleep(.055)
    def _tick(self):
        self.time_label.configure(text=f'{format_ts(self.preview_t).replace(",", ".")} / {format_ts(self.duration).replace(",", ".")}')
        self.after(100, self._tick)

    # ---------- preview + waveform ----------
    def _show_frame(self, seconds):
        if self.cap is None or Image is None or cv2 is None: return
        try:
            self.cap.set(cv2.CAP_PROP_POS_MSEC, seconds*1000); ok, frame=self.cap.read()
            if not ok: return
            frame=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB); img=Image.fromarray(frame)
            w=max(320,self.preview.winfo_width()-4); h=max(180,self.preview.winfo_height()-4); img.thumbnail((w,h),Image.Resampling.LANCZOS)
            idx=self._cue_at(seconds)
            if idx is not None and self.cues[idx].text:
                text=self.cues[idx].text; font=preview_font(self.style)
                if font:
                    # Pillow does not interpret outline alpha; use readable opaque preview.
                    bbox=ImageDraw.Draw(img).multiline_textbbox((0,0),text,font=font,stroke_width=max(1,self.style.outline//2),spacing=4,align='center')
                    tw,th=bbox[2]-bbox[0],bbox[3]-bbox[1]
                    if self.style.position=='top': y=self.style.margin_v
                    elif self.style.position=='middle': y=max(8,(img.height-th)//2)
                    else: y=max(8,img.height-th-self.style.margin_v)
                    x=max(8,(img.width-tw)//2)
                    fill=self.style.color; outline=self.style.outline_color
                    ImageDraw.Draw(img).multiline_text((x,y),text,font=font,fill=fill,stroke_width=max(1,self.style.outline//2),stroke_fill=outline,spacing=4,align='center')
            self._photo=ImageTk.PhotoImage(img); self.preview.configure(image=self._photo,text='')
        except Exception:
            pass

    def _cue_at(self,t):
        for i,c in enumerate(self.cues):
            if c.start <= t <= c.end: return i
        return None

    def _select_timeline_cue(self):
        idx=self._cue_at(self.preview_t)
        if idx is not None and idx != self.current_index:
            self.current_index=idx; self.tree.selection_set(str(idx)); self.tree.focus(str(idx)); self.tree.see(str(idx)); c=self.cues[idx]; self.start_var.set(format_ts(c.start)); self.end_var.set(format_ts(c.end)); self.text.delete('1.0','end'); self.text.insert('1.0',c.text)

    def _start_waveform_job(self, media):
        self._wave_id += 1; wave_id=self._wave_id; self.waveform=[]
        self._set_status('正在分析波形…')
        def worker():
            ff=find_ffmpeg()
            if not ff or wave_id != self._wave_id: return
            try:
                cmd=[ff,'-nostdin','-hide_banner','-loglevel','error','-i',str(media),'-vn','-ac','1','-ar','8000','-f','s16le','-']
                proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                raw,_=proc.communicate()
                if proc.returncode != 0 or not raw: raise RuntimeError('FFmpeg waveform extraction failed')
                import array
                samples=array.array('h'); samples.frombytes(raw)
                target=1800; step=max(1,len(samples)//target); vals=[]
                for i in range(0,len(samples),step):
                    chunk=samples[i:i+step]
                    if not chunk: break
                    rms=math.sqrt(sum((x/32768.0)**2 for x in chunk)/len(chunk)); vals.append(min(1.0,rms*4.0))
                self.after(0,lambda v=vals,w=wave_id: self._set_waveform(v,w))
            except Exception as exc:
                self.after(0,lambda e=exc: self._set_status(f'波形分析失敗：{e}'))
        self._wave_thread=threading.Thread(target=worker,daemon=True); self._wave_thread.start()

    def _set_waveform(self, vals, wave_id):
        if wave_id != self._wave_id: return
        self.waveform=vals; self._set_status('波形分析完成'); self.draw_timeline()

    def draw_timeline(self):
        self.canvas.delete('all')
        if self.duration <= 0: return
        w=max(10,self.canvas.winfo_width()); h=max(20,self.canvas.winfo_height())
        # waveform
        if self.waveform:
            mid=35; amp=28; step=max(1,len(self.waveform)//max(1,w))
            pts=[]
            for x in range(w):
                i=min(len(self.waveform)-1,x*len(self.waveform)//w); y=self.waveform[i]*amp
                pts.extend((x,mid-y,x,mid+y))
            for x in range(w):
                i=min(len(self.waveform)-1,x*len(self.waveform)//w); y=self.waveform[i]*amp
                self.canvas.create_line(x,mid-y,x,mid+y,fill='#46506a')
        # time ticks
        tick= max(1.0, self.duration/8)
        t=0.0
        while t <= self.duration + 0.01:
            x=t/self.duration*w; self.canvas.create_line(x,0,x,h,fill='#262c38'); self.canvas.create_text(x+3,8,text=format_ts(t)[:8],anchor='nw',fill='#7b8498',font=('Segoe UI',8)); t += tick
        # cue blocks
        for i,c in enumerate(self.cues):
            x1=c.start/self.duration*w; x2=max(x1+4,c.end/self.duration*w); y1=58; y2=h-12
            fill='#5b7cfa' if i==self.current_index else '#334057'
            self.canvas.create_rectangle(x1,y1,x2,y2,fill=fill,outline='#90a4ff' if i==self.current_index else '#4a566f')
            label=(c.text.replace('\n',' ')[:22]+'…') if len(c.text)>22 else c.text.replace('\n',' ')
            self.canvas.create_text((x1+x2)/2,(y1+y2)/2,text=label,fill='white',font=('Microsoft JhengHei UI',9))
        px=self.preview_t/self.duration*w; self.canvas.create_line(px,0,px,h,fill='#f2c94c',width=2)

    def _timeline_time(self,x): return max(0,min(self.duration,x/max(1,self.canvas.winfo_width())*self.duration))

    def _hit_cue(self,x,y):
        if self.duration<=0: return None
        w=max(10,self.canvas.winfo_width())
        for i,c in enumerate(self.cues):
            x1=c.start/self.duration*w; x2=max(x1+4,c.end/self.duration*w)
            if 54 <= y <= self.canvas.winfo_height()-10 and x1 <= x <= x2: return i,x1,x2
        return None

    def _timeline_mouse_down(self,event):
        hit=self._hit_cue(event.x,event.y)
        if hit:
            i,x1,x2=hit; self.select_index(i); edge=0 if abs(event.x-x1)<7 else 2 if abs(event.x-x2)<7 else 1
            self._timeline_drag={'index':i,'mode':edge,'start_x':event.x,'orig_start':self.cues[i].start,'orig_end':self.cues[i].end,'before':self.snapshot()}
        else:
            self.seek(self._timeline_time(event.x))

    def _timeline_mouse_drag(self,event):
        d=self._timeline_drag
        if not d or self.duration<=0: return
        i=d['index']; c=self.cues[i]; delta=(event.x-d['start_x'])/max(1,self.canvas.winfo_width())*self.duration
        min_gap=0.05
        if d['mode']==1:
            length=d['orig_end']-d['orig_start']; start=max(0,min(self.duration-length,d['orig_start']+delta)); c.start=start; c.end=start+length
        elif d['mode']==0:
            c.start=max(0,min(d['orig_end']-min_gap,d['orig_start']+delta))
        else:
            c.end=max(c.start+min_gap,min(self.duration,d['orig_end']+delta))
        self.start_var.set(format_ts(c.start)); self.end_var.set(format_ts(c.end)); self.draw_timeline(); self.seek(c.start)

    def _timeline_mouse_up(self,event):
        d=self._timeline_drag
        if not d or self.duration<=0:
            self._timeline_drag=None
            return
        i=d['index']
        if abs(event.x-d['start_x'])>2:
            # Record the pre-drag state as the undo point.
            self.undo_stack.append(d['before'])
            self.redo_stack.clear()
            if len(self.undo_stack)>100: self.undo_stack.pop(0)
            self.refresh_tree(); self.select_index(i)
        else:
            self.seek(self._timeline_time(event.x))
        self._timeline_drag=None

    # ---------- burn-in ----------
    def _make_ass(self, path: Path) -> Path:
        play_res_x, play_res_y = 1920, 1080
        align = {'bottom':2,'middle':5,'top':8}.get(self.style.position,2)
        primary = hex_to_ass(self.style.color, max(0, 255-int(2.55*self.style.opacity)))
        outline = hex_to_ass(self.style.outline_color, 0)
        bold = -1 if self.style.bold else 0; italic=-1 if self.style.italic else 0
        header='''[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'''
        styleline=f"Style: Default,{self.style.font},{self.style.size},{primary},&H00FFFFFF,{outline},&H80000000,{bold},{italic},0,0,100,100,0,0,1,{self.style.outline},{self.style.shadow},{align},40,40,{self.style.margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        def ass_time(s):
            h=int(s//3600); m=int((s%3600)//60); sec=s%60
            return f'{h}:{m:02d}:{sec:05.2f}'
        lines=[header,styleline]
        for c in self.cues:
            lines.append(f"Dialogue: 0,{ass_time(c.start)},{ass_time(max(c.start+.05,c.end))},Default,,0,0,0,,{ass_escape(c.text.replace(chr(10), r'\\N'))}\n")
        path.write_text(''.join(lines),encoding='utf-8-sig')
        return path

    def burn_subtitles(self):
        if not self.video_path or not self.video_path.exists():
            messagebox.showwarning('缺少影片','請先載入影片。'); return
        if not self.cues:
            messagebox.showwarning('沒有字幕','請先載入或產生字幕。'); return
        default = self.video_path.with_name(self.video_path.stem + '_subtitled.mp4')
        out = filedialog.asksaveasfilename(defaultextension='.mp4', initialfile=default.name, filetypes=[('MP4','*.mp4')])
        if not out: return
        self._set_status('正在燒字輸出影片…')
        self._burn_btn_state(False)
        def worker():
            ff=find_ffmpeg()
            if not ff:
                self.after(0,lambda: messagebox.showerror('FFmpeg 不存在','找不到內建 FFmpeg。'))
                self.after(0,lambda: self._burn_btn_state(True)); return
            work=Path(out).with_suffix('.ass')
            try:
                self._make_ass(work)
                ass_path = work.resolve().as_posix().replace(':', '\\:').replace("'", "\\'")
                vf=f"ass='{ass_path}'"
                cmd=[ff,'-y','-hide_banner','-loglevel','error','-i',str(self.video_path),'-vf',vf,'-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k',str(out)]
                subprocess.run(cmd,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                try: work.unlink()
                except Exception: pass
                self.after(0,lambda: self._set_status(f'燒字完成：{Path(out).name}'))
                self.after(0,lambda: messagebox.showinfo('完成',f'已輸出：\n{out}'))
            except subprocess.CalledProcessError as exc:
                self.after(0,lambda e=exc: messagebox.showerror('燒字失敗',f'FFmpeg 失敗（exit code {e.returncode}）。\n請確認輸入影片格式與 FFmpeg。'))
                self.after(0,lambda: self._set_status('燒字失敗'))
            except Exception as exc:
                self.after(0,lambda e=exc: messagebox.showerror('燒字失敗',str(e)))
                self.after(0,lambda: self._set_status('燒字失敗'))
            finally:
                self.after(0,lambda: self._burn_btn_state(True))
        threading.Thread(target=worker,daemon=True).start()

    def _burn_btn_state(self, enabled):
        # Best effort; button is created as a direct child of bottom.
        for child in self.winfo_children():
            if isinstance(child, ttk.Frame):
                for c in child.winfo_children():
                    try:
                        if c.cget('text').startswith('🔥'):
                            c.configure(state='normal' if enabled else 'disabled')
                    except Exception: pass

    def open_result(self, media_path, srt_path): self.load_media(media_path); self.load_srt(srt_path)

    def destroy(self):
        self.playing=False; self._stop_play.set(); self._wave_id += 1; self._release_video(); super().destroy()
