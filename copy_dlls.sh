#!/usr/bin/env bash
# Copy Slay the Spire 2 game DLLs into the local runtime lib directory.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  ./copy_dlls.sh [game-data-dir] [--output lib]

Examples:
  ./copy_dlls.sh
  ./copy_dlls.sh "/path/to/Slay the Spire 2/data_sts2_macos_arm64"
  ./copy_dlls.sh "/path/to/Slay the Spire 2/data_sts2_macos_x86_64" --output lib

The output directory defaults to lib/ because the headless project and CLI
resolve sts2.dll from lib/ unless STS2_LIB is set.
EOF
}

GAME_DIR=""
OUTPUT_DIR="lib"

normalize_cli_path() {
    local path="$1"
    if [[ "$path" =~ ^[A-Za-z]:[\\/].* ]]; then
        if command -v cygpath >/dev/null 2>&1; then
            cygpath -u "$path"
            return 0
        fi
        if command -v wslpath >/dev/null 2>&1; then
            wslpath -u "$path"
            return 0
        fi
    fi
    printf '%s\n' "$path"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        -o|--output)
            if [ "$#" -lt 2 ]; then
                echo "ERROR: --output requires a directory." >&2
                exit 1
            fi
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            if [ -n "$GAME_DIR" ]; then
                echo "ERROR: unexpected argument: $1" >&2
                usage >&2
                exit 1
            fi
            GAME_DIR="$1"
            shift
            ;;
    esac
done

if [ -n "$GAME_DIR" ]; then
    GAME_DIR=$(normalize_cli_path "$GAME_DIR")
fi
OUTPUT_DIR=$(normalize_cli_path "$OUTPUT_DIR")

has_sts2_dll() {
    [ -f "$1/sts2.dll" ]
}

find_data_dir_under() {
    local root="$1"
    if [ -d "$root" ]; then
        if has_sts2_dll "$root"; then
            printf '%s\n' "$root"
            return 0
        fi
        local found
        found=$(find "$root" -maxdepth 4 -type f -name sts2.dll -print -quit 2>/dev/null || true)
        if [ -n "$found" ]; then
            dirname "$found"
            return 0
        fi
    fi
    return 1
}

detect_game_dir() {
    local system
    system=$(uname -s)
    local machine
    machine=$(uname -m)
    local candidates=()

    case "$system" in
        Darwin)
            local base="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources"
            if [ "$machine" = "arm64" ] || [ "$machine" = "aarch64" ]; then
                candidates+=("$base/data_sts2_macos_arm64" "$base/data_sts2_macos_x86_64")
            else
                candidates+=("$base/data_sts2_macos_x86_64" "$base/data_sts2_macos_arm64")
            fi
            ;;
        Linux)
            candidates+=(
                "$HOME/.steam/steam/steamapps/common/Slay the Spire 2"
                "$HOME/.local/share/Steam/steamapps/common/Slay the Spire 2"
            )
            ;;
        MINGW*|MSYS*|CYGWIN*)
            candidates+=(
                "C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2"
                "C:/Program Files/Steam/steamapps/common/Slay the Spire 2"
            )
            ;;
    esac

    for candidate in "${candidates[@]}"; do
        if find_data_dir_under "$candidate"; then
            return 0
        fi
    done
    return 1
}

if [ -z "$GAME_DIR" ]; then
    if ! GAME_DIR=$(detect_game_dir); then
        echo "ERROR: could not locate a Slay the Spire 2 data directory with sts2.dll." >&2
        echo "Pass the game data directory explicitly, for example:" >&2
        echo "  ./copy_dlls.sh \"/path/to/data_sts2_macos_arm64\"" >&2
        exit 1
    fi
else
    if ! GAME_DIR=$(find_data_dir_under "$GAME_DIR"); then
        echo "ERROR: sts2.dll was not found under the provided directory." >&2
        exit 1
    fi
fi

echo "Game data directory: $GAME_DIR"
echo "Output directory: $OUTPUT_DIR"

mkdir -p "$OUTPUT_DIR"

if [ -f "$OUTPUT_DIR/sts2.dll" ] && [ ! -f "$OUTPUT_DIR/sts2.dll.original" ]; then
    cp "$OUTPUT_DIR/sts2.dll" "$OUTPUT_DIR/sts2.dll.original"
    echo "Backed up existing sts2.dll to $OUTPUT_DIR/sts2.dll.original"
fi

DLLS=(
    "sts2.dll"
    "SmartFormat.dll"
    "SmartFormat.ZString.dll"
    "Sentry.dll"
    "Steamworks.NET.dll"
    "MonoMod.Backports.dll"
    "MonoMod.ILHelpers.dll"
    "0Harmony.dll"
    "System.IO.Hashing.dll"
)

missing=()
echo "Copying DLLs..."
for dll in "${DLLS[@]}"; do
    src="$GAME_DIR/$dll"
    if [ ! -f "$src" ]; then
        src=$(find "$GAME_DIR" -name "$dll" -print -quit 2>/dev/null || true)
    fi

    if [ -n "$src" ] && [ -f "$src" ]; then
        cp "$src" "$OUTPUT_DIR/$dll"
        echo "  copied $dll"
    else
        missing+=("$dll")
        echo "  missing $dll"
    fi
done

if [ "${#missing[@]}" -gt 0 ]; then
    echo "ERROR: missing required DLLs: ${missing[*]}" >&2
    exit 1
fi

echo "DLL copy complete."
