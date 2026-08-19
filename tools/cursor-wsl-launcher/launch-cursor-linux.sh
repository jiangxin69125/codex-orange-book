#!/usr/bin/env bash
# Launch Linux Cursor from WSL2 / WSLg, and repair the Sign in / Join in flow.
#
# Linux Cursor does not use cursor:// to finish login. After the browser page
# says the login is done, the IDE polls api2.cursor.sh in the background.
# On WSL2 this commonly fails for two independent reasons:
#   1) xdg-open has no usable default browser (WSLg DISPLAY makes it skip wslview)
#   2) Electron http.proxySupport=override / http_proxy=127.0.0.1 silently
#      blocks that poll, so Join in / Sign in never enters the app
#
# Usage:
#   ./launch-cursor-linux.sh
#   ./launch-cursor-linux.sh --help
#   ./launch-cursor-linux.sh --diagnose-only
#   ./launch-cursor-linux.sh --fix-only
#   ./launch-cursor-linux.sh --dry-run
#   ./launch-cursor-linux.sh --no-fix
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${CURSOR_LAUNCHER_LOG:-$SCRIPT_DIR/cursor-linux-login.log}"
MARKER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Cursor"
USER_SETTINGS="$MARKER_DIR/User/settings.json"
ARGV_JSON="$MARKER_DIR/argv.json"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
MIME_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/mimeapps.list"
URL_BRIDGE="$SCRIPT_DIR/open-url-on-windows.sh"

DO_FIX=1
DO_LAUNCH=1
DRY_RUN=0
DIAGNOSE_ONLY=0
FIX_ONLY=0

BROWSER_VERDICT="unknown"
PROXY_VERDICT="unknown"
BIN_VERDICT="unknown"
DISPLAY_VERDICT="unknown"
AUTH_VERDICT="unknown"
SELECTED_BIN=""
SELECTED_PROXY=""
WINDOWS_BROWSER=""
declare -a DIAG_LINES=()

usage() {
  cat <<'EOF'
Launch Linux Cursor (WSL2 / WSLg) and repair the Join in / Sign in login path.

Usage:
  launch-cursor-linux.sh
  launch-cursor-linux.sh --diagnose-only
  launch-cursor-linux.sh --fix-only
  launch-cursor-linux.sh --dry-run
  launch-cursor-linux.sh --no-fix
  launch-cursor-linux.sh --help

Examples:
  launch-cursor-linux.sh
  launch-cursor-linux.sh --diagnose-only
  CURSOR_LINUX_BIN=/path/to/Cursor.AppImage launch-cursor-linux.sh --dry-run

What it fixes:
  - WSL default browser / xdg-open so Sign in can open authenticator.cursor.sh
  - Cursor settings so Linux background login polling is not blocked
  - AppImage/FUSE and --no-sandbox flags required under WSL

Exit codes:
  0  diagnose/fix/launch started successfully
  2  usage error
  3  no Linux Cursor binary found
  4  no DISPLAY/WSLg (GUI cannot start)
EOF
}

log() {
  local msg="$*"
  local ts
  ts="$(date -Is 2>/dev/null || date)"
  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
  printf '%s %s\n' "$ts" "$msg" | tee -a "$LOG_FILE" >/dev/null
  printf '%s\n' "$msg"
}

note() {
  DIAG_LINES+=("$1")
  log "$1"
}

