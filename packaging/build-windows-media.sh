#!/usr/bin/env bash
set -euo pipefail

# Build on Ubuntu with gcc-mingw-w64-x86-64-win32,
# g++-mingw-w64-x86-64-win32, make, nasm, curl, xz-utils, and zip.
ffmpeg_version=8.1.3
untrunc_commit=87a5d9202ae48495b9aa6b5880649dbdf32c82d0
out=$(realpath -m "${1:?Specify an output directory}")
recipe=$(realpath "$0")
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$out/vendor/media" "$out/licenses" "$work/sources"
cd "$work/sources"

ffmpeg_archive="ffmpeg-$ffmpeg_version.tar.xz"
untrunc_archive="untrunc-$untrunc_commit.tar.gz"
curl -fsSL --retry 3 "https://ffmpeg.org/releases/$ffmpeg_archive" -o "$ffmpeg_archive"
echo "7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3  $ffmpeg_archive" | sha256sum --check
curl -fsSL --retry 3 "https://codeload.github.com/anthwlock/untrunc/tar.gz/$untrunc_commit" -o "$untrunc_archive"
cp "$recipe" .
file_list=("$ffmpeg_archive" "$untrunc_archive" "$(basename "$recipe")")
(
    for source_archive in "$ffmpeg_archive" "$untrunc_archive"; do
        tar -xf "$source_archive" -C "$work"
    done
    cd "$work/ffmpeg-$ffmpeg_version"
    ./configure --arch=x86_64 --target-os=mingw32 --cross-prefix=x86_64-w64-mingw32- \
        --cc=x86_64-w64-mingw32-gcc-win32 --enable-cross-compile --enable-w32threads \
        --enable-shared --disable-static --disable-autodetect --disable-network \
        --disable-doc --disable-debug --disable-ffplay --disable-avdevice \
        --disable-encoders --enable-encoder=aac,pcm_s16le,wrapped_avframe \
        --prefix="$work/installed"
    make -j"$(nproc)"
    make install
    cp COPYING.LGPLv2.1 "$out/licenses/FFmpeg-LGPL-2.1.txt"
)

(
    cd "$work/untrunc-$untrunc_commit"
    x86_64-w64-mingw32-g++-win32 -std=c++17 -D_FILE_OFFSET_BITS=64 \
        "-DUNTR_VERSION=\"${untrunc_commit:0:12}\"" -O2 -static-libgcc -static-libstdc++ -s \
        -isystem "$work/installed/include" src/*.cpp src/avc1/*.cpp src/hvc1/*.cpp \
        -L"$work/installed/lib" -lavformat -lavcodec -lavutil -o "$out/vendor/media/untrunc.exe"
    cp COPYING "$out/licenses/Untrunc-GPL-2.0.txt"
)
cp "$work/installed/bin/ffmpeg.exe" "$work/installed/bin/ffprobe.exe" "$work/installed/bin/"*.dll "$out/vendor/media/"
(
    x86_64-w64-mingw32-gcc-win32 --version
    x86_64-w64-mingw32-g++-win32 --version
    sha256sum "$ffmpeg_archive" "$untrunc_archive"
) > BUILD-INFO.txt
zip -q "$out/Media-Tools-Corresponding-Source.zip" "${file_list[@]}" BUILD-INFO.txt
