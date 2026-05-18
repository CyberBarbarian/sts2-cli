#!/bin/bash
# copy_dlls.sh — Copy game DLLs from macOS x86_64 Steam data to lib_x86/
#
# Usage:
#   ./copy_dlls.sh                    # Use default macOS x86_64 Steam data path
#   ./copy_dlls.sh /path/to/game/data # Manual x86_64 data directory

set -e

DLL_SOURCE_DIR="$1"

if [ -z "$DLL_SOURCE_DIR" ]; then
    DLL_SOURCE_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_x86_64"
fi

if [ ! -d "$DLL_SOURCE_DIR" ]; then
    echo "❌ DLL source directory not found: $DLL_SOURCE_DIR"
    echo ""
    echo "Usage: ./copy_dlls.sh /path/to/game/data_sts2_macos_x86_64"
    exit 1
fi

echo "📁 DLL source directory: $DLL_SOURCE_DIR"

mkdir -p lib_x86

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

echo ""
echo "📦 Copying DLLs to lib_x86/..."
for dll in "${DLLS[@]}"; do
    src="$DLL_SOURCE_DIR/$dll"
    if [ -f "$src" ]; then
        cp "$src" "lib_x86/$dll"
        echo "  ✓ $dll"
    else
        echo "  ✗ $dll not found at $src"
        # Try searching subdirectories
        found=$(find "$DLL_SOURCE_DIR" -name "$dll" -print -quit 2>/dev/null)
        if [ -n "$found" ]; then
            cp "$found" "lib_x86/$dll"
            echo "    → found at $found"
        else
            echo "    ⚠ Skipped (may cause build errors)"
        fi
    fi
done

echo ""
echo "✅ DLL copy complete!"
