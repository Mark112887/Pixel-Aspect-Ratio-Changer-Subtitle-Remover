# Pixel Aspect Ratio Changer + Subtitle Remover

A Lightweight Windows Desktop Tool For Batch-Modifying The **Pixel Aspect Ratio (PAR)** Of MP4 Video Files And Optionally **Removing Embedded Subtitle Tracks** — All Without Re-Encoding.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2B-yellow)

## What It Does

When Videos Are Recorded With Non-Square Pixels (Common In Dashcams, Security Cameras, And Older Consumer Electronics), They May Appear Stretched Or Squashed In Modern Players That Assume Square Pixels. This Tool Writes The Correct PAR Metadata Into The MP4 Container So The Video Displays At Its Intended **Display Aspect Ratio (DAR)**.

### Key Features

- **No Re-Encoding** — Uses [GPAC MP4Box](https://gpac.wp.imt.fr/) To Modify Container Metadata Only, So Processing Is Near-Instant With Zero Quality Loss
- **Automatic Dimension Detection** — Video Width And Height Are Grabbed Automatically From Each File; You Never Need To Enter Them Manually
- **Batch Processing** — Add As Many MP4 Files As You Need And Process Them All At Once
- **Drag & Drop** — Drop MP4 Files Directly Onto The Window To Add Them To The Queue
- **Subtitle Removal** — Optionally Strip Embedded Subtitle Tracks (TTML, TX3G) In The Same Pass
- **Input Validation** — The DAR Field Only Accepts Digits And Colons, Preventing Invalid Entries
- **Persistent Settings** — Remembers Your Last-Used Output Directory Between Sessions
- **Dark Theme UI** — Easy On The Eyes For Extended Use

## Quick Start (Executable)

1. Download `Pixel Aspect Ratio Changer + Subtitle Remover.exe` From The Latest Release.
2. Double-Click To Launch.
3. **Drag & Drop** Or **Browse** For MP4 Files.
4. Enter Your Desired Display Aspect Ratio (Default: `16:9`).
5. *(Optional)* Check **Remove Subtitles** If You Want Subtitle Tracks Stripped.
6. Click **📂 Output Dir** To Choose Where Processed Files Go.
7. Hit **▶  Process** And Wait For Completion.

### Supported DAR Formats

| Format | Example |
|--------|---------|
| Colon-Separated | `16:9`, `4:3`, `21:9` |
| Slash-Separated | `2.35/1`, `1.85/1` |

## Building From Source

### Prerequisites

- **Python 3.11+** (Windows)
- **PyInstaller**: `pip install pyinstaller`
- **pywin32**: `pip install pywin32`
- **GPAC MP4Box**: Place `mp4box.exe` And Its DLLs Alongside The Python Script

### Build Steps

```powershell
# Clone Or Download This Repository
cd PAR_Tools

# Build The Standalone Executable
pyinstaller Pixel_Aspect_Ratio_Changer_Subtitle_Remover.spec

# The Exe Lands In Dist/
.\dist\Pixel Aspect Ratio Changer + Subtitle Remover.exe
```

The `.spec` File Already Lists All Required MP4Box DLLs As Bundled Binaries, So The Resulting Executable Is Fully Self-Contained.

### Run Directly

You Can Also Run The Script Without Building:

```powershell
python Pixel_Aspect_Ratio_Changer_Subtitle_Remover.py
```

Make Sure `mp4box.exe` And Its Dependencies Are In The Same Directory As The Script.

## How It Works

For Each File, The Tool Performs Two Steps:

1. **Probes The MP4** Using `mp4box -info` To Read The Video Resolution (Width × Height) And Identify Track IDs For Any Subtitle Streams.
2. **Calculates PAR** From The Formula:

   ```
   PAR = DAR / SAR
   ```

   Where **DAR** Is Your Desired Display Aspect Ratio And **SAR** (Sample Aspect Ratio) Is `width / height`. The Result Is Expressed As A Reduced Fraction (E.g., `256:81`) Capped At A Denominator Of 1000.

3. **Writes Metadata** Via `mp4box -par` To Set The Pixel Aspect Ratio On The Video Track, And Optionally Removes Subtitle Tracks With `-rem`. The Output Is A New File Written To Your Chosen Output Directory — Original Files Are Never Modified.

## Project Structure

```
Pixel_Aspect_Ratio_Changer_Subtitle_Remover/
├── Pixel_Aspect_Ratio_Changer_Subtitle_Remover.py   # Main Application Source
├── Pixel_Aspect_Ratio_Changer_Subtitle_Remover.spec # PyInstaller Build Spec
├── mp4box.exe                                       # GPAC MP4Box Binary
├── *.dll                                            # MP4Box Dependencies
├── README.md                                        # This File
└── .gitignore
```

## Requirements At Runtime

No Python Installation Needed If You Use The Bundled `.exe`. The Executable Carries Its Own Python Interpreter And All Dependencies. The Only External Dependency Is The Bundled MP4Box Binaries, Which Are Included In The PyInstaller Build.

## License

MIT — See [LICENSE](LICENSE) For Details.

## Author

Built By [Mark112887](https://github.com/Mark112887).
