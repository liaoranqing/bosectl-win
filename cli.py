"""Windows console entry point for the bosectl command line.

Upstream bosectl ships exactly one entry point, ``pybmap.cli:main``, and
that module is preserved here byte-for-byte. This wrapper sits in front of
it and adds the parts that only make sense on Windows:

* **ANSI colour actually turns on.** Upstream enables colours only when
  ``sys.stdout.isatty()``, and a Windows console reports False until
  virtual-terminal processing is explicitly enabled. Without this call the
  CLI's gradient banner and status colours come out as escape-code soup.
* **Chinese help.** ``--help`` prints a localised cheat sheet; the upstream
  ``usage()`` remains reachable as ``--help-raw``.
* **Chinese errors.** Upstream writes its failure text and exits; the
  wrapper captures it and prints a translated summary, leaving the original
  line in place for bug reports.
* **``--diagnose``.** A Windows-only environment report — Bluetooth radio,
  paired devices, readable product IDs — for when a connection fails before
  the protocol layer is even reached.
* **Flags instead of only environment variables.** ``--mac``, ``--device``
  and ``--timeout`` are mapped onto the ``BOSE_MAC`` / ``BMAP_MAC`` /
  ``BMAP_DEVICE`` variables upstream already reads, so the documented
  upstream usage keeps working unchanged.

Exit codes match upstream: 0 on success, 1 on any handled failure.
"""

from __future__ import annotations

import io
import os
import sys

__all__ = ["main"]

VERSION_LINE = "BoseCtl for Windows"

WINDOWS_HELP = """\
BoseCtl for Windows — 命令行工具
================================

用法：
    bosectl [选项] <命令> [参数…]

连接选项（也可用环境变量 BOSE_MAC / BMAP_MAC、BMAP_DEVICE 指定）：
    -m, --mac AA:BB:CC:DD:EE:FF   指定耳机蓝牙地址
    -d, --device <型号>           指定型号：qc_ultra2 / qc_ultra2_earbuds /
                                  qc35 / qc45 / qc_prince / qc_earbuds /
                                  ultra_open
    -t, --timeout <秒>            单通道连接超时，默认 6
        --mock                    使用内置模拟设备，无需真实耳机
        --diagnose                打印 Windows 蓝牙环境自检报告
        --version                 显示版本
    -h, --help                    显示本帮助
        --help-raw                显示上游原始英文帮助

常用命令（与上游 bosectl 完全一致）：
    status                显示全部状态（型号、电量、模式、设置）
    battery               只输出电量数字
    cnc [0-10]            查看/设置降噪等级（0 = 最强降噪）
    anr off|low|high|wind QC35 世代的降噪模式
    anc on|off            主动降噪开关
    wind on|off           抗风噪开关
    eq B M T              设置均衡器（-10…+10），或 eq flat
    spatial off|room|head 空间音频
    name [文字]           查看/设置设备名称
    prompts on|off        语音提示开关
    multipoint on|off     多点连接
    autopause on|off      摘下自动暂停
    autoanswer on|off     自动接听
    sidetone off|low|medium|high
    profiles              列出全部音频配置
    profile set NAME …    新建/更新自定义配置
    profile rm NAME       删除自定义配置
    switch NAME           切换到指定配置
    quiet / aware / immersion / cinema    切到预设模式
    source                当前音频来源
    route <MAC>           把音频切到另一台设备
    pair                  进入蓝牙配对模式
    off                   关闭耳机电源
    buttons [set <动作>]  查看/重映射按键
    dump                  导出全部模式状态
    raw <十六进制>        直接发送 BMAP 数据包，如 raw 1f 01 05 00

示例：
    bosectl --mock status
    bosectl --diagnose
    bosectl --mac 68:F2:1F:0D:F5:11 --device qc_ultra2 cnc 8
    bosectl status

说明：BMAP 的部分功能（如重命名、按键重映射）需要耳机接受 SETGET
操作；不受支持的项会明确报错，而不是静默失败。
"""