die() {
  log "ERROR: $1"
  exit "${2:-1}"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

windows_host_ip() {
  if [[ -n "${WINDOWS_HOST_IP:-}" ]]; then
    printf '%s' "$WINDOWS_HOST_IP"
    return 0
  fi
  awk '/^nameserver / { print $2; exit }' /etc/resolv.conf 2>/dev/null || true
}

rewrite_loopback_proxy() {
  local value="${1:-}"
  local host
  host="$(windows_host_ip)"
  if [[ -z "$value" || -z "$host" ]]; then
    printf '%s' "$value"
    return
  fi
  printf '%s' "$value" | sed -E "s#://(127\\.0\\.0\\.1|localhost)#://$host#g"
}

is_linux_cursor_bin() {
  local path="$1"
  [[ -n "$path" && -e "$path" ]] || return 1
  local base
  base="$(basename "$path")"
  case "$base" in
    Cursor.exe|cursor.exe) return 1 ;;
  esac
  if [[ "$path" == /mnt/c/* && "$base" == *.exe ]]; then
    return 1
  fi
  return 0
}

newest_match() {
  local pattern="$1"
  local found=""
  # shellcheck disable=SC2086
  found="$(ls -1t $pattern 2>/dev/null | head -n 1 || true)"
  if [[ -n "$found" && -e "$found" ]]; then
    printf '%s' "$found"
  fi
}

find_cursor_bin() {
  local candidate
  if [[ -n "${CURSOR_LINUX_BIN:-}" ]]; then
    if is_linux_cursor_bin "$CURSOR_LINUX_BIN"; then
      printf '%s' "$CURSOR_LINUX_BIN"
      return 0
    fi
    return 1
  fi

  local search_roots=(
    "$SCRIPT_DIR"
    /mnt/e/CursorDownload
    /mnt/d/CursorDownload
    "$HOME/Applications"
    "$HOME/.local/bin"
    /opt/cursor
    /usr/share/cursor
    /usr/bin
  )

  local extra
  extra="$(newest_match "$SCRIPT_DIR/Cursor*.AppImage")"
  [[ -n "$extra" ]] && search_roots+=("$extra")
  extra="$(newest_match "/mnt/e/CursorDownload/Cursor*.AppImage")"
  [[ -n "$extra" ]] && search_roots+=("$extra")
  extra="$(newest_match "/mnt/e/CursorDownload/*/Cursor*.AppImage")"
  [[ -n "$extra" ]] && search_roots+=("$extra")

  local named=(
    cursor
    Cursor
    usr/bin/cursor
    squashfs-root/usr/bin/cursor
    cursor.AppImage
  )

  for root in "${search_roots[@]}"; do
    [[ -n "$root" ]] || continue
    if [[ -f "$root" ]] && is_linux_cursor_bin "$root"; then
      printf '%s' "$root"
      return 0
    fi
    for name in "${named[@]}"; do
      candidate="$root/$name"
      if [[ -f "$candidate" ]] && is_linux_cursor_bin "$candidate"; then
        printf '%s' "$candidate"
        return 0
      fi
    done
  done

  if need_cmd cursor; then
    candidate="$(command -v cursor)"
    if is_linux_cursor_bin "$candidate"; then
      printf '%s' "$candidate"
      return 0
    fi
  fi
  return 1
}

find_windows_browser() {
  local candidates=(
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe"
    "/mnt/c/Program Files/Mozilla Firefox/firefox.exe"
  )
  local p
  for p in "${candidates[@]}"; do
    if [[ -f "$p" ]]; then
      printf '%s' "$p"
      return 0
    fi
  done
  if [[ -f /mnt/c/Windows/System32/cmd.exe ]]; then
    printf '%s' "/mnt/c/Windows/System32/cmd.exe"
    return 0
  fi
  return 1
}

write_windows_url_bridge() {
  cat >"$URL_BRIDGE" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
url="${1:-}"
if [[ -z "$url" ]]; then
  echo "Usage: open-url-on-windows.sh <url>" >&2
  exit 2
fi
cmd="/mnt/c/Windows/System32/cmd.exe"
if [[ ! -x "$cmd" && -f "$cmd" ]]; then
  cmd="/mnt/c/Windows/Sysnative/cmd.exe"
fi
if [[ ! -f "$cmd" ]]; then
  echo "Windows cmd.exe not found; cannot open $url" >&2
  exit 1
fi
# Empty window title is required: `start url` otherwise treats the URL as a title.
exec "$cmd" /c start "" "$url"
EOF
  chmod +x "$URL_BRIDGE"
}

write_desktop_handler() {
  local desktop="$APPS_DIR/cursor-wsl-windows-browser.desktop"
  mkdir -p "$APPS_DIR"
  cat >"$desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Windows Browser (WSL login bridge)
NoDisplay=true
StartupNotify=false
MimeType=x-scheme-handler/http;x-scheme-handler/https;
Exec=$URL_BRIDGE %u
EOF
  if need_cmd update-desktop-database; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
  fi
  printf '%s' "$desktop"
}

upsert_mime_default() {
  local mime_file="$1"
  mkdir -p "$(dirname "$mime_file")"
  [[ -f "$mime_file" ]] || printf '[Default Applications]\n' >"$mime_file"
  python3 - "$mime_file" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8") if path.exists() else "[Default Applications]\n"
lines = text.splitlines()
wanted = {
    "x-scheme-handler/http": "cursor-wsl-windows-browser.desktop",
    "x-scheme-handler/https": "cursor-wsl-windows-browser.desktop",
}
out = []
section = None
seen = {"http": False, "https": False}
for line in lines:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        section = stripped
        out.append(line)
        continue
    if section == "[Default Applications]":
        low = stripped.lower()
        if low.startswith("x-scheme-handler/http="):
            out.append("x-scheme-handler/http=cursor-wsl-windows-browser.desktop")
            seen["http"] = True
            continue
        if low.startswith("x-scheme-handler/https="):
            out.append("x-scheme-handler/https=cursor-wsl-windows-browser.desktop")
            seen["https"] = True
            continue
    out.append(line)
if "[Default Applications]" not in "\n".join(out):
    out.append("[Default Applications]")
if not seen["http"]:
    out.append("x-scheme-handler/http=cursor-wsl-windows-browser.desktop")
if not seen["https"]:
    out.append("x-scheme-handler/https=cursor-wsl-windows-browser.desktop")
path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY
}

patch_jsonc_file() {
  local path="$1"
  local mode="$2"
  local proxy_value="${3:-}"
  mkdir -p "$(dirname "$path")"
  python3 - "$path" "$mode" "$proxy_value" <<'PY'
import json, os, pathlib, shutil, stat, sys, tempfile

path = pathlib.Path(sys.argv[1])
mode = sys.argv[2]
proxy = sys.argv[3]


def strip_jsonc(text):
    """Remove JSONC comments and trailing commas without touching strings."""
    without_comments = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        if in_string:
            without_comments.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            without_comments.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < len(text):
            next_char = text[index + 1]
            if next_char == "/":
                index += 2
                while index < len(text) and text[index] not in "\r\n":
                    index += 1
                continue
            if next_char == "*":
                index += 2
                while index + 1 < len(text) and text[index:index + 2] != "*/":
                    if text[index] in "\r\n":
                        without_comments.append(text[index])
                    index += 1
                if index + 1 >= len(text):
                    raise ValueError("unterminated block comment")
                index += 2
                continue
        without_comments.append(char)
        index += 1

    cleaned = "".join(without_comments)
    without_trailing_commas = []
    index = 0
    in_string = False
    escaped = False
    while index < len(cleaned):
        char = cleaned[index]
        if in_string:
            without_trailing_commas.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
        elif char == ",":
            lookahead = index + 1
            while lookahead < len(cleaned) and cleaned[lookahead].isspace():
                lookahead += 1
            if lookahead < len(cleaned) and cleaned[lookahead] in "}]":
                index += 1
                continue
        without_trailing_commas.append(char)
        index += 1
    return "".join(without_trailing_commas)


raw = path.read_text(encoding="utf-8") if path.exists() else "{}"
try:
    data = json.loads(strip_jsonc(raw)) if raw.strip() else {}
except (json.JSONDecodeError, ValueError) as error:
    print(f"ERROR: refusing to overwrite invalid JSONC file {path}: {error}", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(data, dict):
    print(f"ERROR: refusing to overwrite non-object JSONC file {path}", file=sys.stderr)
    raise SystemExit(1)

if mode == "settings":
    data.update({
        "http.proxySupport": "on",
        "cursor.general.disableHttp2": True,
    })
    if proxy:
        data["http.proxy"] = proxy
elif mode == "argv":
    data.setdefault("disable-hardware-acceleration", True)
else:
    print(f"ERROR: unsupported JSONC patch mode: {mode}", file=sys.stderr)
    raise SystemExit(2)

if path.exists():
    shutil.copy2(path, path.with_name(path.name + ".cursor-wsl-launcher.bak"))

descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
temporary = pathlib.Path(temporary_name)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if path.exists():
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
    os.replace(temporary, path)
finally:
    if temporary.exists():
        temporary.unlink()
PY
}

patch_jsonc_settings() {
  patch_jsonc_file "$1" settings "${2:-}"
}

patch_argv_json() {
  patch_jsonc_file "$1" argv
}

probe_url() {
  local url="$1"
  local extra=()
  if [[ -n "${2:-}" ]]; then
    extra+=(--proxy "$2")
  fi
  curl -sI -o /dev/null -w "%{http_code}" --max-time 8 --connect-timeout 5 "${extra[@]}" "$url" 2>/dev/null || printf '000'
}

current_http_handler() {
  if need_cmd xdg-mime; then
    xdg-mime query default x-scheme-handler/https 2>/dev/null || true
  fi
}

diagnose_display() {
  if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    DISPLAY_VERDICT="ok"
    note "[判定] GUI/WSLg: 正常 (DISPLAY=${DISPLAY:-empty} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-empty})"
  else
    DISPLAY_VERDICT="bad"
    note "[判定] GUI/WSLg: 异常 (没有 DISPLAY/WAYLAND_DISPLAY，Linux Cursor 窗口出不来)"
  fi
}

diagnose_browser() {
  local handler
  handler="$(current_http_handler)"
  WINDOWS_BROWSER="$(find_windows_browser || true)"
  if [[ -z "$WINDOWS_BROWSER" ]]; then
    BROWSER_VERDICT="bad"
    note "[判定] 默认浏览器: 异常 (WSL 里找不到 Windows Chrome/Edge/Firefox/cmd.exe)"
    return
  fi
  if [[ "$handler" == "cursor-wsl-windows-browser.desktop" ]]; then
    BROWSER_VERDICT="ok"
    note "[判定] 默认浏览器: 已修好 (xdg-open -> Windows 浏览器桥: $WINDOWS_BROWSER)"
    return
  fi
  if [[ -n "$handler" && "$handler" != "wslview.desktop" && "$handler" != "cursor-wsl-windows-browser.desktop" ]]; then
    BROWSER_VERDICT="bad"
    note "[判定] 默认浏览器: 异常 (https handler=$handler；WSLg 下 Linux Cursor 点 Join in 常打不开 Windows 登录页)"
    return
  fi
  if [[ -z "$handler" ]]; then
    BROWSER_VERDICT="bad"
    note "[判定] 默认浏览器: 异常 (未注册 x-scheme-handler/https。这是 Join in 点了没反应的最常见原因)"
    return
  fi
  BROWSER_VERDICT="warn"
  note "[判定] 默认浏览器: 半正常 (handler=$handler)。WSLg 有 DISPLAY 时 xdg-open 经常不用 wslview，仍可能打不开登录页"
}

diagnose_proxy() {
  local raw="${https_proxy:-${HTTPS_PROXY:-${http_proxy:-${HTTP_PROXY:-}}}}"
  local rewritten
  rewritten="$(rewrite_loopback_proxy "$raw")"
  local code_direct code_proxy
  code_direct="$(probe_url https://api2.cursor.sh)"
  if [[ -n "$rewritten" ]]; then
    code_proxy="$(probe_url https://api2.cursor.sh "$rewritten")"
  else
    code_proxy="skip"
  fi
  local settings_proxy=""
  if [[ -f "$USER_SETTINGS" ]]; then
    settings_proxy="$(python3 - "$USER_SETTINGS" <<'PY' || true
import json, pathlib, re, sys
p = pathlib.Path(sys.argv[1])
raw = p.read_text(encoding="utf-8")
body = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
body = re.sub(r"^\s*//.*$", "", body, flags=re.M)
try:
    data = json.loads(body)
except Exception:
    data = {}
print(data.get("http.proxySupport", ""), data.get("http.proxy", ""), data.get("cursor.general.disableHttp2", ""))
PY
)"
  fi

  if [[ "$code_direct" != "000" && -n "$code_direct" ]]; then
    AUTH_VERDICT="ok"
  else
    AUTH_VERDICT="bad"
  fi

  if [[ -n "$raw" && "$raw" != "$rewritten" ]]; then
    PROXY_VERDICT="bad"
    SELECTED_PROXY="$rewritten"
    note "[判定] 登录轮询/代理: 异常 (环境变量代理指向 127.0.0.1，在 WSL2 里打不到 Windows 代理。将改写为 $rewritten)"
  elif [[ "$settings_proxy" == override* || "$settings_proxy" == *"override"* ]]; then
    PROXY_VERDICT="bad"
    SELECTED_PROXY="$rewritten"
    note "[判定] 登录轮询/代理: 异常 (http.proxySupport=override 会挡住 Linux Cursor 后台 poll，官方常见根因)"
  elif [[ "$code_direct" == "000" && "$code_proxy" != "skip" && "$code_proxy" != "000" ]]; then
    PROXY_VERDICT="bad"
    SELECTED_PROXY="$rewritten"
    note "[判定] 登录轮询/代理: 异常 (直连 api2.cursor.sh 失败，经 $rewritten 成功 HTTP $code_proxy)"
  elif [[ "$code_direct" == "000" && ( "$code_proxy" == "skip" || "$code_proxy" == "000" ) ]]; then
    PROXY_VERDICT="bad"
    note "[判定] 登录轮询/代理: 异常 (直连和代理都访问不了 api2.cursor.sh，Join in 后必然卡在登录页)"
  else
    PROXY_VERDICT="ok"
    SELECTED_PROXY=""
    note "[判定] 登录轮询/代理: 正常 (api2.cursor.sh HTTP $code_direct；将强制 http.proxySupport=on 并关闭 HTTP/2 以免 Electron 默认值再挡住)"
  fi
  note "[信息] 当前 Cursor settings: ${settings_proxy:-<none>}"
}

diagnose_binary() {
  if SELECTED_BIN="$(find_cursor_bin)"; then
    BIN_VERDICT="ok"
    note "[判定] Linux Cursor 程序: 找到 $SELECTED_BIN"
  else
    BIN_VERDICT="bad"
    note "[判定] Linux Cursor 程序: 未找到 AppImage/二进制。请把 Linux 包放到 E:\\CursorDownload 或设置 CURSOR_LINUX_BIN"
  fi
}

print_verdict_summary() {
  note "-------- 总判定 --------"
  if [[ "$BROWSER_VERDICT" == "bad" || "$BROWSER_VERDICT" == "warn" ]]; then
    note "[总因] 默认浏览器/xdg-open 入口异常：Join in / Sign in 经常打不开 authenticator.cursor.sh"
  fi
  if [[ "$PROXY_VERDICT" == "bad" || "$AUTH_VERDICT" == "bad" ]]; then
    note "[总因] launcher/GUI 登录轮询入口异常：浏览器即使登录成功，Linux Cursor 也收不到会话"
  fi
  if [[ "$BROWSER_VERDICT" == "ok" && "$PROXY_VERDICT" == "ok" && "$DISPLAY_VERDICT" == "ok" && "$BIN_VERDICT" == "ok" ]]; then
    note "[总因] 启动链路看起来已修好。请用本脚本启动后，只点 Cursor 窗口里的 Sign in / Log in / Join in，不要手工打开登录页。"
  fi
  note "Linux 登录不会靠 cursor:// 跳回。浏览器停在 All set / 可以返回 Cursor 是正常的，IDE 会在后台轮询。"
}

apply_fixes() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    note "[dry-run] 跳过写入修复"
    return 0
  fi
  mkdir -p "$MARKER_DIR/User" "$APPS_DIR" "$(dirname "$MIME_FILE")"
  write_windows_url_bridge
  write_desktop_handler >/dev/null
  upsert_mime_default "$MIME_FILE"
  upsert_mime_default "$APPS_DIR/mimeapps.list"
  if need_cmd xdg-mime; then
    xdg-mime default cursor-wsl-windows-browser.desktop x-scheme-handler/https >/dev/null 2>&1 || true
    xdg-mime default cursor-wsl-windows-browser.desktop x-scheme-handler/http >/dev/null 2>&1 || true
  fi
  if need_cmd xdg-settings; then
    xdg-settings set default-web-browser cursor-wsl-windows-browser.desktop >/dev/null 2>&1 || true
  fi
  patch_jsonc_settings "$USER_SETTINGS" "$SELECTED_PROXY"
  patch_argv_json "$ARGV_JSON"
  note "[修复] 已写入 Windows 浏览器桥、mimeapps、http.proxySupport=on、disableHttp2=true"
}

prepare_env_for_launch() {
  export BROWSER="$URL_BRIDGE"
  # Keep Cursor's own proxy setting; WSL loopback proxy env vars break poll.
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY || true
  if [[ -n "$SELECTED_PROXY" ]]; then
    export http_proxy="$SELECTED_PROXY"
    export https_proxy="$SELECTED_PROXY"
    export HTTP_PROXY="$SELECTED_PROXY"
    export HTTPS_PROXY="$SELECTED_PROXY"
  fi
  export APPIMAGE_EXTRACT_AND_RUN=1
  export ELECTRON_OZONE_PLATFORM_HINT=x11
  if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]] && need_cmd dbus-launch; then
    # shellcheck disable=SC2046
    eval "$(dbus-launch --sh-syntax)"
  fi
}

