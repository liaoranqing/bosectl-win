#!/usr/bin/env python3
"""BoseCtl for Windows — single development entry point.

Dispatches to the desktop GUI or the command line, so one command covers
both during development::

    python bosectl.py                 # desktop GUI
    python bosectl.py --demo          # GUI, straight into demo mode
    python bosectl.py status          # CLI, same as upstream bosectl
    python bosectl.py --mock status   # CLI against the simulated device
    python bosectl.py --version

The packaged builds do not use this file: the windowed ``BoseCtl.exe`` and
the console ``bosectl.exe`` have their own entry scripts (see ``build/``),
because Windows decides console-vs-windowed at link time and one executable
cannot be both cleanly.
"""

import sys

USAGE = """\
BoseCtl for Windows

    python bosectl.py                 启动桌面界面
    python bosectl.py --demo          启动界面并直接进入演示模式
    python bosectl.py <命令> …        运行命令行（与上游 bosectl 一致）
    python bosectl.py --version       显示版本
    python bosectl.py --help          显示命令行帮助

设置 BMAP_MOCK=1 可让命令行使用内置模拟设备，无需真实耳机。
"""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--version" in argv and len(argv) == 1:
        import pybmap
        print("BoseCtl for Windows %s (pybmap %s · %s · upstream %s)"
              % (pybmap.__version__, pybmap.__version__, pybmap.PORT_NAME,
                 pybmap.UPSTREAM_VERSION))
        return 0

    if not argv:
        return _run_gui([])

    if argv[0] in ("--gui", "--desktop"):
        return _run_gui(argv[1:])
    if argv[0] in ("-h", "--usage"):
        print(USAGE)
        return 0

    from cli import main as cli_main
    return cli_main(argv)


def _run_gui(extra):
    if extra and "--help" in extra:
        print(USAGE)
        return 0
    try:
        from gui.app import main as gui_main
    except ImportError as exc:
        # The GUI needs tkinter, which some minimal Python builds omit. Say
        # so plainly instead of dumping a traceback on a new user.
        print("无法启动桌面界面：%s" % exc, file=sys.stderr)
        print("请安装带 tkinter 的 Python，或改用命令行：python bosectl.py --help",
              file=sys.stderr)
        return 2
    return gui_main(["bosectl"] + list(extra))


if __name__ == "__main__":
    sys.exit(main())
