# Cross-Platform Usage

This guide explains how to prepare `sts2-cli` on another machine when the game
files are installed locally through Steam. The CLI still runs the original Slay
the Spire 2 engine; this document only covers copying the required local game
DLLs into the runtime directory that the headless adapter already uses.

## Requirements

- A purchased Steam installation of Slay the Spire 2 on the machine used to
  extract the game files.
- A checkout of this repository.
- .NET 9 SDK or newer on the machine that will run the CLI.
- Game DLLs that match the CPU architecture of the runtime process.

Do not commit or redistribute game DLLs. The `lib/` directory is ignored by Git
and should remain local to your machine or private server.

## Architecture

The managed game assemblies must be compatible with the machine that runs the
headless process.

| Runtime machine | Recommended game data directory |
| --- | --- |
| `x86_64` / `amd64` | `data_sts2_macos_x86_64` or Windows x86_64 data |
| `aarch64` / `arm64` | `data_sts2_macos_arm64` |

Check a Linux server with:

```bash
uname -m
```

If the architecture is wrong, .NET will fail to load `sts2.dll`.

## Copy Game DLLs

From the repository root, run:

```bash
./copy_dlls.sh
```

The script auto-detects common Steam install locations on macOS, Linux, and
Git Bash style Windows shells. It copies DLLs to `lib/` by default because the
headless project and Python CLI resolve `sts2.dll` from `lib/` unless `STS2_LIB`
is set.

You can pass the data directory explicitly:

```bash
./copy_dlls.sh "/path/to/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"
```

Or choose a different output directory:

```bash
./copy_dlls.sh "/path/to/game/data" --output /private/sts2-lib
```

When using a custom output directory, set both runtime variables before starting
the headless process:

```bash
export STS2_LIB=/private/sts2-lib
export STS2_GAME_DIR=/private/sts2-lib
```

## Run The CLI

On Unix-like systems:

```bash
python3 python/play.py
```

On Windows from the repository root, use the launcher:

```cmd
.\sts2-cli.bat
```

PowerShell requires the `.\` prefix for commands in the current directory. Use
`.\sts2-cli-zh.bat` for the Chinese launcher, or `.\setup-windows.bat` when you
only want to copy/build prerequisites without starting a run.

The first run builds the headless adapter if needed. If you used the default
`lib/` output directory, no additional environment variables are required.

## Server Upload

If you copy DLLs on one machine and run the CLI on a private Linux server,
upload the contents of `lib/` to the server checkout:

```bash
rsync -av lib/ user@server:/path/to/sts2-cli/lib/
```

Verify the files on the server:

```bash
ls -lh /path/to/sts2-cli/lib
```

## Troubleshooting

### Assembly Architecture Mismatch

If .NET reports that an assembly architecture is incompatible with the current
process, replace the copied DLLs with files from a game data directory that
matches the server CPU architecture.

### Missing DLLs

`copy_dlls.sh` fails if any required DLL cannot be found. Pass the exact game
data directory if auto-detection found the wrong Steam path.

### Simulator Does Not Start

Run the headless project directly to see the raw exception:

```bash
printf '{"cmd":"start_run","character":"Ironclad","seed":"test","ascension":0}\n{"cmd":"quit"}\n' \
  | STS2_LIB=/path/to/sts2-cli/lib \
    STS2_GAME_DIR=/path/to/sts2-cli/lib \
    dotnet run --project src/Sts2Headless/Sts2Headless.csproj
```

If the error still points to assembly loading, re-check the copied DLLs and
architecture match.
