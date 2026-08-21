import sys

# In a --windowed PyInstaller build there is no real console, so sys.stdout and
# sys.stderr are None. Several dependencies (warnings.warn, stray prints) write
# to them unconditionally and crash with AttributeError if left as None. Must
# happen before any other imports that might emit output at import time.
if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
    from pathlib import Path

    _log_path = Path(sys.executable).resolve().parent / "app.log"
    _log_file = open(_log_path, "a", buffering=1, encoding="utf-8")
    sys.stdout = _log_file
    sys.stderr = _log_file

import os
import socket
import threading
import time
import traceback
import webbrowser

import uvicorn

from app.main import app
from app import config

HOST = "127.0.0.1"
PORT = 8000


def _port_is_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def _open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


def _show_error(title: str, message: str):
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        pass


def _ensure_api_key():
    if config.ANTHROPIC_API_KEY:
        return

    import tkinter as tk
    from tkinter import messagebox, simpledialog

    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        "YT Video Developer - Setup",
        "Welcome! Before you can generate scripts, paste your Anthropic API key.\n\n"
        "Get one at https://console.anthropic.com/settings/keys",
    )
    key = simpledialog.askstring("Anthropic API Key", "Paste your Anthropic API key:", show="*")
    root.destroy()

    if not key:
        return
    key = key.strip()

    env_path = config.DATA_DIR / ".env"
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = [ln for ln in existing.splitlines() if not ln.startswith("ANTHROPIC_API_KEY=")]
    lines.append(f"ANTHROPIC_API_KEY={key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    config.ANTHROPIC_API_KEY = key
    os.environ["ANTHROPIC_API_KEY"] = key


def _tray_icon_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(30, 33, 41, 255))
    d.polygon([(24, 18), (24, 46), (46, 32)], fill=(108, 140, 255, 255))
    return img


def run_dev():
    """Plain console mode for `python run.py` during development."""
    threading.Timer(1.5, _open_browser).start()
    uvicorn.run(app, host=HOST, port=PORT, reload=False)


def run_frozen():
    """System-tray mode for the packaged standalone app: no console window,
    single-instance safe, and shuts down cleanly from the tray Quit action."""
    print("Starting YT Video Developer...")

    if _port_is_open():
        # Another instance is already serving; just focus it instead of starting a second one.
        print("Another instance is already running; focusing it.")
        _open_browser()
        return

    _ensure_api_key()

    import pystray

    server_config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    for _ in range(60):
        if _port_is_open():
            break
        time.sleep(0.5)
    else:
        print("Server did not come up within 30 seconds.")

    print("Server is up, opening browser.")
    _open_browser()

    def on_open(icon, item):
        _open_browser()

    def on_quit(icon, item):
        print("Quit requested from tray, shutting down.")
        server.should_exit = True
        server_thread.join(timeout=10)
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open YT Video Developer", on_open, default=True),
        pystray.MenuItem("Quit", on_quit),
    )
    icon = pystray.Icon("YTVideoDeveloper", _tray_icon_image(), "YT Video Developer", menu)
    icon.run()

    # icon.run() only returns after on_quit stopped it - guarantee the process
    # actually ends rather than lingering on a stray non-daemon thread.
    sys.exit(0)


def main():
    if getattr(sys, "frozen", False):
        run_frozen()
    else:
        run_dev()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        if getattr(sys, "frozen", False):
            _show_error(
                "YT Video Developer - Error",
                "The app hit an error and couldn't start:\n\n" + traceback.format_exc()[-1200:],
            )
        raise