def _enable_virtual_terminal():
    """Turn on ANSI escape processing in the current Windows console.

    Returns True when colours can be rendered. Windows Terminal and the
    modern conhost both support this; only the opt-in is missing.
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handles = []
        for std in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(std)
            if handle in (0, -1, None):
                continue
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                continue
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            handles.append(handle)
        return bool(handles)
    except Exception:
        return False


def _configure_console():
    """Make stdout/stderr UTF-8 so Chinese text is not mangled by cp936."""
    for stream in ("stdout", "stderr"):
        current = getattr(sys, stream, None)
        if current is None:
            continue
        encoding = (getattr(current, "encoding", "") or "").lower()
        if encoding.replace("-", "") in ("utf8", "utf8mb4"):
            continue
        try:
            current.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # Not a TextIOWrapper (or already detached): wrap it instead.
            buffer = getattr(current, "buffer", None)
            if buffer is not None:
                setattr(sys, stream, io.TextIOWrapper(
                    buffer, encoding="utf-8", errors="replace", line_buffering=True))


class _Tee:
    """Mirror a stream into a buffer so failures can be re-reported."""

    def __init__(self, stream, buffer):
        self._stream = stream
        self._buffer = buffer

    def write(self, text):
        self._buffer.write(text)
        return self._stream.write(text)

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass

    def __getattr__(self, item):
        return getattr(self._stream, item)


def _parse_flags(argv):
    """Split wrapper flags from the upstream command line.

    Returns:
        (flags, remaining) where ``flags`` holds the recognised options and
        ``remaining`` is what should be handed to ``pybmap.cli``.
    """
    flags = {"mac": None, "device": None, "timeout": None}
    rest = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        index += 1
        if arg in ("-m", "--mac"):
            if index < len(argv):
                flags["mac"] = argv[index]
                index += 1
        elif arg in ("-d", "--device"):
            if index < len(argv):
                flags["device"] = argv[index]
                index += 1
        elif arg in ("-t", "--timeout"):
            if index < len(argv):
                flags["timeout"] = argv[index]
                index += 1
        elif arg.startswith("--mac="):
            flags["mac"] = arg.split("=", 1)[1]
        elif arg.startswith("--device="):
            flags["device"] = arg.split("=", 1)[1]
        elif arg.startswith("--timeout="):
            flags["timeout"] = arg.split("=", 1)[1]
        else:
            rest.append(arg)
    return flags, rest


def _print_version():
    import pybmap
    print("%s %s" % (VERSION_LINE, pybmap.__version__))
    print("  pybmap            %s (%s)" % (pybmap.__version__, pybmap.PORT_NAME))
    print("  上游兼容版本      pybmap %s (aaronsb/bosectl)"
          % pybmap.UPSTREAM_VERSION)
    print("  Python            %s · %s" % (sys.version.split()[0], sys.platform))
    print("  支持机型          %s" % ", ".join(sorted(pybmap.DEVICES)))


def _run_diagnostics():
    """Print the Windows Bluetooth environment report."""
    import pybmap

    print("BoseCtl for Windows — 蓝牙环境自检")
    print("=" * 44)
    try:
        report = pybmap.diagnose()
    except Exception as exc:  # pragma: no cover - defensive
        print("自检失败：%s" % exc)
        return 1

    def line(label, value):
        print("  %-16s %s" % (label, value))

    present = bool(report.get("radio_present"))
    connectable = bool(report.get("radio_connectable"))

    line("操作系统", report.get("platform", "—"))
    line("蓝牙适配器", "已检测到" if present else "未检测到")
    line("蓝牙开关", "已开启" if connectable else ("已关闭" if present else "—"))
    line("已配对设备", report.get("paired_count", 0))
    line("可枚举设备", report.get("enumerated_count", 0))
    line("识别为 Bose", report.get("bose_count", 0))
    line("可读产品 ID", report.get("product_ids_known", 0))
    line("WinRT 投影", "已安装" if report.get("winrt_available") else "未安装")

    devices = report.get("devices", [])
    if devices:
        print("\n设备列表：")
        for device in devices:
            detail = device.get("mac", "")
            if device.get("product_id"):
                detail += "  PID 0x%04X" % device["product_id"]
            if device.get("suggested_type"):
                detail += "  → %s" % device["suggested_type"]
            flags = []
            if device.get("connected"):
                flags.append("已连接")
            elif device.get("paired"):
                flags.append("已配对")
            if device.get("bose"):
                flags.append("Bose")
            print("  %-34s %s%s" % (
                (device.get("name") or "未命名")[:34], detail,
                ("  [%s]" % ", ".join(flags)) if flags else ""))

    print()
    if not present:
        print("结论：未检测到蓝牙适配器。请确认电脑有蓝牙模块；台式机通常需要外接"
              "蓝牙适配器，或在「设备管理器」中检查蓝牙驱动。")
        return 1
    if not connectable:
        print("结论：蓝牙适配器存在，但蓝牙处于关闭状态。"
              "请在「设置 → 蓝牙和其他设备」中打开蓝牙开关后重试。")
        return 1
    if not devices:
        print("结论：没有已配对的蓝牙设备。请先完成 Windows 蓝牙配对。")
        return 1
    bose = [d for d in devices if d.get("bose")]
    if not bose:
        print("结论：已配对设备中没有识别到 Bose 耳机。"
              "如果耳机确实已配对，请用 --mac 手动指定地址。")
        return 1
    print("结论：发现 %d 台 Bose 设备，可用下列命令连接：" % len(bose))
    for device in bose:
        print("  bosectl --mac %s --device %s status"
              % (device.get("mac"), device.get("suggested_type") or "qc_ultra2"))
    return 0


def main(argv=None):
    """Console entry point.

    Returns:
        Process exit code. ``sys.exit`` is only raised for the paths that
        delegate to upstream, which calls it itself.
    """
    argv = list(sys.argv[1:] if argv is None else argv)

    # Windows console prerequisites.
    _configure_console()
    _enable_virtual_terminal()

    if "--version" in argv or "-V" in argv:
        _print_version()
        return 0
    if "--help" in argv or "-h" in argv:
        print(WINDOWS_HELP)
        return 0
    if "--diagnose" in argv:
        return _run_diagnostics()

    flags, rest = _parse_flags(argv)

    mock = "--mock" in rest or "--demo" in rest
    rest = [a for a in rest if a not in ("--mock", "--demo")]

    if "--help-raw" in rest:
        # Upstream's usage() prints the English cheat sheet and exits.
        from pybmap import cli as upstream_cli
        rest = [a for a in rest if a != "--help-raw"]
        if not rest:
            upstream_cli.usage()
            return 0

    if mock:
        os.environ["BMAP_MOCK"] = "1"
    if flags["mac"]:
        os.environ["BOSE_MAC"] = flags["mac"]
    if flags["device"]:
        os.environ["BMAP_DEVICE"] = flags["device"]
    if flags["timeout"]:
        try:
            os.environ["BMAP_TIMEOUT"] = str(float(flags["timeout"]))
        except ValueError:
            print("错误：--timeout 需要一个数字，收到 %r" % flags["timeout"],
                  file=sys.stderr)
            return 1

    if not rest:
        print(WINDOWS_HELP)
        return 0

    # Delegate to the upstream dispatcher, collecting its stderr so a
    # failure can be re-stated in Chinese afterwards. Upstream reads
    # sys.argv directly, so the command line is swapped in rather than
    # editing that module — it stays byte-for-byte identical to upstream.
    from pybmap import cli as upstream_cli

    captured = io.StringIO()
    original_stderr = sys.stderr
    original_argv = sys.argv
    sys.stderr = _Tee(original_stderr, captured)
    sys.argv = ["bosectl"] + rest
    code = 0
    try:
        upstream_cli.main()
        code = 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    finally:
        sys.stderr = original_stderr
        sys.argv = original_argv

    if code:
        from pybmap.messages import translate_message
        text = captured.getvalue().strip()
        if text:
            translated = translate_message(text)
            if translated != text:
                # Send the summary to stderr, after the original line, so
                # piping stdout still yields clean machine-readable output.
                print("\n中文提示：\n%s" % translated, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
