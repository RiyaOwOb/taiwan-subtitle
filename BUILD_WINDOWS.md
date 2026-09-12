# Windows 發行流程

## 1. 準備環境

在 Windows 10/11 x64 安裝 Python 3.12 或 3.13 x64 與 Inno Setup 6。

## 2. 建置

```bat
build_windows.bat
```

完成後：

```text
portable:
  dist\\TaiwanSubtitle\\TaiwanSubtitle.exe

installer:
  release\\TaiwanSubtitle-windows-x64-setup.exe
```

## 3. 乾淨機測試

在一台沒有 Python / FFmpeg / PyTorch 的 Windows x64 測試機：

1. 執行 installer。
2. 啟動 Taiwan Subtitle。
3. 確認 runtime 顯示 FFmpeg OK。
4. 放入 30–60 秒 MP4。
5. 第一次啟動等待模型下載完成。
6. 產生 SRT，確認繁體中文與時間戳。
7. 再執行一次相同檔案，確認模型不會重複下載。
8. 切換 CPU 模式再測試一次。

## 4. 發行建議

把 installer 與 SHA-256 一起放到 GitHub Releases。不要把 Hugging Face 模型權重硬塞進 installer。
