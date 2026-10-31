# Native Packaging

Arch and Fedora recipes consume the same canonical `insidious-X.Y.Z.tar.xz`
source archive. Versions come from its `version.txt`; source identity follows the
[archive metadata contract](releasing.md#source-archive-metadata-contract).
Native packages use system Qt, libvips, ImageMagick loader and libarchive.
X11 startup uses Qt's `xcb` platform plugin; native Wayland startup uses its
`wayland` plugin. On the current targets, these plugins ship in
[Arch qt6-base](https://archlinux.org/packages/extra/x86_64/qt6-base/files/) and
[Fedora qt6-qtbase-gui](https://packages.fedoraproject.org/pkgs/qt6-qtbase/qt6-qtbase-gui/fedora-44.html).
A separate Qt Wayland module is not required by the viewer. Recheck plugin
packaging when qualifying a different distribution or older Qt version.
Debian/Ubuntu recipes remain deferred while those targets are excluded or blocked
in the [platform matrix](../packaging/platforms.json).

## Prepare recipes

Obtain a trusted source archive and verify its release checksums/provenance before
preparing packages. From the source checkout or extracted source tree:

```sh
python3 tools/packaging/prepare.py \
  --source downloads/insidious-0.1.0.tar.xz \
  --output .ci-results/native
```

The output directory must not exist. Preparation validates archive paths, numeric
version agreement and source metadata, then writes `PKGBUILD`, `insidious.spec`,
a copy of the source archive and `SHA256SUMS`. The Arch recipe includes the actual
SHA-256 and final public release URL. These checks establish internal consistency,
not authenticity: source metadata alone cannot prove that an archive is official.
Source creation and publication use the [release automation](releasing.md#implemented-automation).
`--repository OWNER/REPOSITORY` overrides the recipe's public source repository
for an isolated release trial; production defaults to the project repository.

## Arch

Use a clean Arch environment and run makepkg as an ordinary user:

```sh
cd .ci-results/native
sha256sum -c SHA256SUMS
SRCDEST="$PWD" makepkg -s --cleanbuild
```

Seeding `SRCDEST` allows pre-publication builds without downloading an unpublished
asset. Makepkg still verifies the checksum in the rendered recipe. The stable
`insidious` package conflicts with the root recipe's `insidious-git`; both use
shared CMake installation rules. See the [Arch guide](arch-linux.md) for the VCS
workflow.

The automated qualification runner additionally disables HTTP(S) source download
agents, so a missing cached source cannot fall back to the public release URL.

## Fedora

Use a clean Fedora 44 environment with the spec's build requirements installed:

```sh
cd .ci-results/native
sha256sum -c SHA256SUMS
mkdir -p rpm-build/SOURCES rpm-build/SPECS
cp insidious-*.tar.xz rpm-build/SOURCES/
cp insidious.spec rpm-build/SPECS/
rpmbuild -ba --define "_topdir $PWD/rpm-build" rpm-build/SPECS/insidious.spec
```

RPM generates shared-library requirements; explicit Qt/libvips minimums and the
`vips-magick` runtime dependency retain the application requirements. `-ba`
produces binary and source RPMs. No package maintainer script fetches libraries,
changes user settings or assigns default file associations.

## Package checks

Package qualification uses two fresh disposable containers per target. Run these
checks for packaging changes and releases through the reusable package workflow;
other PRs retain build-only jobs. Do not add another full build or CTest pass on top of
the native recipe's build and tests.

`tools/packaging/check.sh` installs distribution build dependencies, builds the
native package and runs CTest once through its recipe. It retains the binary
package, Fedora source/debug packages, resolved package inventory and build log.
`build.json` binds the tested binary package's SHA-256 to the source archive's
version, commit and SHA-256. Use the pinned image from the platform matrix:

```sh
mkdir -p .ci-results/package-arch
docker run --rm --platform linux/amd64 \
  -v "$PWD/.ci-results/native:/input:ro" \
  -v "$PWD:/src:ro" \
  -v "$PWD/.ci-results/package-arch:/results" \
  IMAGE bash /src/tools/packaging/check.sh arch
```

`tools/packaging/runtime.sh` consumes that output in a new container, verifies the
package digest, and installs the package through the native package manager. It
installs only validation/display tools beforehand and rejects an environment
containing a compiler, CMake or Ninja. Runtime dependencies must come from the
package's requirements. It checks library resolution, installed contents and
desktop metadata, exercises X11 and headless Wayland startup with a space/Unicode
image path, and removes the package while preserving pre-existing user settings.
It does not compile or run CTest.

```sh
mkdir -p .ci-results/runtime-arch
docker run --rm --platform linux/amd64 \
  -v "$PWD/.ci-results/package-arch:/input:ro" \
  -v "$PWD:/src:ro" \
  -v "$PWD/.ci-results/runtime-arch:/results" \
  IMAGE bash /src/tools/packaging/runtime.sh arch --first-package
```

Run a clean installation for every version using `--clean-install` (the default).
`--first-package` performs the same clean check and explicitly records that no
preceding package exists. When a previous package is available, additionally run
a separate fresh container with its own output directory, mount the previous
package directory read-only at `/previous`, and pass `/previous/PACKAGE`. The
runner installs the previous package first, requires an older numeric application
version, then installs the new package and checks
settings preservation. Reinstalling the same version does not count as an upgrade.

Use `fedora` and separate output directories for Fedora. Build input includes
the prepared recipes, source archive and `SHA256SUMS`; runtime input includes
`build.json` and its binary package. Use empty output directories. A successful
runtime pass writes `runtime.json` with the source/package identity, check outcomes
and installation mode/upgrade outcome; failed runs produce logs without a success
report.
An upgrade report cannot replace the mandatory clean-install report. These
reports record local checks, not source authenticity or release publication.
Keep raw results in the explicit output directories rather than documentation.
Python 3, native packaging tools, desktop-file-utils, AppStream, Xvfb and Weston
are developer/validation tools, not application runtime dependencies.

Native qualification uses automated package checks and X11/Wayland startup
checks, plus upgrade from the preceding package when available. Viewer behavior
is covered by the existing regression suite. Manual menu/Open With or interactive
UI acceptance is not required for platform qualification or releases. Keep
`native_qualified` false until the applicable automated package gates pass.
Release readiness also requires release automation and publication validation.
See [release acceptance](releasing.md#delivery-stages-and-acceptance).
