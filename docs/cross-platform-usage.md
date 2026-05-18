# 跨平台使用指南

本文档说明如何在本地 macOS 或 Windows 安装《Slay the Spire 2》，提取对应架构的游戏 DLL，并上传到 Linux 服务器运行 `sts2-cli`。

## 前置条件

- 本地 macOS 或 Windows 已通过 Steam 购买并安装《Slay the Spire 2》。
- Linux 服务器已准备好本仓库代码。
- Linux 服务器已安装 .NET 9 SDK 或更高版本。
- 本地提取的 DLL 架构必须和 Linux 服务器的 CPU 架构一致。
- DLL 来自游戏安装目录，不能提交、上传或同步到 GitHub 等代码仓库。

常见对应关系：

| Linux 服务器架构 | 应提取的游戏数据目录 |
| --- | --- |
| `x86_64` / `amd64` | macOS: `data_sts2_macos_x86_64`；Windows: `data_sts2_windows_x86_64` |
| `aarch64` / `arm64` | macOS: `data_sts2_macos_arm64` |

Windows 版游戏目前通常只提供 x86_64 DLL，因此适合给 `x86_64` / `amd64` Linux 服务器提取 DLL。如果目标服务器是 ARM64，请优先从 macOS ARM64 游戏目录提取。

可以在 Linux 服务器上用下面的命令确认架构：

```bash
uname -m
```

## 1. 在本地提取 DLL

### macOS

先进入本地的 `sts2-cli` 仓库目录，然后使用快捷脚本复制 DLL：

```bash
cd /path/to/sts2-cli
./copy_dlls.sh
```

`copy_dlls.sh` 默认会从 macOS x86_64 版本游戏目录复制 DLL：

```text
~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_x86_64
```

如果需要手动指定游戏数据目录，可以传入目录路径：

```bash
./copy_dlls.sh "/path/to/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_x86_64"
```

如果目标服务器是 ARM64，则应改用 ARM64 游戏数据目录：

```bash
./copy_dlls.sh "$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"
```

### Windows

如果本地是在 Windows 上安装游戏，可以从 Steam 游戏目录中提取 x86_64 DLL。常见路径类似：

```text
C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2\data_sts2_windows_x86_64
```

Windows 版 DLL 通常只有 x86_64 版本，因此只适合上传到 x86_64/amd64 的 Linux 服务器使用。不要把 Windows x86_64 DLL 上传给 ARM64 Linux 服务器使用。

脚本会把 DLL 复制到本地仓库的 `lib_x86/` 目录。需要上传的文件包括：

```text
sts2.dll
SmartFormat.dll
SmartFormat.ZString.dll
Sentry.dll
Steamworks.NET.dll
MonoMod.Backports.dll
MonoMod.ILHelpers.dll
0Harmony.dll
System.IO.Hashing.dll
```

## 2. 版权和分发注意事项

这些 DLL 来自 Steam 游戏安装目录，属于《Slay the Spire 2》游戏文件。使用前请先购买并安装正版游戏。

不要将 DLL 提交到 GitHub 或其他代码仓库，也不要通过公开渠道分发 DLL。推荐只在自己的本地机器和服务器之间传输，并确保 `lib/`、`lib_x86/` 等目录不会被 Git 跟踪。

## 3. 上传 DLL 到 Linux 服务器

将本地复制好的 DLL 上传到服务器仓库的 `lib/` 目录：

```bash
scp lib_x86/*.dll root@your-server:/root/autodl-tmp/sts2-cli/lib/
```

如果服务器上的 `lib/` 目录不存在，先创建：

```bash
mkdir -p /root/autodl-tmp/sts2-cli/lib
```

上传后可以检查文件是否齐全：

```bash
ls -lh /root/autodl-tmp/sts2-cli/lib
```

## 4. 在 Linux 服务器安装 .NET

如果服务器还没有 .NET SDK，可以安装 .NET 9 SDK。Ubuntu 22.04 示例：

```bash
cd /tmp
wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
dpkg -i packages-microsoft-prod.deb
rm packages-microsoft-prod.deb

apt-get update
apt-get install -y dotnet-sdk-9.0
```

验证安装：

```bash
dotnet --version
```

## 5. 运行游戏

进入服务器上的仓库目录：

```bash
cd /root/autodl-tmp/sts2-cli
```

启动中文交互模式：

```bash
python3 ./python/play.py --lang zh
```

英文模式：

```bash
python3 ./python/play.py
```

第一次运行时项目会自动构建。如果 `lib/` 中的 DLL 架构正确，构建完成后即可在终端中游玩。

## 常见问题

### The assembly architecture is not compatible

如果出现类似错误：

```text
The assembly architecture is not compatible with the current process architecture.
```

说明 `lib/sts2.dll` 的 CPU 架构和服务器不一致。例如，`linux-x64` 服务器不能加载 `macos_arm64` 的 `sts2.dll`。

解决方法是重新从匹配架构的游戏数据目录提取 DLL，并覆盖上传到服务器的 `lib/` 目录。

### Failed to start simulator

如果只看到：

```text
Failed to start simulator
```

可以直接运行 headless 项目查看原始异常：

```bash
cd /root/autodl-tmp/sts2-cli
printf '{"cmd":"start_run","character":"Ironclad","seed":"test","ascension":0}\n{"cmd":"quit"}\n' \
  | STS2_GAME_DIR=/root/autodl-tmp/sts2-cli/lib \
    STS2_LIB=/root/autodl-tmp/sts2-cli/lib \
    dotnet run --project src/Sts2Headless/Sts2Headless.csproj
```

如果异常仍然指向架构不兼容，继续按上面的架构对应关系重新提取 DLL。
