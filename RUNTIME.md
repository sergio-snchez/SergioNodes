# DLSS 5 Runtime

The nodes in this pack drive NVIDIA DLSS 5 Neural Rendering through a native
D3D12 worker. The worker itself — NVIDIA, ReShade and RenoDX binaries plus
`ffmpeg.exe` — is **not part of this repository** and is not redistributed by
it. It lives in `runtime/`, `ffmpeg/` and the machine-specific `config.json`,
all three of which are gitignored.

If those folders are missing (fresh clone), restore them by running the setup
script exactly once. Use the Python of the ComfyUI install you run:

```bat
python_embeded\python.exe ComfyUI\custom_nodes\SergioNodes\install_runtime.py
```

From the ComfyUI portable root (the folder containing `python_embeded` and
`ComfyUI`), or with a custom venv:

```bat
path\to\venv\python.exe install_runtime.py
```

What it does:

1. Prints a licensing notice and asks for confirmation (`--yes` skips it).
2. Downloads the third-party DLSS 5 Visual Enhancer release v3.0 from its
   GitHub releases page (about 467 MB, ~700 MB on disk after extraction).
3. Extracts only `bin/runtime` and `bin/ffmpeg/bin` into `runtime/` and
   `ffmpeg/bin` inside the node pack.
4. Writes `config.json` pointing at those two folders.

To register an existing installation instead of downloading again:

```bat
python install_runtime.py --runtime-dir "D:\DLSS 5 Visual Enhancer\bin\runtime"
```

Other flags: `--url` overrides the download source, `--keep-archive` keeps the
downloaded zip. Release v3.0 is what this pack is built against (worker
protocol version 4); an older release fails at session setup.

**Antivirus.** The worker must keep the file name `nvngx.dll` and runs a `.dll`
as a process, a pattern Windows Defender flags. If the node reports the worker
could not be started, add the `runtime` folder to your exclusion list.

Everything else — node code, `dlss5/`, `nodes/` — is self-contained and commits
normally. See `README-dlss5.md` for full install, troubleshooting and node
documentation.