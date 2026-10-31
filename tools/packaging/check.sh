#!/usr/bin/env bash
# Run only inside a disposable target container. /input contains prepare.py output.
set -euo pipefail
[[ -f /.dockerenv ]] || { printf 'Run in a disposable Docker container only\n' >&2; exit 2; }
export LC_ALL=C.UTF-8
export CMAKE_BUILD_PARALLEL_LEVEL=2
mkdir -p /results /work
[[ ! -e /results/build.json ]]
exec > >(tee /results/package-check.log) 2>&1
date -u +%Y-%m-%dT%H:%M:%SZ > /results/started-at.txt
cp /etc/os-release /results/os-release
(cd /input && sha256sum -c SHA256SUMS)
source /src/tools/packaging/assertions.sh
source /etc/os-release
case "${1:?Expected arch or fedora}" in
    arch)
        [[ "$ID" == arch ]]
        pacman -Syu --noconfirm --needed base-devel cmake ninja pkgconf git zip python qt6-base libvips imagemagick libarchive desktop-file-utils appstream
        id builder >/dev/null 2>&1 || useradd --create-home builder
        cp /input/PKGBUILD /work/
        cp /input/insidious-*.tar.xz /work/
        # The release URL may not exist yet. A missing cached archive must fail,
        # never fall back to downloading a different source during qualification.
        cp /etc/makepkg.conf /work/makepkg.conf
        printf '\nDLAGENTS=(\x27https::/usr/bin/false\x27 \x27http::/usr/bin/false\x27)\n' >> /work/makepkg.conf
        chown -R builder:builder /work
        cd /work
        runuser -u builder -- env SRCDEST=/work MAKEFLAGS=-j2 makepkg --config /work/makepkg.conf --noconfirm --cleanbuild --force
        cp insidious-*.pkg.tar.zst /results/
        package=(/results/insidious-*.pkg.tar.zst)
        pacman -Q > /results/packages.txt
        ;;
    fedora)
        [[ "$ID" == fedora && "$VERSION_ID" == 44 ]]
        dnf -y --disable-repo=fedora-cisco-openh264 --setopt=install_weak_deps=False upgrade --refresh
        dnf -y --disable-repo=fedora-cisco-openh264 --setopt=install_weak_deps=False install gcc-c++ cmake ninja-build git-core zip python3 qt6-qtbase-devel vips-devel vips-magick libarchive-devel desktop-file-utils appstream rpm-build
        mkdir -p /work/rpmbuild/{SOURCES,SPECS}
        cp /input/insidious-*.tar.xz /work/rpmbuild/SOURCES/
        cp /input/insidious.spec /work/rpmbuild/SPECS/
        rpmbuild -ba --define '_topdir /work/rpmbuild' --define '_smp_mflags -j2' /work/rpmbuild/SPECS/insidious.spec
        copy_rpms /work/rpmbuild /results
        package=(/results/insidious-[0-9]*.x86_64.rpm)
        rpm -qa | sort > /results/packages.txt
        ;;
    *) exit 2 ;;
esac
[[ "${#package[@]}" == 1 && -f "${package[0]}" ]]
source_archive=(/input/insidious-*.tar.xz)
[[ "${#source_archive[@]}" == 1 && -f "${source_archive[0]}" ]]
python3 /src/tools/packaging/evidence.py build "$1" "${source_archive[0]}" "${package[0]}" /results/build.json
printf 'Package build and regression tests passed; runtime check requires a fresh container\n'
