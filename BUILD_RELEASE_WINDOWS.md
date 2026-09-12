# Taiwan Subtitle — Windows x64 Release

本專案的 Windows 發行版由 Windows x64 runner 建置。Linux/macOS 不能可靠地產生並驗證這個 PyInstaller + FFmpeg + PyTorch 的 Windows binary，所以不要在非 Windows 主機上自行把 `.py` 改名成 `.exe`。

## 最簡單：GitHub Actions

1. 把整個 `taiwan-subtitle-windows` 資料夾放進 GitHub repository。
2. Push 到 GitHub。
3. 打開 `Actions` → `Windows Release` → `Run workflow`。
4. 等 workflow 完成後，在該 workflow 的 `Artifacts` 下載：
   - `TaiwanSubtitle-windows-x64-portable.zip`
   - `TaiwanSubtitle-windows-x64-setup.exe`

建立 tag，例如 `v0.5.1`，workflow 也會自動建立 GitHub Release 並附上兩個檔案。

## Windows 本機建置

在 Windows 10/11 x64 執行：

```bat
build_windows.bat
```

輸出：

```text
dist\\TaiwanSubtitle\\TaiwanSubtitle.exe
release\\TaiwanSubtitle-windows-x64-portable.zip
release\\TaiwanSubtitle-windows-x64-setup.exe
```

## 預期使用方式

Portable：解壓後直接雙擊 `TaiwanSubtitle.exe`。

Installer：雙擊 `TaiwanSubtitle-windows-x64-setup.exe`，安裝後從開始功能表或桌面捷徑啟動。

FFmpeg 會隨應用程式提供。AI 模型第一次使用時會下載至使用者的 Local AppData 快取，不會塞進安裝器。


## v0.5.2 build fix

The PyInstaller spec resolves project files from the build working directory. The release workflow changes into the repository directory before invoking PyInstaller, so the spec no longer depends on `__file__` being defined by PyInstaller.
