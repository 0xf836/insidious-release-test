# Distribution Target Matrix

`platforms.json` is the canonical machine-readable inventory of native target decisions. Schema version 1 records qualified targets, candidates, exclusions and diagnostic evidence. CI consumes its selected targets. Native qualification uses the [package checks](../docs/packaging.md#package-checks); publication uses the [release workflow](../docs/releasing.md#implemented-automation).

- `selected_for_future_qualification` retains the Arch/Fedora CI test scope, including qualified targets. Fedora 44 is explicit, not an alias for whichever release is latest later.
- `native_qualified` requires successful clean-system builds, automated regression tests and package checks using standard packages, including X11/Wayland startup. Arch and Fedora 44 are qualified; Debian/Ubuntu remain excluded or blocked.
- `release_required` identifies mandatory release targets after qualification. Arch and Fedora 44 are mandatory. Publication rejects missing mandatory targets and an empty qualified target set.
- `build_validation` distinguishes host-local tests, passing clean-container tests, unrun candidates, and a diagnostic build with a dependency constraint override. A diagnostic override never qualifies a native target.
- `ci_image` pins each selected CI candidate to an official repository and full digest. `image_digest` must agree with it.
- `image_digest` is null when no target image was tested. It is not permissible to invent a digest or infer qualification from a package listing.
- `artifact_kind` states the intended package type. Arch/Fedora recipe templates and preparation are described in [Native packaging](../docs/packaging.md); publication is governed by the [release runbook](../docs/releasing.md#release-runbook-and-recovery-contract). Build workflows are documented in [Continuous integration](../docs/ci.md).
- `package_validation` records clean build/runtime qualification; `upgrade_validation` distinguishes the first package, which has no predecessor, from a tested upgrade.

`audit_complete` covers dependency analysis and the initial platform inventory.
`native_qualification_complete` is true for the selected Arch/Fedora scope.
`release_ready` requires hosted qualification of the current publication workflow.
It is false until the simplified workflow has completed that trial.
It does not configure the production repository or authorize its first release;
the [maintainer runbook](../docs/releasing.md#release-runbook-and-recovery-contract)
remains required. Manual interactive acceptance is not required. Keep individual
build logs, test results and resolved package inventories in Actions artifacts or
the ignored `.ci-results/` directory.

See the [dependency audit](../docs/dependency-audit.md) and [release specification](../docs/releasing.md) for evidence and acceptance gates. This file is developer documentation and is not added to current installed documentation rules; package checks consume the canonical source archive.
