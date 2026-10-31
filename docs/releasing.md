# Versioning, Releases, and Linux Distribution

**Status: Dependency requirements, version identity, CI, desktop integration, Arch/Fedora package qualification and release automation are implemented. The simplified publication workflow requires a fresh hosted trial before production enablement. Production repository setup and the first production release remain pending.**

This is the canonical specification for version identity, release publication and Linux distribution. [Continuous integration](ci.md) documents the current build workflows. Implement the remaining delivery stages separately.

## Goals and current baseline

Provide a predictable maintainer workflow and complete, clearly labelled downloads: merge ordinary changes, review a generated release PR, merge it, and let CI publish the tested release. Native packages must use distribution-provided libraries. Preserve the application's privacy contract and existing rendering capabilities.

The current baseline is:

- `version.txt` declares version `0.1.0`; CMake reads it before `project()`. The dependency requirements are Qt >= 6.6 and vips-cpp >= 8.18.3. The [dependency audit](dependency-audit.md) records the implemented requirement correction and Ubuntu 26.04 experiments; first production publication remains pending.
- `src/app/main.cpp` exposes generated build identity through `--version`, `-v` and Qt application metadata. About displays the same identity. The early version path does not initialize Qt or libvips and does not require a display.
- The root `PKGBUILD` builds `insidious-git` from Git and installs through CMake.
- Validation, package and release workflows are implemented. Inspect remote tags and GitHub Releases before bootstrapping a repository; workflow files alone do not configure repository policy or authorize a production release.
- CMake installs the binary, desktop entry, icons, AppStream metadata, documentation and license. [Native packaging](packaging.md) describes Arch/Fedora recipe preparation.

