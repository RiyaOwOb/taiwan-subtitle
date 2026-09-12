# Taiwan Subtitle v0.5 Editor Guide

## Timeline

The timeline shows an approximate audio waveform and subtitle clips. Click empty space to seek. Click a subtitle clip to select it. Drag the center of a clip to move the cue; drag the left or right edge to change its start/end time.

## Style preview

Open the **樣式** tab to change font, size, bold/italic, position, margins, text color, outline color, outline width and shadow. The current cue is rendered with the selected style in the video preview.

## Burn-in export

Click **🔥 燒字輸出 MP4**. The editor creates a temporary ASS subtitle file and asks the bundled FFmpeg to render the subtitles into an H.264/AAC MP4. The temporary ASS file is removed after a successful render.

The burn-in export is intentionally separate from SRT export: SRT remains editable while the MP4 is a rendered delivery copy.
