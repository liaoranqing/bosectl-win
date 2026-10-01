<div align="center">

# BoseCtl for Windows

**在 Windows 上本地控制 Bose 耳机 — 不装 App、不连云端、不需要账号。**

基于 [aaronsb/bosectl](https://github.com/aaronsb/bosectl)（BMAP 协议逆向工程）的完整 Windows 移植，
包含精美桌面前端、命令行工具，以及一键下载即用的单文件 EXE。

[![CI](https://github.com/liaoranqing/bosectl-win/actions/workflows/ci.yml/badge.svg)](https://github.com/liaoranqing/bosectl-win/actions/workflows/ci.yml)
[![Build](https://github.com/liaoranqing/bosectl-win/actions/workflows/build.yml/badge.svg)](https://github.com/liaoranqing/bosectl-win/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

## 这是什么

Bose 耳机通过一条未被公开文档化的 **BMAP** 通道（蓝牙 RFCOMM）接受本地控制。上游 bosectl 在
Linux / macOS 上实现了这套协议，但依赖 POSIX 的 `AF_BLUETOOTH` 套接字或 macOS 的 IOBluetooth
框架 —— 两者在 Windows 上都不存在。

本项目把整条链路搬到了 Windows：

| 层 | 上游实现 | 本项目 |
| --- | --- | --- |
| 协议编解码 | `pybmap/protocol.py` | **逐字保留** |
| 设备目录 / 产品 ID | `pybmap/catalog.py` | **逐字保留** |
| 各型号寄存器配置 | `pybmap/devices/` | **逐字保留** |
| 连接与重试逻辑 | `pybmap/connection.py`、`__init__.py` | **逻辑保留**，传输层换成 Windows 实现 |
| 命令行 | `pybmap/cli.py` | **逐字保留**，外层加 Windows 入口包装 |
| 传输层 | `AF_BLUETOOTH` / IOBluetooth | **重写**：`ctypes` → Winsock `AF_BTH` RFCOMM |
| 设备发现 | `bluetoothctl` + Modalias | **重写**：注册表 + `bluetoothapis.dll` + SetupAPI 硬件 ID |
| 界面 | bosectl-qt（Qt6 / Linux） | **新增**：CustomTkinter 桌面前端 |

> **这不是破解。** 使用的是 BMAP 标准的 `SETGET` 操作符，耳机本来就不对此做鉴权。
> 不提取密钥、不破解加密、不重放流量。

## 功能

界面截图见 [`build/screenshots/`](build/screenshots)。

| 页面 | 能力 |
| --- | --- |
| **连接** | 扫描已配对设备（自动识别型号）、手动指定地址与型号、连接超时、启动时自动连接、**演示模式** |
| **声音** | 降噪等级（CNC 0-10 滑杆）、主动降噪开关、抗风噪、空间音频（关/房间/头部）、三频均衡器（-10…+10） |
| **模式** | 四个内置预设（安静 / 感知 / 沉浸 / 影院）、自定义配置的新建/更新/删除、全部槽位一览 |
| **设备** | 设备名称、多点连接、摘下自动暂停、自动接听、语音提示与语言、按键映射读取与重映射 |
| **高级** | 音频源与路由切换、进入配对模式、关闭耳机、导出全部模式状态、**Windows 蓝牙环境自检**、原始 BMAP 数据包控制台、电池明细（耳塞/充电盒分项） |
| **关于** | 支持机型列表、版本信息、上游归属 |

命令行覆盖上游 `bosectl` 的全部命令（`status`、`cnc`、`anr`、`eq`、`spatial`、`profiles`、
`profile set/rm`、`switch`、`multipoint`、`prompts`、`buttons`、`source`、`route`、`pair`、`off`、
`dump`、`raw`、以及 `quiet`/`aware`/`immersion`/`cinema` 预设）。

**支持机型**：QuietComfort Ultra 耳机（2 代）、QuietComfort Ultra 耳塞（2 代）、QuietComfort
Headphones、QuietComfort 45、QuietComfort 耳塞、QuietComfort 35 / 35 II、Ultra Open 耳塞。

## 下载即用

从 [Releases](https://github.com/liaoranqing/bosectl-win/releases) 下载，**无需安装 Python**：

| 文件 | 说明 |
| --- | --- |
| `BoseCtl.exe` | 桌面程序。双击运行。 |
| `bosectl-cli.exe` | 命令行工具。`bosectl-cli.exe --help` 查看用法。 |
| `SHA256SUMS` | 校验和，用于确认下载完整。 |

> 命令行程序为什么叫 `bosectl-cli.exe` 而不是 `bosectl.exe`？因为
> `BoseCtl.exe` 和 `bosectl.exe` 忽略大小写后是**同一个文件名**，在 Windows/macOS 上
> 同时下载到同一个文件夹会互相覆盖。加 `-cli` 后缀可以避免这个坑。

Windows SmartScreen 首次运行会提示"未知发布者"（EXE 未做代码签名）：点"更多信息 → 仍要运行"。
如介意，可自行从源码构建 —— 见下。

### 使用前：配对

1. Windows「设置 → 蓝牙和其他设备 → 添加设备」，选你的 Bose 耳机，等它显示"已连接"。
2. **关掉手机上的 Bose 应用。** 耳机的 BMAP 通道同一时间只允许一个连接；手机端占用时，
   本程序会提示"设备正忙"。
3. 打开 `BoseCtl.exe`，在"连接"页点"重新扫描"，设备列表里应当出现你的耳机（带 ★Bose 标记），
   点"连接"。
4. 没有耳机也能用：点"**启动演示模式**"，界面里所有功能都能点、能改，只是不发送到真实硬件。

## 命令行

```bash
# 环境自检：蓝牙适配器、已配对设备、能否读到产品 ID
bosectl-cli.exe --diagnose

# 无硬件试跑（内置模拟设备）
bosectl-cli.exe --mock status

# 真实设备
bosectl-cli.exe status                 # 型号、电量、模式、全部设置
bosectl-cli.exe cnc 8                  # 降噪等级（0 = 最强降噪）
bosectl-cli.exe eq 3 0 -2              # 均衡器：低音/中音/高音
bosectl-cli.exe spatial head           # 空间音频
bosectl-cli.exe switch 沉浸            # 切换到指定配置
bosectl-cli.exe profile set 通勤 cnc=8 spatial=off wind=on
bosectl-cli.exe raw 1f 01 05 00        # 直接发送 BMAP 数据包

# 指定设备
bosectl-cli.exe --mac 68:F2:1F:0D:F5:11 --device qc_ultra2 status
```

`bosectl-cli.exe --help` 是中文速查表；`--help-raw` 保留上游原始英文帮助。
环境变量 `BOSE_MAC` / `BMAP_MAC`、`BMAP_DEVICE`、`BMAP_TIMEOUT`、`BMAP_MOCK` 与上游一致。

## 从源码运行

需要 Python 3.9+（图形界面需要带 tkinter 的 Python）。

```bash
git clone https://github.com/liaoranqing/bosectl-win.git
cd bosectl-win
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt

python bosectl.py                  # 桌面界面
python bosectl.py --demo           # 直接进演示模式
python bosectl.py status           # 命令行
pytest tests -q                    # 测试
```

## 在 GitHub 上构建

**不需要本地打包环境。** 三条流水线覆盖全流程：

| 流水线 | 触发 | 产出 |
| --- | --- | --- |
| [`ci.yml`](.github/workflows/ci.yml) | push / PR | 版本一致性检查、全量测试（Windows 3.9/3.11/3.13 + Linux + macOS）、界面冒烟测试、ruff 检查 |
| [`build.yml`](.github/workflows/build.yml) | push / PR / 手动 | 打包 `BoseCtl.exe` 与 `bosectl-cli.exe`，实际启动验证，SHA256 校验，PE 子系统检查，上传为构建产物 |
| [`release.yml`](.github/workflows/release.yml) | 推送 `v*` 标签 | 校验版本号一致 → 跑测试 → 打包 → 验证 → 自动创建 GitHub Release 并附上 EXE 与校验和 |

发布新版本只需：

```bash
# 1. 同步四处版本号（脚本会告诉你哪里不一致）
python scripts/check_version.py
#    连带上标签一起校验：
python scripts/check_version.py v1.1.0

# 2. 提交后打标签
git commit -am "Release v1.1.0"
git tag v1.1.0
git push origin main --tags
```

流水线会拒绝版本号不一致的标签，因此不会出现"Release 写 1.1.0、EXE 属性写 1.0.0"的情况。

### 构建过程做了什么验证

打包不是"能编译就算过"。构建流水线会在 Windows runner 上实际验证：

- `bosectl-cli.exe --version` / `--help` / `--mock status` / `--mock cnc 8` 均返回 0；
- `BoseCtl.exe --demo` 启动后 20 秒仍在运行（能抓住"启动即崩溃"：主题资源缺失、
  customtkinter 参数改名等）；
- 两个 EXE 的 SHA256 与记录一致；
- `bosectl-cli.exe` 的属性对话框里 `FileVersion` 与源码版本号一致；
- `BoseCtl.exe` 的 PE 子系统是 `WINDOWS_GUI`（否则每次启动都会闪黑框）。

界面本身由 `tests/test_gui_smoke.py` 覆盖：它创建真实窗口、连到模拟耳机、逐页访问、
来回切换主题、并跑通"写降噪等级 → 读回校验"的完整链路。

## 项目结构

```
bosectl-win/
├── pybmap/                  BMAP 库（协议、设备配置、连接、Windows 传输与发现）
│   ├── protocol.py          BMAP 数据包编解码          ← 上游逐字保留
│   ├── connection.py        类型化连接 API              ← 上游逐字保留
│   ├── cli.py               命令行实现                  ← 上游逐字保留
│   ├── catalog.py           设备目录 / 产品 ID          ← 上游逐字保留
│   ├── devices/             各型号寄存器配置            ← 上游逐字保留
│   ├── transport.py         Windows RFCOMM（Winsock）   ← 本项目重写
│   ├── discovery.py         Windows 设备发现            ← 本项目重写
│   ├── messages.py          错误信息中文层              ← 本项目新增
│   └── mock.py              内置模拟设备                ← 本项目新增
├── gui/                     桌面前端（CustomTkinter）
│   ├── app.py               窗口外壳、连接生命周期
│   ├── theme.py             设计令牌与明暗配色
│   ├── widgets.py           复用组件
│   ├── views/               六个页面（连接/声音/模式/设备/高级/关于）
│   ├── worker.py            设备 I/O 的后台串行执行
│   ├── settings.py          %APPDATA%\bosectl-win\settings.json
│   └── resources.py         DPI、任务栏标识、图标
├── build/                   PyInstaller 规格、图标、版本资源
├── scripts/                 版本一致性检查
├── tests/                   测试（含界面冒烟测试）
├── docs/                    架构、构建、使用、移植说明
├── cli.py                   Windows 控制台入口
└── bosectl.py               开发用统一入口（界面或命令行）
```

## 架构

```
   界面 / CLI
       │
   BmapConnection          类型化 API，按型号分发到正确的地址与解析器
       │
   设备配置 (devices/)     纯数据：地址、解析器、构造器、型号差异
       │
   Transport               Windows: Winsock AF_BTH RFCOMM（ctypes）
       │
   Protocol                BMAP 二进制编解码（无 I/O、无设备知识）
       │
   蓝牙 RFCOMM
```

细节见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 排错

| 现象 | 原因与处理 |
| --- | --- |
| "设备正忙" | 上一个连接尚未释放，或手机端 Bose 应用仍占用通道。等 5 秒重试，并在手机上断开耳机。 |
| "设备拒绝连接" | 耳机未配对、未开机，或不在范围内。先在 Windows 蓝牙设置里确认"已连接"。 |
| "连接超时" | 耳机待机休眠。操作一次唤醒，或把"连接超时"调到 12 / 20 秒。 |
| "未找到已配对的 Bose 设备" | 尚未配对，或设备名不含 Bose。改用"手动连接"填写地址与型号。 |
| 扫描列表是空的 | 运行 `bosectl-cli.exe --diagnose`，按报告检查蓝牙适配器与配对状态。 |
| 某型号没有均衡器 / 空间音频 | 该型号硬件不支持（如 QC35 世代）。界面会自动禁用对应控件。 |
| "需要 Bose 云端鉴权" | 该操作（重命名、部分按键重映射）被固件锁定。日常设置不受影响。 |
| 界面模糊 | 程序已开启 per-monitor DPI 感知；若仍模糊，检查系统缩放设置。 |

命令行报错时，`bosectl-cli.exe --diagnose` 的输出是最有用的信息；提交 issue 时请附上它。

## 开发

```bash
pytest tests -q                 # 全量测试
pytest tests -q -k gui          # 只跑界面冒烟测试
pytest tests --integration      # 需要真实耳机已配对
ruff check pybmap gui tests     # 静态检查
python build/make_icon.py       # 重新生成图标
python scripts/check_version.py # 版本一致性
```

界面无法在无显示器环境创建窗口时，冒烟测试会自动跳过而不是失败。

## 版权与归属

本项目是 [aaronsb/bosectl](https://github.com/aaronsb/bosectl)（作者 Aaron Bockelie，MIT 许可）
的 Windows 移植。BMAP 协议的逆向工程成果 —— 协议帧格式、寄存器地址、各型号差异、设备目录 ——
完全来自上游。本项目只改了"字节如何抵达耳机"以及外围界面。

完整文件级归属见 [`NOTICE`](NOTICE)，许可证见 [`LICENSE`](LICENSE)。

Bose、QuietComfort 及相关标识是 Bose Corporation 的商标。本项目与 Bose 无隶属或背书关系。