launch_cursor() {
  local bin="$SELECTED_BIN"
  [[ -n "$bin" ]] || die "no Linux Cursor binary" 3
  chmod +x "$bin" 2>/dev/null || true
  prepare_env_for_launch
  local -a args=(--no-sandbox --disable-gpu-sandbox --disable-dev-shm-usage --ozone-platform=x11)
  if [[ "$bin" == *.AppImage || "$bin" == *.appimage ]]; then
    args+=(--appimage-extract-and-run)
  fi
  note "[启动] $bin ${args[*]}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    note "[dry-run] 不实际拉起 GUI"
    note "LAUNCH_OK=dry-run LOGIN_OK=not_yet"
    return 0
  fi
  local main_log="${LOG_FILE%.log}-main.log"
  # Detach completely so Cursor [main]/EventEmitter logs do not flood the bat window.
  # Those lines only mean the process started; they are not Join in / login success.
  if command -v setsid >/dev/null 2>&1; then
    setsid "$bin" "${args[@]}" </dev/null >>"$main_log" 2>&1 &
  else
    nohup "$bin" "${args[@]}" </dev/null >>"$main_log" 2>&1 &
    disown $! 2>/dev/null || true
  fi
  note "[启动] 已在后台拉起 Linux Cursor。点窗口里的 Sign in / Log in / Join in；浏览器登录后不要关 Cursor，等几秒让它自己进。"
  note "LAUNCH_OK=process_started LOGIN_OK=not_yet main_log=$main_log"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --diagnose-only) DIAGNOSE_ONLY=1; DO_LAUNCH=0; DO_FIX=0 ;;
      --fix-only) FIX_ONLY=1; DO_LAUNCH=0; DO_FIX=1 ;;
      --dry-run) DRY_RUN=1 ;;
      --no-fix) DO_FIX=0 ;;
      *)
        printf 'Unknown option: %s\n\n' "$1" >&2
        usage >&2
        exit 2
        ;;
    esac
    shift
  done
}

main() {
  parse_args "$@"
  mkdir -p "$(dirname "$LOG_FILE")"
  : >"$LOG_FILE" || true
  note "Cursor Linux login launcher"
  note "log: $LOG_FILE"
  diagnose_display
  diagnose_binary
  diagnose_browser
  diagnose_proxy
  print_verdict_summary

  if [[ "$DIAGNOSE_ONLY" -eq 1 ]]; then
    return 0
  fi
  if [[ "$DO_FIX" -eq 1 ]]; then
    apply_fixes
  fi
  if [[ "$BIN_VERDICT" != "ok" ]]; then
    die "Linux Cursor binary not found" 3
  fi
  if [[ "$DISPLAY_VERDICT" != "ok" && "$DRY_RUN" -eq 0 && "$FIX_ONLY" -eq 0 ]]; then
    die "No DISPLAY/WSLg; GUI login cannot start" 4
  fi
  if [[ "$DO_LAUNCH" -eq 1 ]]; then
    launch_cursor
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
