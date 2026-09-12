from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from subtitle_editor import SubtitleEditor

from taiwan_subtitle import (
    APP_NAME,
    DEFAULT_ALIGNER_MODEL,
    DEFAULT_ASR_MODEL,
    DEFAULT_ASR_MODEL_SMALL,
    SUPPORTED_EXTENSIONS,
    app_data_dir,
    detect_runtime,
    format_bytes,
    transcribe,
)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # pragma: no cover - runtime fallback
    DND_FILES = None
    TkinterDnD = None


BaseTk = TkinterDnD.Tk if TkinterDnD else tk.Tk


class App(BaseTk):
    def __init__(self):
        super().__init__()
        self.title("Taiwan Subtitle 0.5")
        self.geometry("1080x720")
        self.minsize(900, 620)
        self.configure(bg="#f6f7f9")

        self.files: list[Path] = []
        self.output_dir = tk.StringVar()
        self.model = tk.StringVar(value="TEA-ASR-1.1")
        self.device = tk.StringVar(value="auto")
        self.aligner = tk.BooleanVar(value=True)
        self.max_chars = tk.IntVar(value=28)
        self.max_seconds = tk.DoubleVar(value=5.0)
        self.status = tk.StringVar(value="就緒")
        self.runtime = tk.StringVar(value="偵測中…")
        self.progress_value = tk.DoubleVar(value=0)
        self.running = False
        self.cancel_event = threading.Event()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.batch_index = 0
        self.batch_total = 0

        self.output_dir.set(str(Path.home() / "Videos" / "TaiwanSubtitle"))
        self._setup_style()
        self._build()
        self._update_runtime()
        self.after(120, self._drain_logs)

        if DND_FILES:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._drop_files)
            self.drop_label.configure(text="把影片／音訊拖到這裡")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#667085")
        style.configure("Card.TLabelframe", padding=12)
        style.configure("Primary.TButton", padding=(18, 10), font=("Segoe UI", 10, "bold"))
        style.configure("Big.Horizontal.TProgressbar", thickness=12)
        style.configure("Accent.TButton", padding=(14, 10), font=("Segoe UI", 10, "bold"))

    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="Taiwan Subtitle", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="台灣繁中 AI 字幕｜Windows Local-first", style="Sub.TLabel").pack(anchor="w", pady=(2, 8))
        ttk.Label(header, textvariable=self.runtime, style="Sub.TLabel").pack(anchor="e")

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True, pady=(6, 0))

        home = ttk.Frame(self.tabs, padding=8)
        editor_tab = ttk.Frame(self.tabs, padding=0)
        self.tabs.add(home, text="AI 轉錄")
        self.tabs.add(editor_tab, text="字幕編輯器")

        # ---- AI transcription tab ----
        drop = tk.Frame(home, bg="#ffffff", highlightthickness=1, highlightbackground="#d0d5dd")
        drop.pack(fill="x", pady=(0, 10))
        self.drop_label = tk.Label(drop, text="選擇影片或音訊檔", bg="#ffffff", fg="#344054", font=("Segoe UI", 14, "bold"), pady=16)
        self.drop_label.pack(fill="x")
        ttk.Button(drop, text="選擇檔案", command=self.pick_files).pack(pady=(0, 12))

        files_card = ttk.LabelFrame(home, text="待處理檔案", style="Card.TLabelframe")
        files_card.pack(fill="both", expand=True)
        list_wrap = ttk.Frame(files_card); list_wrap.pack(fill="both", expand=True)
        self.file_list = tk.Listbox(list_wrap, height=7, selectmode=tk.EXTENDED, borderwidth=0, highlightthickness=0, font=("Segoe UI", 10))
        self.file_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.file_list.yview); scroll.pack(side="right", fill="y")
        self.file_list.configure(yscrollcommand=scroll.set)
        controls = ttk.Frame(files_card); controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="新增", command=self.pick_files).pack(side="left")
        ttk.Button(controls, text="移除選取", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(controls, text="清空", command=self.clear_files).pack(side="left")

        settings = ttk.LabelFrame(home, text="設定", style="Card.TLabelframe"); settings.pack(fill="x", pady=10)
        settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text="模型").grid(row=0, column=0, sticky="w", padx=8, pady=5)
        ttk.Combobox(settings, textvariable=self.model, values=("TEA-ASR-1.1", "TEA-ASR-1.1-mini"), state="readonly", width=22).grid(row=0, column=1, sticky="w", padx=8, pady=5)
        ttk.Label(settings, text="運算").grid(row=0, column=2, sticky="w", padx=8, pady=5)
        ttk.Combobox(settings, textvariable=self.device, values=("auto", "cuda", "cpu"), state="readonly", width=12).grid(row=0, column=3, sticky="w", padx=8, pady=5)
        ttk.Checkbutton(settings, text="精準時間戳（Forced Aligner）", variable=self.aligner).grid(row=0, column=4, sticky="w", padx=8, pady=5)
        ttk.Label(settings, text="每行字數").grid(row=1, column=0, sticky="w", padx=8, pady=5)
        ttk.Spinbox(settings, from_=10, to=60, textvariable=self.max_chars, width=8).grid(row=1, column=1, sticky="w", padx=8, pady=5)
        ttk.Label(settings, text="最長秒數").grid(row=1, column=2, sticky="w", padx=8, pady=5)
        ttk.Spinbox(settings, from_=1.0, to=15.0, increment=0.5, textvariable=self.max_seconds, width=8).grid(row=1, column=3, sticky="w", padx=8, pady=5)

        output = ttk.Frame(home); output.pack(fill="x")
        ttk.Label(output, text="輸出資料夾").pack(side="left")
        ttk.Entry(output, textvariable=self.output_dir).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(output, text="瀏覽…", command=self.pick_output).pack(side="left")

        bottom = ttk.Frame(home); bottom.pack(fill="x", pady=(10, 0))
        self.start_btn = ttk.Button(bottom, text="開始產生字幕", style="Primary.TButton", command=self.start); self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(bottom, text="停止", command=self.cancel, state="disabled"); self.cancel_btn.pack(side="left", padx=8)
        ttk.Label(bottom, textvariable=self.status).pack(side="left", padx=10)
        self.progress = ttk.Progressbar(bottom, variable=self.progress_value, mode="determinate", style="Big.Horizontal.TProgressbar"); self.progress.pack(side="right", fill="x", expand=True, padx=(24, 0))

        log_frame = ttk.LabelFrame(home, text="處理紀錄", style="Card.TLabelframe"); log_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.log = tk.Text(log_frame, height=5, wrap="word", state="disabled", borderwidth=0, bg="#fbfcfe", font=("Consolas", 9)); self.log.pack(fill="both", expand=True)

        self.editor = SubtitleEditor(editor_tab, on_status=self._editor_status)
        self.editor.pack(fill="both", expand=True)

    def _editor_status(self, text: str):
        self.status.set(text)

    def _update_runtime(self):
        try:
            info = detect_runtime()
            self.runtime.set(info)
        except Exception as exc:
            self.runtime.set(f"環境檢查失敗：{exc}")

    def _drop_files(self, event):
        for path in self.tk.splitlist(event.data):
            self._add_file(Path(path))

    def pick_files(self):
        patterns = " ".join(f"*{x}" for x in sorted(SUPPORTED_EXTENSIONS))
        paths = filedialog.askopenfilenames(filetypes=[("Video / Audio", patterns), ("All files", "*.*")])
        for p in paths:
            self._add_file(Path(p))

    def _add_file(self, p: Path):
        p = p.expanduser()
        if not p.is_file() or p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        rp = p.resolve()
        if rp not in self.files:
            self.files.append(rp)
            self.file_list.insert("end", f"{rp.name}    ({format_bytes(rp.stat().st_size)})")

    def remove_selected(self):
        selected = list(self.file_list.curselection())
        for idx in reversed(selected):
            self.file_list.delete(idx)
            self.files.pop(idx)

    def clear_files(self):
        self.file_list.delete(0, "end")
        self.files.clear()

    def pick_output(self):
        p = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.home()))
        if p:
            self.output_dir.set(p)

    def write_log(self, text: str):
        self.log_queue.put(text)

    def _drain_logs(self):
        while True:
            try:
                text = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(120, self._drain_logs)

    def start(self):
        if not self.files:
            messagebox.showwarning("缺少檔案", "請先選擇至少一個影片或音訊檔。")
            return
        out = Path(self.output_dir.get()).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        self.running = True
        self.cancel_event.clear()
        self.batch_index = 0
        self.batch_total = len(self.files)
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.configure(mode="determinate", maximum=max(1, self.batch_total))
        self.progress_value.set(0)
        self.status.set(f"準備處理 {self.batch_total} 個檔案…")
        threading.Thread(target=self._worker, args=(out,), daemon=True).start()

    def cancel(self):
        self.cancel_event.set()
        self.status.set("正在停止目前工作…")
        self.cancel_btn.configure(state="disabled")

    def _worker(self, output_dir: Path):
        asr = DEFAULT_ASR_MODEL_SMALL if self.model.get() == "TEA-ASR-1.1-mini" else DEFAULT_ASR_MODEL
        aligner = DEFAULT_ALIGNER_MODEL if self.aligner.get() else None
        force_gpu = self.device.get() == "cuda"
        force_cpu = self.device.get() == "cpu"
        completed = 0
        failures: list[str] = []

        for index, input_path in enumerate(self.files, start=1):
            if self.cancel_event.is_set():
                break
            self.after(0, lambda i=index, n=self.batch_total, name=input_path.name: self.status.set(f"處理 {i}/{n}：{name}"))
            try:
                result = transcribe(
                    input_path,
                    output_dir,
                    asr_model=asr,
                    aligner_model=aligner,
                    force_gpu=force_gpu,
                    force_cpu=force_cpu,
                    max_chars=max(10, int(self.max_chars.get())),
                    max_seconds=max(1.0, float(self.max_seconds.get())),
                    cancel_event=self.cancel_event,
                    log=self.write_log,
                )
                completed += 1
                self.write_log(f"完成：{Path(result.srt).name}")
                self.after(0, lambda r=result: self._open_result_editor(r))
            except Exception as exc:
                failures.append(f"{input_path.name}: {type(exc).__name__}: {exc}")
                self.write_log(f"失敗：{input_path.name} — {exc}")
            finally:
                self.after(0, lambda v=index: self.progress_value.set(v))

        self.running = False
        self.after(0, lambda: self.start_btn.configure(state="normal"))
        self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
        if self.cancel_event.is_set():
            self.after(0, lambda: self.status.set(f"已停止；完成 {completed} 個"))
            return
        if failures:
            self.after(0, lambda: self.status.set(f"完成 {completed}/{self.batch_total}，有失敗項目"))
            self.after(0, lambda: messagebox.showwarning("部分完成", "部分檔案處理失敗，請查看處理紀錄。"))
        else:
            self.after(0, lambda: self.status.set(f"全部完成：{completed} 個檔案"))
            self.after(0, lambda: messagebox.showinfo("完成", f"已完成 {completed} 個檔案。\n輸出位置：\n{output_dir}"))

    def _open_result_editor(self, result):
        try:
            self.editor.open_result(result.input, result.srt)
            self.tabs.select(1)
            self.status.set(f"字幕編輯器已載入：{Path(result.srt).name}")
        except Exception as exc:
            self.write_log(f"編輯器載入失敗：{exc}")

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno("正在處理", "目前仍在處理檔案。確定要關閉嗎？"):
                return
            self.cancel_event.set()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
