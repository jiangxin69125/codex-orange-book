#!/usr/bin/env bash
# Automated tests for the WSL Cursor Linux login launcher (no GUI required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/launch-cursor-linux.sh"
PASS=0
FAIL=0
WORKDIR=""

cleanup() {
  if [[ -n "$WORKDIR" && -d "$WORKDIR" ]]; then
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

fail() {
  FAIL=$((FAIL + 1))
  printf 'FAIL  %s\n' "$1"
}

ok() {
  PASS=$((PASS + 1))
  printf 'PASS  %s\n' "$1"
}

expect_eq() {
  local got="$1" want="$2" name="$3"
  if [[ "$got" == "$want" ]]; then
    ok "$name"
  else
    fail "$name (got='$got' want='$want')"
  fi
}

expect_file_contains() {
  local file="$1" needle="$2" name="$3"
  if grep -F -- "$needle" "$file" >/dev/null; then
    ok "$name"
  else
    fail "$name (missing '$needle' in $file)"
  fi
}

expect_exit() {
  local want="$1" name="$2"
  shift 2
  local rc=0
  "$@" >/dev/null 2>&1 || rc=$?
  expect_eq "$rc" "$want" "$name"
}

WORKDIR="$(mktemp -d /tmp/cursor-wsl-launcher-test.XXXXXX)"
export HOME="$WORKDIR/home"
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
mkdir -p "$HOME" "$WORKDIR/bin" "$WORKDIR/download"

# Isolated copy so tests do not touch the repo working tree logs.
cp "$SRC" "$WORKDIR/launch-cursor-linux.sh"
chmod +x "$WORKDIR/launch-cursor-linux.sh"

# shellcheck disable=SC1091
source "$WORKDIR/launch-cursor-linux.sh"

echo "== unit: rewrite_loopback_proxy =="
WINDOWS_HOST_IP="1.2.3.4"
export WINDOWS_HOST_IP
expect_eq "$(rewrite_loopback_proxy 'http://127.0.0.1:7890')" "http://1.2.3.4:7890" "rewrite 127.0.0.1 proxy to Windows host"
expect_eq "$(rewrite_loopback_proxy 'http://localhost:7890')" "http://1.2.3.4:7890" "rewrite localhost proxy"
expect_eq "$(rewrite_loopback_proxy 'http://10.0.0.8:7890')" "http://10.0.0.8:7890" "leave non-loopback proxy"

echo "== unit: is_linux_cursor_bin =="
touch "$WORKDIR/download/Cursor.exe"
touch "$WORKDIR/download/Cursor.AppImage"
chmod +x "$WORKDIR/download/Cursor.AppImage"
if is_linux_cursor_bin "$WORKDIR/download/Cursor.exe"; then
  fail "reject Windows Cursor.exe"
else
  ok "reject Windows Cursor.exe"
fi
if is_linux_cursor_bin "$WORKDIR/download/Cursor.AppImage"; then
  ok "accept Linux AppImage"
else
  fail "accept Linux AppImage"
fi

echo "== unit: settings + mime patch =="
USER_SETTINGS="$XDG_CONFIG_HOME/Cursor/User/settings.json"
MIME_FILE="$XDG_CONFIG_HOME/mimeapps.list"
APPS_DIR="$XDG_DATA_HOME/applications"
mkdir -p "$(dirname "$USER_SETTINGS")" "$APPS_DIR"
printf '{\n  // comment\n  "editor.fontSize": 14,\n  "http.proxySupport": "override"\n}\n' >"$USER_SETTINGS"
printf '[Default Applications]\nx-scheme-handler/https=discover.desktop\n' >"$MIME_FILE"
patch_jsonc_settings "$USER_SETTINGS" "http://1.2.3.4:7890"
upsert_mime_default "$MIME_FILE"
expect_file_contains "$USER_SETTINGS" '"http.proxySupport": "on"' "force proxySupport=on"
expect_file_contains "$USER_SETTINGS" '"cursor.general.disableHttp2": true' "disable HTTP/2"
expect_file_contains "$USER_SETTINGS" '"http.proxy": "http://1.2.3.4:7890"' "write rewritten proxy"
expect_file_contains "$USER_SETTINGS" '"editor.fontSize": 14' "preserve existing setting"
expect_file_contains "$MIME_FILE" 'x-scheme-handler/https=cursor-wsl-windows-browser.desktop' "https handler -> Windows bridge"
expect_file_contains "$MIME_FILE" 'x-scheme-handler/http=cursor-wsl-windows-browser.desktop' "http handler -> Windows bridge"

echo "== unit: url bridge script =="
SCRIPT_DIR="$WORKDIR"
URL_BRIDGE="$WORKDIR/open-url-on-windows.sh"
write_windows_url_bridge
if [[ -x "$URL_BRIDGE" ]]; then
  ok "url bridge is executable"
else
  fail "url bridge is executable"
fi
expect_file_contains "$URL_BRIDGE" 'start ""' "cmd start uses empty title then URL"
rc=0
"$URL_BRIDGE" >/dev/null 2>&1 || rc=$?
expect_eq "$rc" "2" "url bridge without args exits 2"

echo "== cli: --help =="
help_out="$("$WORKDIR/launch-cursor-linux.sh" --help)"
if printf '%s' "$help_out" | grep -q -- '--diagnose-only'; then
  ok "help lists --diagnose-only"
else
  fail "help lists --diagnose-only"
fi
if printf '%s' "$help_out" | grep -q 'Examples:'; then
  ok "help includes examples"
else
  fail "help includes examples"
fi
expect_exit 2 "unknown flag exits 2" "$WORKDIR/launch-cursor-linux.sh" --not-a-real-flag

echo "== cli: diagnose + dry-run launch =="
export CURSOR_LINUX_BIN="$WORKDIR/download/Cursor.AppImage"
export DISPLAY=":0"
export CURSOR_LAUNCHER_LOG="$WORKDIR/cursor-linux-login.log"
export SCRIPT_DIR="$WORKDIR"
# Re-run as a subprocess so SCRIPT_DIR/log isolation matches real CLI use.
diag_out="$(CURSOR_LAUNCHER_LOG="$WORKDIR/d.log" CURSOR_LINUX_BIN="$CURSOR_LINUX_BIN" DISPLAY=":0" WINDOWS_HOST_IP="1.2.3.4" \
  HOME="$HOME" XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_DATA_HOME="$XDG_DATA_HOME" \
  "$WORKDIR/launch-cursor-linux.sh" --diagnose-only 2>&1)" || true
printf '%s\n' "$diag_out" >"$WORKDIR/diagnose.txt"
expect_file_contains "$WORKDIR/diagnose.txt" '[判定] Linux Cursor 程序: 找到' "diagnose finds AppImage"
expect_file_contains "$WORKDIR/diagnose.txt" '[判定] GUI/WSLg: 正常' "diagnose sees DISPLAY"
expect_file_contains "$WORKDIR/diagnose.txt" '[总因]' "diagnose prints root-cause summary"

fix_out="$(CURSOR_LAUNCHER_LOG="$WORKDIR/f.log" CURSOR_LINUX_BIN="$CURSOR_LINUX_BIN" DISPLAY=":0" WINDOWS_HOST_IP="1.2.3.4" \
  HOME="$HOME" XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_DATA_HOME="$XDG_DATA_HOME" \
  "$WORKDIR/launch-cursor-linux.sh" --dry-run --fix-only 2>&1)" || rc=$?
printf '%s\n' "$fix_out" >"$WORKDIR/fix.txt"
expect_file_contains "$WORKDIR/fix.txt" '[dry-run] 跳过写入修复' "dry-run skips writes"

dry_launch="$(CURSOR_LAUNCHER_LOG="$WORKDIR/dl.log" CURSOR_LINUX_BIN="$CURSOR_LINUX_BIN" DISPLAY=":0" WINDOWS_HOST_IP="1.2.3.4" \
  HOME="$HOME" XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_DATA_HOME="$XDG_DATA_HOME" \
  "$WORKDIR/launch-cursor-linux.sh" --dry-run 2>&1)" || true
printf '%s\n' "$dry_launch" >"$WORKDIR/dry-launch.txt"
expect_file_contains "$WORKDIR/dry-launch.txt" 'LAUNCH_OK=dry-run LOGIN_OK=not_yet' "dry-run launch prints not-logged-in marker"

if grep -q "还不等于已经登录" "$ROOT/Launch-Cursor-Linux.bat"; then
  ok "bat tells user process logs are not login success"
else
  fail "bat tells user process logs are not login success"
fi
if grep -q "setsid" "$ROOT/launch-cursor-linux.sh"; then
  ok "launcher detaches Cursor so [main] logs stay out of the bat window"
else
  fail "launcher detaches Cursor so [main] logs stay out of the bat window"
fi

# Real fix-only should write files into the fake HOME.
CURSOR_LAUNCHER_LOG="$WORKDIR/fix2.log" CURSOR_LINUX_BIN="$CURSOR_LINUX_BIN" DISPLAY=":0" WINDOWS_HOST_IP="1.2.3.4" \
  HOME="$HOME" XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_DATA_HOME="$XDG_DATA_HOME" \
  "$WORKDIR/launch-cursor-linux.sh" --fix-only >/dev/null
expect_file_contains "$XDG_CONFIG_HOME/Cursor/User/settings.json" '"http.proxySupport": "on"' "fix-only writes settings"
if [[ -x "$WORKDIR/open-url-on-windows.sh" || -x "$ROOT/open-url-on-windows.sh" ]]; then
  ok "fix-only created url bridge next to script"
else
  fail "fix-only created url bridge next to script"
fi
if [[ -f "$XDG_DATA_HOME/applications/cursor-wsl-windows-browser.desktop" ]]; then
  ok "fix-only wrote Windows browser desktop handler"
else
  fail "fix-only wrote Windows browser desktop handler"
fi

echo "== cli: missing binary =="
expect_exit 3 "missing binary exits 3" env CURSOR_LAUNCHER_LOG="$WORKDIR/m.log" CURSOR_LINUX_BIN="$WORKDIR/nope" DISPLAY=":0" \
  HOME="$HOME" "$WORKDIR/launch-cursor-linux.sh" --fix-only

echo
echo "passed=$PASS failed=$FAIL"
if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi
