from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
BACKEND_ENV_FILE = BACKEND_DIR / ".env"
BACKEND_ENV_EXAMPLE = BACKEND_DIR / ".env.example"
BACKEND_REQUIREMENTS = BACKEND_DIR / "requirements.txt"
BACKEND_VENV_DIR = BACKEND_DIR / ".venv"
BACKEND_REQUIREMENTS_MARKER = BACKEND_VENV_DIR / ".agentrewind_requirements.sha256"
FRONTEND_PACKAGE_LOCK = FRONTEND_DIR / "package-lock.json"
FRONTEND_PACKAGE_JSON = FRONTEND_DIR / "package.json"
FRONTEND_NODE_MODULES = FRONTEND_DIR / "node_modules"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
FRONTEND_BUILD_ENTRY = FRONTEND_DIST_DIR / "index.html"
FRONTEND_INSTALL_MARKER = FRONTEND_NODE_MODULES / ".agentrewind_package_lock.sha256"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
RESET = "\033[0m"
BANNER_WHITE = "\033[97m"
ACCENT_BLUE = "\033[38;5;45m"
BANNER_FILL = "#"

BANNER_FONT = {
    "A": (" ### ", "#   #", "#####", "#   #", "#   #"),
    "D": ("#### ", "#   #", "#   #", "#   #", "#### "),
    "E": ("#####", "#    ", "#### ", "#    ", "#####"),
    "G": (" ####", "#    ", "# ###", "#   #", " ####"),
    "I": ("#####", "  #  ", "  #  ", "  #  ", "#####"),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #"),
    "R": ("#### ", "#   #", "#### ", "#  # ", "#   #"),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  "),
    "W": ("#   #", "#   #", "# # #", "## ##", "#   #"),
    " ": ("     ", "     ", "     ", "     ", "     "),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start AgentRewind from one terminal.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind the web server.")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="Preferred port for the web server."
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip frontend build checks and reuse the current dist folder.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the AgentRewind web UI in the default browser after startup.",
    )
    return parser.parse_args()


def enable_ansi_colors() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        return


def render_banner_rows(text: str) -> list[str]:
    rows = ["", "", "", "", ""]
    for character in text.upper():
        glyph = BANNER_FONT.get(character, BANNER_FONT[" "])
        for index, segment in enumerate(glyph):
            rows[index] += segment + " "
    return [row.rstrip() for row in rows]


def paint_banner_row(row: str) -> str:
    return "".join(BANNER_FILL if character == "#" else " " for character in row)


