# Taiwan Subtitle — Windows x64

把原本 Apple Silicon / MLX 取向的 `taiwan-subtitle` 改成真正以 **Windows x64** 為發行目標的桌面字幕工具。

設計上參考 AutoSubs：它目前提供 Windows x86_64 安裝檔、local-first 處理、桌面 GUI，以及 bundled FFmpeg sidecar；同樣採本機模型，不把影片上傳雲端。 citehttps://github.com/tmoroney/auto-subs

## 這個版本的架構

- GUI：Tkinter + tkinterdnd2，支援拖放影片／音訊與多檔批次。
- ASR：TEA-ASR-1.1 / TEA-ASR-1.1-mini。
- Timestamp：Qwen3-ForcedAligner-0.6B。Qwen3-ASR 官方目前提供 Transformers backend，並能直接掛上 Forced Aligner 回傳時間戳。 citehttps://github.com/QwenLM/Qwen3-ASR
- GPU：自動偵測 NVIDIA CUDA；也可手動 CPU / CUDA。
- FFmpeg：打包成 sidecar，先把影片／音訊轉為 16 kHz mono PCM WAV，再交給 ASR；這能避免不同 Windows codec／container 造成讀檔差異。
- Cache：模型放在 `%LOCALAPPDATA%\\TaiwanSubtitle\\models\\huggingface`，不寫入 Program Files。
- Log：放在 `%LOCALAPPDATA%\\TaiwanSubtitle\\logs`。
- 匯出：SRT、TXT、JSON。



## v0.5：影片編輯器風格工作區

- 波形時間軸：載入影片後背景分析音訊波形。
- 可拖曳字幕區塊：拖中間可平移，拖左右邊緣可調整開始／結束時間。
- 即時樣式預覽：字型、大小、粗體／斜體、位置、文字色、外框、陰影。
- 燒字輸出：使用 bundled FFmpeg 直接輸出 H.264 MP4。
- 樣式會同時套用到畫面預覽與最終燒字影片。

## v0.4：字幕編輯器＋影片預覽

這一版加入內建編輯工作區，轉錄完成後會自動切到「字幕編輯器」並載入影片與 SRT。編輯器提供影片預覽、播放/暫停、±5 秒、timeline 定位、字幕 cue 清單、開始/結束時間與文字編輯，以及新增、刪除、合併、切分、復原/重做與 SRT 另存。

影片預覽目前採本機 OpenCV/Pillow 解碼，預覽播放為**靜音**；音訊仍會完整交給 FFmpeg/ASR 處理。這樣 portable EXE 不必要求使用者另外安裝 VLC 或其他播放器。

這個編輯器的工作流參考 AutoSubs 的「轉錄 → 編輯字幕 → 匯出」模型；AutoSubs 官方目前也將 standalone 模式描述為轉錄後編輯 speakers/subtitles，再輸出 SRT/text 或整合到 Resolve/Adobe。 citehttps://github.com/tmoroney/auto-subs

## 最終使用方式

使用者拿到安裝檔後：

1. 雙擊 `TaiwanSubtitle-windows-x64-setup.exe`。
2. 安裝完成後桌面會出現 `Taiwan Subtitle`。
3. 雙擊啟動。
4. 把影片拖進去。
5. 按「開始產生字幕」。
6. 第一次使用時自動從 Hugging Face 下載模型；之後使用本機 cache。

這裡的「一鍵」指的是使用者不需要安裝 Python、pip、PyTorch、FFmpeg 或在命令列操作。PyTorch、qwen-asr、FFmpeg 都在建置好的 Windows 發行包中；只有模型權重第一次使用時需要網路下載。

## 建立真正的 Windows EXE

這個 repository 必須在 **Windows x64** 上執行 `build_windows.bat`，因為 PyInstaller 需要針對 Windows 建立 Windows bootloader / DLL 組合；目前這個 Linux 工作環境不能直接驗證 Windows 執行檔本身。

建議先安裝：

- Python 3.12 或 3.13 x64
- Inno Setup 6

然後：

```bat
build_windows.bat
```

腳本會：

- 建立 `.venv`
- 安裝目前的 Windows PyTorch wheel
- 安裝 qwen-asr / OpenCC / drag-and-drop / Pillow / OpenCV GUI 依賴
- 下載 FFmpeg Windows essentials sidecar
- 用 PyInstaller 建立 `dist\\TaiwanSubtitle\\TaiwanSubtitle.exe`
- 若偵測到 Inno Setup，另外建立 `release\\TaiwanSubtitle-windows-x64-setup.exe`

FFmpeg 的 Windows builds 頁目前提供 release essentials ZIP，而且列出 Windows 10+ 相容性；本專案使用其固定下載別名 `ffmpeg-release-essentials.zip`。 citehttps://www.gyan.dev/ffmpeg/builds/

## 開發模式

```bat
install_dev_windows.bat
run_windows.bat
```

CLI：

```bat
cli_windows.bat "D:\\video\\test.mp4"
cli_windows.bat "D:\\video\\test.mp4" --small-model
cli_windows.bat "D:\\video\\test.mp4" --device cuda
cli_windows.bat "D:\\video\\test.mp4" --device cpu --no-aligner
```

## 為什麼不是把所有模型一起塞進 EXE？

TEA-ASR 與 Forced Aligner 本身就是大型模型。把它們硬塞進安裝檔會讓 installer 巨大，而且更新模型時必須重新下載整個程式。這版採「程式固定、模型可獨立 cache」的方式，安裝器保持可更新，模型也只下載一次。

## Windows 發行注意事項

PyInstaller 對 Python/ML 套件的打包會比一般桌面程式更複雜，因此 `TaiwanSubtitle.spec` 已經顯式收集 `qwen_asr`、`transformers`、`accelerate`、`tkinterdnd2` 等 package data / hidden imports。打包仍應在乾淨的 Windows x64 環境做一次 smoke test。

## 已知限制

目前這個發行版的第一階段目標是「自動產生高品質台灣繁中 SRT」，不是完整複製 AutoSubs 的 DaVinci Resolve / Premiere 整合。AutoSubs 本身現行桌面端使用 Tauri 2 + React/TypeScript/Rust，並包含 Resolve / Adobe 整合；這個專案則專注在 Taiwan Subtitle 的 ASR 與字幕輸出。 citehttps://github.com/tmoroney/auto-subs/tree/main/AutoSubs-App