Current behavior remains documented in [Current implementation](implementation.md) and [Arch Linux package](arch-linux.md). The decisions behind this design are recorded in [ADR-020 through ADR-022](decisions.md#adr-020-release-prs-control-versioning-and-publication).

## Version policy

### One application version

Root `version.txt` contains one numeric `MAJOR.MINOR.PATCH` version and a trailing newline. CMake validates it before `project(VERSION ...)`; leading zeroes, suffixes, missing newline and extra lines are rejected. The Arch VCS recipe reads and validates this file too. Stable recipes consume the archive's version rather than maintain independent application versions. Release-please uses its `simple` strategy to update this file and `CHANGELOG.md`.

The release-please manifest is automation state, not a second manually maintained version source. CI checks that its root package version agrees with `version.txt` in release PRs and release commits. The release tag must equal `v` followed by that version.

| Identity | Example | Meaning |
| --- | --- | --- |
| Application version | `0.2.0` | Product release identity |
| Git tag | `v0.2.0` | Immutable release commit |
| Arch package version/revision | `0.2.0-1` | Upstream version plus `pkgrel` |
| Debian package version | `0.2.0-1+deb13` | Upstream version plus target-specific packaging revision |
| Ubuntu package version | `0.2.0-1+ubuntu24.04` | Separate build for a qualified Ubuntu target |
| RPM version/release | `0.2.0`, `1%{?dist}` | Upstream version plus distribution release suffix |

These package examples describe naming, not confirmed platform support. Development VCS package versions remain distinct from stable package versions. The existing VCS recipe reads `version.txt` and retains its `.r<count>.g<sha>` suffix.

The shared CMake metadata module generates `build_version.h` for the executable; the bootstrap sets Qt application version from that same value. A build-time target checks identity on every build and only rewrites the header when its contents change. It considers tracked, staged and untracked non-ignored files; ignored build output does not mark a checkout dirty. It uses a 12-character commit abbreviation and recognizes both lightweight and annotated matching tags. A Git-less source directory never inherits a parent checkout. Display rules:

- Clean checkout at the matching release tag, or an official source archive: `Insidious 0.2.0`.
- Other Git checkout: `Insidious 0.2.0-dev+g<short-sha>`.
- Modified Git checkout: append `.dirty` to the development identity, including when HEAD has a release tag.
- Export without Git or official archive metadata: use `0.2.0-dev+unknown`, never imply a verified release.

Release builds require clean sources and explicit validation of version, tag, and commit. An official source archive includes generated source metadata with version and full commit SHA; that metadata must agree with `version.txt`. Do not embed local absolute paths, usernames, or build timestamps in the displayed version. Keep build environment details in CI artifacts.

Headless `--version`/`-v` behavior is preserved. `Help -> About Insidious` and the normal/fullscreen compact menus share one action. The localizable dialog displays the same version, MIT license and project link, with keyboard access to the link and version selection. Opening it performs no network request; clicking the link explicitly opens the browser. Qt organization/application names and the settings schema are unchanged.

### Source archive metadata contract

A Git-less official source archive carries root `source-metadata.json` with string fields `version` and `commit`. The version must match `version.txt`; the commit must be a full 40-character lowercase SHA-1. Malformed JSON, mismatches and invalid commit identifiers fail configuration/build metadata generation. Without this file, a Git-less export identifies as `-dev+unknown`. In a Git checkout, Git state takes precedence over archive metadata.

To prepare metadata alone from a clean checkout at the matching release tag, invoke:

```sh
cmake -DSOURCE_DIR=/path/to/clean/release-checkout \
  -DOUTPUT_FILE=/path/to/staging/source-metadata.json \
  -P cmake/WriteSourceMetadata.cmake
```

Run from the project root. The helper refuses dirty/untagged sources and existing output files; keep staging outside the source checkout. The release source tool generates the same metadata contract directly inside the canonical archive and verifies tag/SHA/source identity. This metadata is an identity record, not an authenticity proof or archive integrity check. Published downloads include SHA-256 checksums.

Git is optional for building an unidentified source export, but is required for checkout identity and the isolated version tests. Those tests also use Bash (already required by the Arch recipe) to verify `pkgver()`. No new application runtime dependency is introduced.

### Semantic versioning and compatibility

Use SemVer with a documented application contract: command-line behavior, settings compatibility, supported opening workflows, and minimum supported platforms/dependencies. Internal C++ implementation details are not a public library ABI.

| Commit classification | Version effect |
| --- | --- |
| `fix:` | PATCH |
| `feat:` | MINOR |
| `!` or `BREAKING CHANGE:` | MINOR before 1.0; MAJOR from 1.0 onward |
| `docs:`, `test:`, `ci:`, `chore:` alone | No release by default |

Configure `bump-minor-pre-major=true` and `bump-patch-for-minor-pre-major=false`. A higher minimum OS/library requirement is a breaking compatibility change. Settings changes require explicit migration/compatibility documentation; a version bump does not itself provide a migration.

Use one ordinary release channel initially. Version `0.x` communicates pre-1.0 maturity but does not automatically make each GitHub release a prerelease. Do not introduce nightly releases, RC automation, moving version tags, or parallel maintenance branches in this stage. The transition to 1.0 is an explicit maintainer decision about the compatibility contract.

### Initial release

The intended first public version is `v0.1.0`. Before configuration, inspect remote tags and Releases and reconcile any existing publication; never overwrite an existing version. If none exists, bootstrap release-please with a one-time first-release version override and a documented history boundary. Remove the override after the initial release PR so subsequent versions are computed normally.

Keep existing Git history intact. Write a curated initial changelog describing the application as delivered, rather than treating old non-Conventional commit titles as release notes. Verify the bootstrap PR in a test repository before enabling production publication.

## Maintainer workflow and automation

Keep `master` as the integration branch. Ordinary work uses short-lived branches and squash-merged PRs. PR titles are unrestricted; an advisory CI notice may remind maintainers about release classification. Use the PR title as the default squash message, then have the merging maintainer choose the appropriate Conventional Commit message.

Release-please maintains a release PR containing the version and changelog changes. The maintainer reviews its scope and notes and merges it only after all required checks pass. Do not enable auto-merge for release PRs. This merge is the publication decision; no separate routine Publish click is required.

Use manifest-mode release-please with one root package, the `simple` release strategy, unprefixed component names, `v` tags, draft releases, and explicit tag creation for drafts. Validate the selected pinned version's draft and tag behavior before rollout. A draft must be bound to a real immutable tag so later runs can identify the release boundary.

Use a GitHub App installation token for release-please so generated PR checks run automatically. Scope the App to this repository and the required contents, pull-request, and issue/label permissions. Store its private key as a GitHub Actions secret and its application ID as configuration. Package build jobs do not receive that key. Ordinary jobs default to `contents: read`; grant release write permissions only to jobs that need them.

Configure branch rules to require PRs and the aggregate CI check. Protect release tags against replacement/deletion, with only the release automation allowed to create them. Enable immutable releases before the first production publication. Record repository settings, App setup, and the exact required check names in the implementation runbook; do not assume these settings exist because workflow files have been merged.

### CI structure

Ordinary code changes run the existing build and test matrix. Documentation-only
changes run validation without compiling the application. Changes to recipes,
dependencies, install rules, desktop resources or CI tooling run the package
matrix instead of build-only checks. A version/changelog-only release PR uses
ordinary CI; publication owns the final tagged package build. PR titles remain
advisory, and `CI required` is the stable required check.

PR jobs have read-only credentials and no release secrets. Do not use
`pull_request_target` to execute contributor code. Actions are pinned to full
commit SHAs; container images are pinned by digest. Distribution repositories
remain rolling, so those pins do not promise identical binaries across attempts.
See [Continuous integration](ci.md) for selection and repository policy.

### Implemented automation

`release-please.yml` maintains the release PR and calls `release.yml` after it
creates the matching tag and draft. Both workflows require the `master` ref and
repository variable `RELEASE_AUTOMATION_ENABLED=true`. The App private key is
used only by release-please, never passed to package jobs.

The publication workflow has four jobs:

1. **Prepare:** resolve the existing tag, require ancestry on `master`, read the
   existing Release and select the Arch/Fedora matrix. An already published
   Release is a successful no-op.
2. **Source:** check out the tag, require agreement with `version.txt` and the
   release-please manifest, create one source archive and render its recipes.
3. **Packages:** build/test each package once, then check it in a separate clean
   runtime container. Both targets must succeed before publication.
4. **Publish:** collect source, rendered recipes, binary packages, source RPM and
   generated debug packages, write `SHA256SUMS`, replace the draft's files and
   publish it. Only this job uploads or removes release assets.

`tools/release/artifacts.py` only exports tracked source with version/full-SHA
metadata and normalized archive ownership/timestamps. It adds no application
runtime dependency. For example, from a clean tagged checkout:

```sh
python3 tools/release/artifacts.py source --source . \
  --tag v0.1.0 --output .ci-results/release-source
```

`--candidate` exports an untagged clean snapshot for PR package checks. Recipes
are rendered from the archive itself. Arch builds use the seeded source cache
and checksum without falling back to the unpublished download URL.

GitHub operations use `gh release view`, `gh release upload`, `gh release edit`
and `gh api` for draft asset deletion. Job dependencies carry build success;
there is no release inventory schema, provenance requirement, original-run
lookup or custom recovery client. Package/build logs remain CI artifacts.
Upgrade checks are available for packaging changes, not required on every release.

Publication is serialized without cancellation. Artifact names are stable within
a run, so **Re-run failed jobs** can use artifacts left by successful jobs.
Retrying a build replaces its CI artifact. A fresh dispatch rebuilds the whole
tag; it does not require retained artifacts from an earlier run.

## Dependency qualification and native support

### Audit before lowering requirements

The [dependency audit](dependency-audit.md) explains the Qt 6.6 and libvips 8.18.3 minimums. The decoder uses `VIPS_KERNEL_MKS2021`; qualifying an older backend requires checking all scaling presets and relevant upstream fixes.

Upstream introduced MKS2021 in 8.17.0, not 8.18.3. The retained 8.18.3 floor instead covers relevant SIMD resize bounds fixes missing from the tested Ubuntu package. Qt 6.5 is insufficient for the existing unconditional `QEvent::DevicePixelRatioChange` use, introduced in 6.6.

For each candidate distribution, record OS release, architecture, repository snapshot/date, compiler, CMake, Qt, libvips, libarchive, relevant codec packages, and test outcomes. Inspect API introduction versions, relevant upstream fixes, and distribution backports. Version-number comparison alone cannot establish either compatibility or vulnerability exposure.

Build and test with the distribution's standard repositories. Check all four scaling presets, ICC conversion and fallback, EXIF orientation, HiDPI, rotated region rendering, archive streaming, cancellation/stale work, and ownership of returned image buffers. Check supported JPEG, PNG, WebP, BMP, and DIB inputs and ZIP, 7z, and RAR sources using redistributable fixtures.

A lower minimum is acceptable only if existing capabilities and behavior remain intact. Do not remove a preset, silently substitute a kernel, or disable a feature to make an older system pass. Document any small API-equivalent compatibility adaptation and test both paths. If compatibility would require substantial rework, exclude that target from native support.

Native packages must not bundle private Qt/libvips, replace system libraries, require third-party PPAs, or download replacement libraries at installation. Do not silently compile a newer dependency in CI and claim support for an OS whose installed runtime cannot satisfy it.

### Native target matrix

Initial architecture: x86_64 (Debian/Ubuntu package architecture name: amd64).

| Target | Package | Qualification status |
| --- | --- | --- |
| Arch Linux rolling | `.pkg.tar.zst` | Qualified through clean native package builds, regression tests and fresh-container runtime checks; publication pending |
| Debian 13 | `.deb` | Excluded with current standard libvips 8.16.1: no MKS2021 |
| Ubuntu 24.04 LTS | Separate `.deb` | Excluded: standard Qt 6.4.2 lacks the required API |
| Ubuntu 26.04 LTS | Separate `.deb` | Diagnostic build/tests pass with 8.18.0; native support blocked by missing SIMD resize fixes |
| Fedora 44 | `.rpm` | Qualified through clean native package builds, regression tests and fresh-container runtime checks; publication pending |

The audit records actual installed Ubuntu 26.04 package versions and distinguishes diagnostic tests from qualification. Recheck repository versions and distribution backports before reconsidering exclusions; do not present these candidates as supported installations based only on API availability or passing smoke tests.

The machine-readable matrix is maintained in [packaging/platforms.json](../packaging/platforms.json); its [contract](../packaging/README.md) distinguishes selected candidates from qualified mandatory targets. Fedora 44 is the explicit Fedora candidate. Image digests remain null for untested environments. CI consumes the selected candidates, and the matrix records their pinned images and local clean-build results. Complete automated package qualification before promoting targets. The release workflow builds the selected Arch/Fedora matrix. Describe supported targets in release notes. Adding/removing a qualified platform requires a reviewed change; a failed release build cannot silently remove a mandatory platform.

Debian and Ubuntu builds are separate even if they use the same recipe. Fedora support does not imply support for RHEL, Rocky Linux, AlmaLinux, or openSUSE. ARM64 is deferred.

## Package design and desktop integration

### Native recipes

Use native distribution tools as the authoritative packaging layer:

- Arch: preserve root `PKGBUILD` for `insidious-git`; add a stable recipe under `packaging/arch/`. Build in a clean Arch environment. Stable sources use the official versioned source asset and a real checksum; VCS `SKIP` semantics do not carry over.
- Debian/Ubuntu: keep debhelper packaging templates under `packaging/debian/`, stage them as `debian/` in the extracted source tree, and build with `dpkg-buildpackage` in the target environment. Generate shared-library dependencies using standard Debian helpers.
- Fedora: keep the spec under `packaging/rpm/` and build with `rpmbuild` in a clean target Fedora environment. Use native dependency generation and explicit minimums where necessary.

All recipes use CMake installation with the target distribution's directory conventions. CPack is not the primary packager: native recipes provide clearer dependency handling, package revisions, validation, and downstream maintenance for the selected families.

Stable Arch metadata and Debian changelog entries are generated from the selected release version in a staging directory. The stable Arch source checksum is computed after creating the official source archive; publish the rendered recipe separately to avoid requiring an archive to contain its own checksum. Keep generation deterministic and retain templates in Git.

The rendered stable Arch recipe retains the final public release URL. Before running `makepkg` in CI, transfer the canonical source archive from the source job's CI artifact into the clean build environment's `SRCDEST`, using the exact filename expected by the recipe. Verify its SHA-256 digest against the source job's recorded digest and run makepkg's source-integrity checks against the rendered recipe. This avoids fetching a source asset that is not public yet while testing the same archive and checksum that users will receive. After publication, separately verify that the public source URL serves those same bytes. A missing or mismatched cached source must fail the pre-publication build rather than fall back to the unpublished URL.

Ship source packages where supported (`.dsc` and associated Debian source files, Fedora `.src.rpm`) and the rendered Arch recipe alongside binaries. Preserve package-manager-native filenames; use per-target directories during CI and ensure uploaded filenames cannot collide across distributions.

Install the application, desktop resources, documentation, and licenses. Do not install tests, audit tools, build caches, or private runtime libraries. Use native desktop/cache triggers where needed; maintainer scripts must not access the network, edit user preferences, or set default file associations.

For the initial release system, an application or packaging correction after publication requires a new application PATCH release. Package revisions start at 1 for each version. Do not replace published assets with a package-only rebuild; a separate package-revision publication pipeline is deferred.

### Desktop identity

Use `io.github._0xf836.Insidious` consistently for the desktop file, icon, AppStream component, and future Flatpak application ID. The leading underscore escapes the GitHub owner's initial digit to satisfy D-Bus well-known name rules, which Flatpak application IDs follow. This does not rename the existing QSettings namespace.

Provide a scalable icon, appropriate raster sizes, a localizable desktop entry, and AppStream metadata. Use `Exec=insidious %f` for the current one-path CLI, `Terminal=false`, and suitable Graphics/Viewer categories. Do not use `%F` until the command-line interface explicitly supports multiple paths.

Register Open With MIME types only for the supported image/archive allowlists. Do not advertise every format exposed by the system libvips build or make Insidious the default archive handler. Include project/help links and the MIT license in metadata; keep application metadata consistent with release versions.

Validate the application ID against Flatpak/D-Bus naming rules, including rejection of components starting with digits, and check identity agreement across desktop, icon, and AppStream resources. Validate with desktop-file and AppStream validators. Automate X11/Wayland startup checks with paths containing spaces and Unicode.

Desktop integration must not add application-owned recent-item writes. A separate file manager or desktop shell may record its own activity; do not claim that a desktop entry can prevent all traces created by other applications. Retain the existing non-native file-dialog policy unless a separate privacy decision changes it.

## Release contents, integrity, and presentation

Use the title `Insidious X.Y.Z` and review the generated changelog before merging
the release PR. Describe highlights, compatibility changes and known limitations.
Downloads contain the canonical `insidious-X.Y.Z.tar.xz`, Arch/Fedora binary
packages, rendered Arch PKGBUILD and Fedora spec, source RPM, any generated debug
packages, and `SHA256SUMS`. Validate downloads with `sha256sum -c SHA256SUMS`.
Checksums detect corruption; they do not authenticate the publisher. Package
repository signing and build provenance are outside the initial release process.

## Release runbook and recovery contract

### One-time setup

Inspect existing tags and Releases before bootstrap; never reuse a published
version. Configure the App, branch/tag policy and immutable releases, then test
an ordinary release and retry in an authorized disposable repository before
production enablement.

Create a dedicated GitHub App, disable its webhook, and grant only repository
Contents, Pull requests and Issues read/write access. Install it for the intended
repository only. In repository **Settings → Secrets and variables → Actions**,
store its numeric App ID as variable `RELEASE_APP_ID` and the complete PEM private
key as secret `RELEASE_APP_PRIVATE_KEY`. Keep the key out of Git, artifacts and
chat; rotate it by adding a new App key, replacing the secret, verifying a run,
then revoking the old key. The repository maintainer owns the App installation,
secret rotation and policy settings.

Set the default branch to `master`, configure the [CI repository policy](ci.md#repository-policy),
protect `v*` tags against updates/deletion with creation reserved for the release
App, and enable **Settings → General → Releases → Enable release immutability**.
The App must be allowed to create release branches/PRs and release tags without
being permitted to bypass required PR checks when merging. No approving review
or additional routine publication approval is required.

Bootstrap configuration retains a one-time `release-as: 0.1.0` override and an
explicit `bootstrap-sha` history boundary. The manifest agrees with `version.txt`.
After verifying that the version is unused, enable the workflows with repository
variable `RELEASE_AUTOMATION_ENABLED=true` and dispatch **Release automation** on
`master`. In the generated first release PR, remove `release-as` and the obsolete
`bootstrap-sha`, and curate the initial changelog entry and PR release notes around the product overview
in `CHANGELOG.md`. CI rejects the release PR until the override is removed. Later
versions are computed normally, without a persistent override.

### Routine release

1. Review the generated version and changelog and wait for `CI required`.
2. Merge the release PR. This is the publication decision.
3. Monitor package builds and publication, then confirm downloads are present.

### Retry policy

- **Unpublished:** use **Re-run failed jobs** while this run's artifacts remain
  available, or dispatch `release.yml` on `master` with the same tag for a full
  rebuild. After successful builds, publication rechecks that the Release is
  still a draft, removes its previous files, uploads the complete fresh set and
  publishes. A failed upload leaves an unpublished draft for another attempt.
- **Published:** do nothing. Never replace its files or move its tag. Corrections
  require a new version. Repeating an older release must not change Latest.

```sh
gh workflow run release.yml --repo OWNER/REPOSITORY --ref master -f tag=v0.1.0
```

Do not manually publish a draft while automation is uploading it. Partial drafts
do not block other versions. There are no abandonment markers or original-run
identifiers to maintain. A rebuild may produce different binary bytes because
distribution repositories change; the fresh set runs the ordinary package checks
again. Bitwise identity between unpublished attempts is not promised.

## Deferred distribution channels

GitHub Releases is the first download channel. AUR publication, hosted apt/RPM repositories, ARM64, nightly/RC channels, and an in-app updater are separate future work. Native recipes and generated metadata should remain suitable for downstream packaging without promising acceptance into distribution repositories.

Flatpak is the planned alternative for hosts excluded by native dependency qualification. Its design must use the same application ID, select a supported Qt-compatible runtime, and explicitly describe any dependencies built inside the Flatpak environment. The prohibition on private libraries applies to native packages; Flatpak's runtime/module model is a distinct future design, not a hidden native-package workaround.

Before implementing Flatpak, resolve file access, adjacent-folder navigation, archives, clipboard behavior, X11/Wayland, and portal/recent-item privacy. Do not assume opening one file through a portal automatically grants access to its neighbors. Flathub publication and permission choices require that later specification; this document does not claim Flatpak support is implemented.

## Delivery stages and acceptance

| Stage | Deliverable | Exit criteria |
| --- | --- | --- |
| 1. Compatibility (complete, revised scope) | Dependency audit, local regression tests and initial platform matrix | API/fix evidence, retained test results, explicit candidates/exclusions; clean qualification deferred to stages 3/4 |
| 2. Version identity (complete) | `version.txt`, generated metadata, About, VCS recipe adaptation | Local tests cover consistent versions, headless output, clean/dirty/unknown/archive cases and incremental refresh; release/archive publication remains future work |
| 3. CI (complete) | Reusable build/test jobs and PR conventions | Arch/Fedora builds, failure/cancellation handling and required-check policy; see [CI](ci.md) |
| 4. Packages and desktop (complete) | Native recipes, qualified Arch/Fedora targets, install rules, icon/desktop/AppStream | Automated regression and fresh-container installation/removal, settings/privacy and X11/Wayland startup checks pass; upgrade is not applicable until a preceding package exists |
| 5. Release automation | Release-please and draft-to-public package workflow | Local checks pass; qualify simplified publication and retry in a hosted test repository |
| 6. First release | Maintainer-reviewed version and full published artifact set | Runbook completed; downloads present and checksums valid |
| 7. Flatpak | Separate specification and implementation | Runtime, permissions, navigation, and privacy qualified before publication |

For package acceptance, test fresh installation and removal in clean environments. Run upgrade checks when installation or migration behavior changes. Check runtime library resolution, install paths, desktop validation, settings preservation, and absence of application-created history/cache/log files. Package-manager logs are distinct from application logs.

The existing automated regression suite covers supported formats, scaling presets, ICC/EXIF, rotated region rendering, and HiDPI. Package qualification and releases do not require a separate manual UI, menu/Open With, or interactive X11/Wayland acceptance pass. Document pre-existing bugs separately; do not claim packaging fixes archive or zoom bugs tracked elsewhere in the roadmap.

Source helper tests cover archive identity, tag/version agreement and clean
sources. CI policy tests cover job selection and required-job results. Hosted
acceptance covers both package builds, draft publication, retry after an upload
failure and a no-op after publication. Keep individual run evidence in Actions
artifacts rather than this specification.

## References

These are design references, not promises that an upstream service or distribution version will remain unchanged. Recheck tool schemas and platform package versions during implementation.

- [Semantic Versioning 2.0.0](https://semver.org/)
- [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
- [Release Please Action](https://github.com/googleapis/release-please-action)
- [Release Please strategies](https://github.com/googleapis/release-please/blob/main/docs/customizing.md)
- [Release Please manifest configuration](https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md)
- [GitHub workflow triggering and token behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- [GitHub release management and draft publication](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
- [Ubuntu 24.04 Qt package listing](https://packages.ubuntu.com/search?keywords=qt6&suite=noble)
- [Debian libvips package listing](https://packages.debian.org/search?keywords=libvips42)
- [Fedora libvips package listing](https://packages.fedoraproject.org/pkgs/vips/vips/)
- [Desktop Entry Specification](https://specifications.freedesktop.org/desktop-entry/latest/)
- [Flatpak application ID conventions](https://docs.flatpak.org/en/latest/conventions.html#application-ids)
- [D-Bus bus-name rules and escaping leading digits](https://dbus.freedesktop.org/doc/dbus-specification.html#message-protocol-names-bus)
- [Flatpak runtime, dependencies, and sandbox concepts](https://docs.flatpak.org/en/latest/basic-concepts.html)