def print_banner() -> None:
    enable_ansi_colors()
    terminal_width = shutil.get_terminal_size(fallback=(100, 24)).columns
    print()
    banner_rows = render_banner_rows("AGENTREWIND")
    banner_width = max(len(paint_banner_row(row)) for row in banner_rows) + 4

    if banner_width > terminal_width:
        banner_rows = [row.replace(" ", "") for row in banner_rows]
        banner_width = max(len(paint_banner_row(row)) for row in banner_rows) + 4

    if banner_width > terminal_width:
        compact_text = " AGENTREWIND "
        left_padding = " " * max(0, (terminal_width - len(compact_text)) // 2)
        print(f"{left_padding}{BANNER_WHITE}{compact_text}{RESET}")
    else:
        left_padding = " " * max(0, (terminal_width - banner_width) // 2)
        for row in banner_rows:
            painted_row = paint_banner_row(row)
            print(
                f"{left_padding}{BANNER_WHITE}"
                f"{painted_row.ljust(banner_width)}{RESET}"
            )
    print(f"\n{ACCENT_BLUE}Preparing AgentRewind...{RESET}\n")


def env_python_path() -> Path:
    if os.name == "nt":
        return BACKEND_VENV_DIR / "Scripts" / "python.exe"
    return BACKEND_VENV_DIR / "bin" / "python"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def read_env_value(path: Path, key: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$")
    for line in read_text(path).splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group(1).strip()
    return None


def upsert_env_value(path: Path, key: str, value: str) -> None:
    contents = read_text(path)
    lines = contents.splitlines() if contents else []
    replaced = False
    next_lines: list[str] = []
    pattern = re.compile(rf"^{re.escape(key)}=")

    for line in lines:
        if pattern.match(line):
            next_lines.append(f"{key}={value}")
            replaced = True
        else:
            next_lines.append(line)

    if not replaced:
        next_lines.append(f"{key}={value}")

    write_text(path, "\n".join(next_lines).rstrip() + "\n")


def ensure_backend_env_file() -> None:
    if BACKEND_ENV_FILE.exists():
        return
    if BACKEND_ENV_EXAMPLE.exists():
        shutil.copyfile(BACKEND_ENV_EXAMPLE, BACKEND_ENV_FILE)
    else:
        write_text(BACKEND_ENV_FILE, "")


def prompt_for_api_key() -> str | None:
    ensure_backend_env_file()
    saved_key = read_env_value(BACKEND_ENV_FILE, "OPENAI_API_KEY")
    prompt_label = (
        "OpenAI API key (press Enter to use the saved key): "
        if saved_key
        else "OpenAI API key (leave blank to start in demo mode): "
    )
    entered_key = getpass.getpass(prompt_label).strip()

    if entered_key:
        upsert_env_value(BACKEND_ENV_FILE, "OPENAI_API_KEY", entered_key)
        upsert_env_value(BACKEND_ENV_FILE, "AGENTREWIND_USE_MOCK_LLM", "false")
        return entered_key

    if saved_key:
        upsert_env_value(BACKEND_ENV_FILE, "AGENTREWIND_USE_MOCK_LLM", "false")
        return saved_key

    upsert_env_value(BACKEND_ENV_FILE, "AGENTREWIND_USE_MOCK_LLM", "true")
    return None


def command_succeeds(command: list[str], *, cwd: Path | None = None) -> bool:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def ensure_backend_runtime() -> Path:
    backend_python = env_python_path()
    if not command_succeeds([str(backend_python), "--version"]):
        if BACKEND_VENV_DIR.exists():
            shutil.rmtree(BACKEND_VENV_DIR)
        print("Creating backend virtual environment...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(BACKEND_VENV_DIR)],
            check=True,
            cwd=str(ROOT_DIR),
        )

    requirements_hash = file_hash(BACKEND_REQUIREMENTS)
    installed_hash = read_text(BACKEND_REQUIREMENTS_MARKER).strip()
    if requirements_hash != installed_hash or not command_succeeds(
        [str(backend_python), "-c", "import fastapi, uvicorn, openai"]
    ):
        print("Installing backend dependencies...")
        subprocess.run(
            [str(backend_python), "-m", "pip", "install", "-r", str(BACKEND_REQUIREMENTS)],
            check=True,
            cwd=str(BACKEND_DIR),
        )
        write_text(BACKEND_REQUIREMENTS_MARKER, requirements_hash)

    return backend_python


def resolve_npm_command() -> str:
    candidates = [
        shutil.which("npm.cmd"),
        shutil.which("npm"),
        str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "npm.cmd"),
        str(
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "nodejs"
            / "npm.cmd"
        ),
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    raise RuntimeError(
        "Node.js/npm was not found. Install Node.js, then run AgentRewind again."
    )


def run_npm_command(npm_command: str, *args: str) -> None:
    if os.name == "nt":
        command = ["cmd", "/c", npm_command, *args]
    else:
        command = [npm_command, *args]
    subprocess.run(command, check=True, cwd=str(FRONTEND_DIR))


def latest_source_mtime() -> float:
    watched_paths = [
        FRONTEND_DIR / "index.html",
        FRONTEND_DIR / "vite.config.ts",
        FRONTEND_DIR / "package.json",
        FRONTEND_PACKAGE_LOCK,
    ]
    watched_paths.extend(path for path in (FRONTEND_DIR / "src").rglob("*") if path.is_file())
    watched_paths.extend(
        path for path in (FRONTEND_DIR / "public").rglob("*") if path.is_file()
    )
    return max(path.stat().st_mtime for path in watched_paths if path.exists())


def build_required() -> bool:
    if not FRONTEND_BUILD_ENTRY.exists():
        return True
    return latest_source_mtime() > FRONTEND_BUILD_ENTRY.stat().st_mtime


def ensure_frontend_ready(skip_build: bool) -> None:
    if skip_build:
        return

    if not build_required():
        return

    npm_command = resolve_npm_command()
    package_hash = file_hash(FRONTEND_PACKAGE_LOCK if FRONTEND_PACKAGE_LOCK.exists() else FRONTEND_PACKAGE_JSON)
    installed_hash = read_text(FRONTEND_INSTALL_MARKER).strip()
    if not FRONTEND_NODE_MODULES.exists() or package_hash != installed_hash:
        print("Installing frontend dependencies...")
        run_npm_command(npm_command, "install")
        write_text(FRONTEND_INSTALL_MARKER, package_hash)

    print("Building frontend bundle...")
    run_npm_command(npm_command, "run", "build")


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def pick_port(host: str, preferred_port: int) -> int:
    if not is_port_open(host, preferred_port):
        return preferred_port
    for candidate in range(preferred_port + 1, preferred_port + 21):
        if not is_port_open(host, candidate):
            return candidate
    raise RuntimeError("Could not find a free port for AgentRewind.")


def wait_for_health(url: str, process: subprocess.Popen[bytes], timeout_seconds: int = 30) -> None:
    health_url = f"{url}/health"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"AgentRewind exited before startup finished (code {process.returncode})."
            )
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.4)
    raise RuntimeError("Timed out waiting for AgentRewind to start.")


def launch_server(
    *,
    backend_python: Path,
    host: str,
    port: int,
    api_key: str | None,
    open_browser: bool,
) -> int:
    url = f"http://{host}:{port}"
    env = os.environ.copy()
    env["AGENTREWIND_FRONTEND_ORIGIN"] = url
    if api_key:
        env["OPENAI_API_KEY"] = api_key

    upsert_env_value(BACKEND_ENV_FILE, "AGENTREWIND_FRONTEND_ORIGIN", url)

    print(f"Launching AgentRewind at {url}")
    print("Press Ctrl+C to stop the server.\n")

    process = subprocess.Popen(
        [
            str(backend_python),
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(BACKEND_DIR),
        env=env,
    )

    try:
        wait_for_health(url, process)
        print(f"AgentRewind web link: {url}\n")
        if open_browser:
            webbrowser.open(url)
        return process.wait()
    except KeyboardInterrupt:
        print("\nShutting down AgentRewind...")
        process.terminate()
        return process.wait()
    except Exception:
        process.terminate()
        raise


def main() -> int:
    args = parse_args()
    print_banner()
    ensure_backend_env_file()
    api_key = prompt_for_api_key()
    if api_key:
        print("OpenAI API key loaded.")
    else:
        print("No API key provided. AgentRewind will start in demo mode.")

    backend_python = ensure_backend_runtime()
    ensure_frontend_ready(skip_build=args.skip_build)
    port = pick_port(args.host, args.port)
    return launch_server(
        backend_python=backend_python,
        host=args.host,
        port=port,
        api_key=api_key,
        open_browser=args.open,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print("\nStartup failed while running a dependency command.")
        print("Command:", " ".join(str(part) for part in error.cmd))
        raise SystemExit(error.returncode)
    except Exception as error:  # noqa: BLE001
        print(f"\nStartup failed: {error}")
        raise SystemExit(1)
