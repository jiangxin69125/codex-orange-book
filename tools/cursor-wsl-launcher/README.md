# Cursor Linux（WSL2）Join in / 登录修复启动器

把这两个文件覆盖到本机 `E:\CursorDownload\` 后，再双击 bat：

- `Launch-Cursor-Linux.bat`
- `launch-cursor-linux.sh`

## 结论（先看这个）

企鹅标窗口能弹出来，说明 **launcher 的 GUI 启动是通的**（WSLg 在画 Linux Cursor）。  
点 **Join in / Sign in / Log in** 进不去，通常不是“按钮坏了”，而是后面两段登录链路坏了，而且经常同时坏：

1. **默认浏览器 / `xdg-open` 异常（更常见）**  
   Linux Cursor 点登录时会让 WSL 打开 `authenticator.cursor.sh`。WSLg 一旦有 `DISPLAY`，`xdg-open` 就不会走 `wslview`，WSL 里又常常没有 Linux 浏览器，于是按钮“点了没反应”，或登录页根本打不开。
2. **launcher 没有修 GUI 登录轮询入口**  
   Linux 版 **不会** 靠 `cursor://` 跳回 App。浏览器停在 All set / 可以返回 Cursor 是正常的，IDE 在后台轮询 `api2.cursor.sh`。Electron 默认 `Http: Proxy Support = override`，以及 WSL 里 `http_proxy=http://127.0.0.1:7890`（打的是 Linux 自己，不是 Windows 代理），都会让轮询静默失败，所以网页登完了窗口还是进不去。

参考：[Linux 登录不回跳、靠轮询](https://forum.cursor.com/t/linux-kde-login-redirect-issue/161870)、[网页登录后客户端不进](https://forum.cursor.com/t/cursor-desktop-app-does-not-sign-in-after-signing-in-from-web/152630/1)。

## 这个启动器会自动做什么

双击 `Launch-Cursor-Linux.bat` 时会：

- 找 `E:\CursorDownload` 下最新的 Linux AppImage / `cursor` 二进制（不启动 `Cursor.exe`）
- 注册 **Windows 浏览器桥**：`xdg-open https://...` → `cmd.exe /c start "" <url>`
- 写入 `~/.config/Cursor/User/settings.json`：`http.proxySupport=on`、`cursor.general.disableHttp2=true`
- 若代理是 `127.0.0.1`，改写成 WSL 的 Windows 主机 IP
- 用 `--no-sandbox --appimage-extract-and-run` 启动，避免 WSL 没有 FUSE

日志写在 `E:\CursorDownload\cursor-linux-login.log`。里面有 `[判定]` / `[总因]`。

## 用法

```text
Launch-Cursor-Linux.bat
Launch-Cursor-Linux.bat --diagnose-only
Launch-Cursor-Linux.bat --fix-only
Launch-Cursor-Linux.bat --dry-run
```

WSL 里也可以直接跑：

```bash
bash /mnt/e/CursorDownload/launch-cursor-linux.sh --help
CURSOR_LINUX_BIN=/mnt/e/CursorDownload/Cursor-xxx.AppImage bash /mnt/e/CursorDownload/launch-cursor-linux.sh
```

## 点 Join in 之后怎么才算成功

1. 只用 **企鹅标那个 Linux Cursor 窗口** 里的 Sign in / Log in / Join in，不要自己另开 cursor.com。
2. Windows 浏览器应弹出 Cursor 登录页。登录完可以停在 All set。
3. **不要关** Linux Cursor。等几秒，它会自己进入工作区。
4. 若浏览器都没弹出：看日志里默认浏览器判定，确认本机有 Chrome / Edge。
5. 若浏览器登完窗口不动：看日志里代理/轮询判定；需要代理时把 Clash/V2Ray 开允许局域网，不要让 WSL 去连 `127.0.0.1`。
