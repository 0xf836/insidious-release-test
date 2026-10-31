#!/usr/bin/env bash
# Run in a fresh disposable container with check.sh output at /input.
set -euo pipefail
[[ -f /.dockerenv ]] || { printf 'Run in a disposable Docker container only\n' >&2; exit 2; }
distribution=${1:?Expected arch or fedora}
previous=${2:---clean-install}
export LC_ALL=C.UTF-8
mkdir -p /results /work
[[ ! -e /results/runtime.json ]]
exec > >(tee /results/runtime-check.log) 2>&1
date -u +%Y-%m-%dT%H:%M:%SZ > /results/started-at.txt
cp /etc/os-release /results/os-release
source /src/tools/packaging/assertions.sh
source /etc/os-release
case "$distribution" in
    arch)
        [[ "$ID" == arch ]]
        pacman -Syu --noconfirm --needed python desktop-file-utils appstream xorg-server-xvfb xorg-xauth weston
        ;;
    fedora)
        [[ "$ID" == fedora && "$VERSION_ID" == 44 ]]
        dnf -y --disable-repo=fedora-cisco-openh264 --setopt=install_weak_deps=False upgrade --refresh
        dnf -y --disable-repo=fedora-cisco-openh264 --setopt=install_weak_deps=False install python3 desktop-file-utils appstream xorg-x11-server-Xvfb xorg-x11-xauth weston
        ;;
    *) exit 2 ;;
esac
# Do not mask undeclared runtime requirements with build dependencies.
for command in c++ cmake ninja; do
    if command -v "$command"; then
        printf 'Build tool unexpectedly present: %s\n' "$command" >&2
        exit 1
    fi
done
package=$(python3 /src/tools/packaging/evidence.py verify "$distribution" /input)
install_package() {
    case "$distribution" in
        arch) pacman -U --noconfirm "$1" ;;
        fedora) dnf -y --disable-repo=fedora-cisco-openh264 --setopt=install_weak_deps=False install "$1" ;;
    esac
}
mkdir -p /work/config/Insidious /work/cache /work/data
export XDG_CONFIG_HOME=/work/config XDG_CACHE_HOME=/work/cache XDG_DATA_HOME=/work/data
printf '[General]\npackageRemovalSentinel=true\n' > /work/config/Insidious/Insidious.conf
if [[ "$previous" == --first-package || "$previous" == --clean-install ]]; then
    upgrade_status=not-run
    [[ "$previous" != --first-package ]] || upgrade_status=not-applicable-first-package
else
    [[ "$previous" == /previous/* && -f "$previous" ]]
    case "$distribution" in
        arch) [[ "$(pacman -Qpq "$previous")" == insidious ]] ;;
        fedora) [[ "$(rpm -qp --qf '%{NAME}' "$previous")" == insidious ]] ;;
    esac
    install_package "$previous"
    insidious --version > /results/previous-version.txt
    python3 /src/tools/packaging/evidence.py previous "$distribution" /input /results/previous-version.txt
    upgrade_status=passed
fi
install_package "/input/$package"
grep -qx 'packageRemovalSentinel=true' /work/config/Insidious/Insidious.conf
case "$distribution" in
    arch)
        pacman -Ql insidious > /results/installed-files.txt
        pacman -Q > /results/packages.txt
        ;;
    fedora)
        rpm -ql insidious > /results/installed-files.txt
        rpm -qa | sort > /results/packages.txt
        ;;
esac
# Reject accidentally packaged developer tools, tests or private libraries.
reject_matches '/(bin/insidious_.*|lib(64)?/.*\.so|[^ ]*/CMakeFiles/|[^ ]*/tools/|[^ ]*/tests/)' /results/installed-files.txt
# Installed resources and runtime dependencies, rather than build-tree resources.
ldd /usr/bin/insidious > /results/ldd.txt
reject_matches 'not found' /results/ldd.txt
insidious --version | tee /results/version.txt
desktop-file-validate /usr/share/applications/io.github._0xf836.Insidious.desktop
appstreamcli validate --no-net /usr/share/metainfo/io.github._0xf836.Insidious.metainfo.xml
cp /usr/share/icons/hicolor/128x128/apps/io.github._0xf836.Insidious.png '/work/image spaces ü.png'
set +e
QT_QPA_PLATFORM=xcb xvfb-run -a timeout 5 insidious '/work/image spaces ü.png' > /results/launch.log 2>&1
status=$?
set -e
[[ "$status" == 124 ]]
reject_matches 'could not connect|could not load.*(platform|xcb|wayland)|no Qt platform|error while loading shared libraries|symbol lookup error' /results/launch.log
# Native Wayland startup without an X server or GPU.
export XDG_RUNTIME_DIR=/work/runtime WAYLAND_DISPLAY=insidious-test
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
weston --backend=headless --renderer=pixman --socket="$WAYLAND_DISPLAY" \
    --idle-time=0 --no-config --log=/results/weston.log &
weston_pid=$!
trap 'kill "$weston_pid" 2>/dev/null || true' EXIT
for attempt in {1..50}; do
    [[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]] && break
    sleep 0.1
done
[[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]]
set +e
QT_QPA_PLATFORM=wayland timeout 5 insidious '/work/image spaces ü.png' > /results/wayland-launch.log 2>&1
status=$?
set -e
[[ "$status" == 124 ]]
reject_matches 'could not connect|failed to create.*display|no Qt platform|error while loading shared libraries|symbol lookup error' /results/wayland-launch.log
kill "$weston_pid"
wait "$weston_pid" || true
trap - EXIT
# Opening an image must not create history, cache or log files.
[[ -z "$(find /work/cache /work/data -type f -print -quit)" ]]
# Removal must preserve the settings created before package installation.
case "$1" in
    arch) pacman -R --noconfirm insidious ;;
    fedora) rpm -e insidious ;;
esac
[[ ! -e /usr/bin/insidious ]]
[[ ! -e /usr/share/applications/io.github._0xf836.Insidious.desktop ]]
[[ ! -e /usr/share/metainfo/io.github._0xf836.Insidious.metainfo.xml ]]
[[ ! -e /usr/share/doc/insidious ]]
[[ ! -e /usr/share/licenses/insidious ]]
for icon in /usr/share/icons/hicolor/*/apps/io.github._0xf836.Insidious.*; do
    [[ ! -e "$icon" ]]
done
grep -qx 'packageRemovalSentinel=true' /work/config/Insidious/Insidious.conf
python3 /src/tools/packaging/evidence.py runtime "$distribution" /input /results/version.txt /results/runtime.json "$upgrade_status"
printf 'Package installation, X11/Wayland startup and removal checks passed\n'
