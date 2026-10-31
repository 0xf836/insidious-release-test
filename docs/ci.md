# Continuous Integration

CI validates pull requests against the Arch and Fedora targets from
[packaging/platforms.json](../packaging/platforms.json). Build-only checks and
native package qualification share one required aggregate. The
[release specification](releasing.md) owns publication, credentials and recovery.

## Workflows and policy

- `ci.yml` runs on pull requests (including title edits), pushes to `master`, and manual dispatch. Every run validates policy and selects either build-only checks or the full native package matrix; documentation-only changes run validation without builds.
- `checks.yml` runs CI policy, packaging and release-tool regressions. It validates numeric version syntax, release-please manifest agreement, tag agreement when called in tag context, selected target images. It exposes the matrix and package-check decision to its caller. Release-please PRs must remove the one-time bootstrap override before they pass.
- `build.yml` accepts the validated matrix as a reusable-workflow input. Each job runs the pinned official x86_64 image with a read-only source mount, copies a Git-less source export into disposable storage, installs standard distribution packages, builds Debug with tests enabled and developer audit tooling disabled, and runs the full CTest suite. Existing offscreen and HiDPI test properties are preserved. The container export identifies as `-dev+unknown`; official source-archive metadata validation remains covered by the version tests.
- `packages.yml` consumes a prepared source artifact and builds/tests each native package once through its recipe, followed by separate clean runtime containers. Changes to CMake, package recipes, desktop resources, CI/release tooling or workflows require this path; version/changelog-only changes do not. Manual dispatch and missing base history also request package checks. Candidate sources record the tested commit. Publication supplies an official tagged archive; upgrades are checked separately when packaging changes warrant it.
- `CI required` runs even after dependency failures. It requires successful validation and the selected build/package jobs, and accepts skips only for the explicitly unselected path or documentation-only changes. Failure, cancellation, missing results and unexpected skips fail the check. The matrix rejects duplicate/unknown targets, missing mandatory targets, empty candidate sets and unpinned images. The advisory title job is excluded from its dependencies and result checks.

`Release note hint` is a separate advisory job for PRs. A title without a
Conventional Commit prefix produces a notice for maintainers and succeeds;
contributors do not need to rename their PR. It does not gate builds or merging.
PR text is read from the event JSON and is never interpolated into shell commands
or echoed into workflow annotations.

Maintainers choose a Conventional Commit message when squash-merging, such as
`fix(viewer): restore zoom after rotation`, to classify release notes.
Dependabot uses the `ci(deps)` prefix automatically. Release-please and version
bump classification follow the [release specification](releasing.md#version-policy).

PR validation and build jobs have read-only permissions, do not persist checkout
credentials, do not inherit secrets and do not use `pull_request_target`. Package
jobs receive no App key or release write token. Only release-please, the
read-draft preparation job and publication have their required additional
credentials; see [release automation](releasing.md#implemented-automation).

Actions are pinned to full SHAs. Dependabot proposes monthly Action updates. Image updates are manual reviewed changes to `ci_image` and `image_digest` in the platform matrix. Container digests freeze the base image, **not** the rolling package repositories: each run upgrades from standard repositories and retains the resolved package inventory. Fedora disables weak dependencies and the optional Cisco OpenH264 repository (H.264 is outside the supported format allowlist); mandatory JPEG/PNG/WebP/BMP and archive support still runs through the regression suite. A digest is not a guarantee of bit-for-bit reproducibility.

## Artifacts and local execution

Each target uploads `build-<target>` for 14 days, including the build/package-manager log, complete installed package inventory, OS identity, repository configuration, UTC start time, CTest JUnit results, CTest logs and `ldd` output when those stages are reached. Failed early runs may have only partial evidence. Build logs contain the compiler, CMake and main dependency versions. These are developer CI artifacts, not application file logs or release packages. Keep raw build/test logs, CTest XML, full package inventories and runtime library reports in Actions artifacts or the ignored `.ci-results/` directory for local runs; do not commit them under `docs/`. Document lasting dependency requirements and compatibility constraints; keep individual run results in CI artifacts or PR discussions.

Run policy checks locally:

```sh
python3 -m unittest discover -s tests -p 'ci_policy_tests.py' -v
python3 -m unittest discover -s tests -p 'packaging_tests.py' -v
python3 -m unittest discover -s tests -p 'release_tests.py' -v
python3 tools/ci/checks.py validate
bash -n tools/ci/build.sh
actionlint
```

To repeat a clean candidate build, obtain its exact `ci_image` from `packaging/platforms.json`, then run from the checkout root, substituting that image and `arch` or `fedora`:

```sh
mkdir -p .ci-results
docker run --rm --platform linux/amd64 \
  -v "$PWD:/src:ro" -v "$PWD/.ci-results:/results" \
  IMAGE bash /src/tools/ci/build.sh DISTRIBUTION
```

Use an empty output directory for each run. Docker-created output may be owned by root. Python 3 and Docker are developer/CI tools; they add no application runtime dependencies or installed contents. `BUILD_TESTING=OFF` removes test targets and the Qt Test requirement. `INSIDIOUS_BUILD_MEMORY_AUDIT=ON` explicitly enables the developer audit executable; it defaults to off and is never installed.

## Rotation regression coverage

`decoderExifRotationAndRegion` is mandatory at every thread count. Transformed rendering uses source-ordered strip evaluation, described in [Current implementation](implementation.md#sequential-decode-and-rotated-rendering). Run the rotation regressions with a low thread count using:

```sh
VIPS_CONCURRENCY=2 QT_QPA_PLATFORM=offscreen \
  build/insidious_core_tests decoderExifRotationAndRegion decoderTransformedSampling
```

## Repository policy

Protect `master` with required pull requests and the exact `CI required` check from GitHub Actions. Require the branch to be up to date, enforce protection for administrators, and disable force pushes and branch deletion. Approving reviews are optional. Enable squash merging with the PR title as the default commit title (`squash_merge_commit_title=PR_TITLE`); maintainers adjust that message before merging when release classification is needed. Do not require `Release note hint` in branch protection. Repository settings are managed separately from workflow files.

Build-only CI does not require a separate live fork PR test. Native package and release readiness remain governed by the [platform matrix](../packaging/README.md) and [release acceptance criteria](releasing.md#delivery-stages-and-acceptance).

Package qualification uses the [two-container check](packaging.md#package-checks)
for packaging changes and releases. It replaces build-only jobs for those changes;
ordinary application PRs retain build-only checks; documentation-only changes skip builds. Native recipes
run the regression suite during package builds; runtime checks consume those
packages without another build or CTest pass. Package evidence is retained for
90 days; ordinary build evidence remains at 14 days. The stable required check
name remains `CI required`.

GitHub semantics used here are described in [reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) and [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
