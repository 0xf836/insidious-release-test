# Architecture Decisions

Decision status is one of **Accepted**, **Planned**, **Historical**, or **Superseded**. Planned records specify an agreed future direction but do not describe implemented behavior; change their status when the relevant implementation and validation are complete. Historical records explain how the current architecture emerged but no longer prescribe a staged implementation. Superseded records retain context and point to the replacement decision.

## ADR-001: Product documentation was written primarily in Russian

**Status:** Superseded by ADR-018.

**Decision:** Early product documents used Russian because the project owner originally formulated and reviewed requirements in Russian. Agent instructions remained in English for engineering precision.

**Rationale:** This reduced friction while the initial product direction was being established. A public repository and a broader contributor audience later made a single English documentation language more valuable.

## ADR-002: Archive support was introduced as a bounded stage

**Status:** Historical.

**Decision:** ZIP, 7z, and RAR support was introduced after the core viewer pipeline, through libarchive and the collection-source abstraction, without disk extraction. Passwords were kept only in memory.

**Rationale:** Archive access introduced streaming, password, error, and format-specific behavior that needed isolation from ordinary file viewing. The result is now part of the regular product architecture rather than a separate development stage.

## ADR-003: Image origins use collection-source semantics

**Status:** Accepted.

**Decision:** Filesystem folders, selected file lists, archives, and homogeneous multi-source selections present images to viewer state through common collection semantics. The Files panel additionally consumes a source tree whose selected folder supplies the active collection.

**Rationale:** This prevents source-specific branching throughout the viewer and makes navigation, errors, and future sources easier to reason about.

## ADR-004: Image caches are memory-only

**Status:** Accepted.

**Decision:** Decoded viewer images, thumbnails, prefetched neighbors, and comparison rasters use bounded process-memory caches only.

**Rationale:** Persistent image caches conflict with the no-traces privacy contract. Memory-only state also makes source changes and process exit clear invalidation boundaries.

## ADR-005: Opening one image uses its parent folder as context

**Status:** Accepted.

**Decision:** Opening one supported filesystem image selects it immediately and asynchronously loads the parent folder as browsing context.

**Rationale:** Neighbor navigation is expected in an image viewer, while immediate selection avoids waiting for the complete folder scan before showing the requested image.

## ADR-006: Viewer rotation does not modify source files

**Status:** Accepted.

**Decision:** Rotate left and right are view-only transforms. Rotation participates in decode and cache identity, resets when the current image changes, and does not affect copied original bytes.

**Rationale:** Source modification requires a separate save and conflict workflow and is outside the viewer’s product role.

## ADR-007: The native application uses C++20 and Qt 6 Widgets

**Status:** Accepted.

**Decision:** The application uses C++20, Qt 6.6+ Widgets, QtConcurrent, and Qt Test. `QEvent::DevicePixelRatioChange` sets the Qt API floor; Ubuntu 24.04 with its standard Qt is excluded.

**Rationale:** Qt provides a native Linux GUI, mature actions and input handling, drag and drop, asynchronous task integration, and a suitable test framework without introducing a web runtime.

## ADR-008: libvips builds display rasters

**Status:** Accepted.

**Decision:** Image decoding, scaling, orientation, region extraction, and optional ICC conversion use libvips/vips-cpp. Unsupported or unavailable codecs produce a decode error rather than switching to a second backend.

**Rationale:** libvips is demand-driven, supports streaming and parallel processing, and fits the application’s performance and memory goals. One backend keeps color, orientation, and memory behavior consistent.

The minimum remains libvips/vips-cpp 8.18.3. MKS2021 itself appeared in 8.17, but Ubuntu 26.04's unpatched 8.18.0 package lacks relevant SIMD resize bounds fixes. A diagnostic build passes functional tests; disabling SIMD as a workaround materially slows resizing and was not adopted. See the [dependency audit](dependency-audit.md) for evidence and limits.

## ADR-009: Decode the raster needed for the current view

**Status:** Accepted.

**Decision:** Fit mode requests a display-sized raster. Non-fit zoom and actual-size views request the visible region plus overscan by default; users may disable region rendering and request the full scaled raster for smoother panning. All paths use the shared render-memory budget.

Scaling quality, embedded color conversion, EXIF orientation, view rotation, output geometry, and device pixel ratio are part of the request and cache identity whenever they change output. Actual size maps one source pixel to one physical display pixel.

**Rationale:** View-sized work reduces memory pressure on large sources while retaining explicit quality and HiDPI semantics. The render budget limits output raster size; separate audit tooling measures total process peak memory.

## ADR-010: Avoid recent-item integration

**Status:** Accepted.

**Decision:** The application does not maintain recent files and uses non-native Qt file dialogs to avoid implicit desktop recent-item integration. `QSettings` stores non-history preferences and layout state only.

**Rationale:** Privacy requires controlling not only application-owned history but also toolkit behavior that may publish viewed paths to the desktop environment.

## ADR-011: Default mouse input separates browsing and inspection

**Status:** Accepted.

**Decision:** Wheel navigates images, `Ctrl+wheel` zooms around the cursor, and `Shift+wheel` does nothing by default. Wheel mappings are configurable. The default left-button mode uses click-to-zoom/restore and drag-to-pan outside base fit; an alternative hold-to-zoom mode restores the previous view on release. Right drag selects a zoom rectangle, and left double click toggles fullscreen without triggering click zoom.

Configured mouse-button shortcuts take priority over built-in gestures using the same input.

**Rationale:** The mapping keeps rapid browsing, temporary inspection, pan, precise rectangle zoom, and fullscreen distinct while allowing users to adapt wheel behavior.

## ADR-012: A failed entry does not destroy the collection

**Status:** Accepted.

**Decision:** Missing, unreadable, corrupt, unsupported, or oversized current entries show an error while preserving the source, active collection, and previous/next navigation. The application does not silently skip the failed entry.

**Rationale:** Automatic skipping makes position and failure behavior unpredictable. The user should decide whether to continue forward or backward.

## ADR-013: Image navigation resets view state by default

**Status:** Accepted.

**Decision:** Previous and next reset zoom and pan to the configured fit or actual-size base mode before loading the destination. Preferences can preserve the view instead. Rotation always resets when the image changes.

**Rationale:** Resetting is predictable across images with different dimensions, while the optional preserve policy supports close inspection of related images.

## ADR-014: Fullscreen chrome uses overlay widgets

**Status:** Accepted.

**Decision:** Viewer fullscreen hides normal chrome and shows edge-triggered child overlays above the image. Compare fullscreen is a separate clean layout without viewer overlays. Overlay visibility must not participate in viewer layout or trigger image rendering.

**Rationale:** Dock or layout-based fullscreen controls resize the viewport and can cause zoom changes, decode work, and flicker. Overlays preserve the displayed view.

## ADR-015: The Files panel uses a source tree and active folder

**Status:** Accepted.

**Decision:** The Files panel separates a folder tree from the active folder’s direct-image List and Thumbnails views. Filesystem branches load lazily; archive trees come from asynchronous header enumeration. Image navigation crosses suitable folders at boundaries, while first and last remain local.

**Rationale:** A single flat recursive list loses source structure and scales poorly. Active-folder semantics keep navigation and UI state understandable.

## ADR-016: Settings schema and settings UI are separate

**Status:** Accepted.

**Decision:** `src/core/app_settings.*` owns defaults, stable identifiers, serialization, validation, and category reset behavior. `src/ui/settings_dialog.*` presents editable widgets but does not define persistence policy.

**Rationale:** A UI-independent schema is easier to test and prevents widget code from becoming the source of truth for privacy or compatibility.

## ADR-017: Multi-source open accepts homogeneous groups

**Status:** Accepted.

**Decision:** Several images form a flat temporary collection; several folders or several archives form ordered roots under a synthetic source tree. Mixed or partially unsupported sets fail atomically.

**Rationale:** Homogeneous groups have clear navigation and password semantics. Rejecting ambiguous mixed sets avoids partial opens and source-specific special cases throughout the UI.

## ADR-018: Project documentation is maintained in English

**Status:** Accepted.

**Decision:** README files, product and engineering documentation, agent instructions, internal comments, identifiers, commit messages, and developer-facing notes are written in English. User-visible UI strings remain prepared for localization.

**Rationale:** One documentation language makes the public repository accessible to a broader audience and reduces ambiguity for contributors and coding agents. Historical context is translated rather than discarded.

## ADR-019: Arch Linux development builds use a VCS package

**Status:** Accepted.

**Decision:** The repository ships a root `PKGBUILD` for `insidious-git`. It clones the public Git repository, derives a development version from `version.txt` and Git revision, builds with CMake and Ninja, runs CTest, and installs through the project’s native CMake install rules.

**Rationale:** The project has no tagged release archive yet, so a VCS package is more truthful than a release recipe with a moving source or skipped checksum. A future release package must use a tag-bound immutable archive and a real checksum. Desktop integration is intentionally separate from the first package because it needs a privacy-aware design for MIME and recent-item behavior.

## ADR-020: Release PRs control versioning and publication

**Status:** Implemented; hosted qualification and production enablement are separate gates.

**Decision:** Use SemVer, Conventional Commit squash titles, and release-please with a single `version.txt` application version. PR titles are unrestricted; maintainers choose the release classification in the final squash commit message. A maintainer merges the tested release PR; GitHub Actions then builds from its exact tagged source, verifies all required packages, and publishes a complete immutable GitHub Release from a draft. Keep `master` and one ordinary release channel initially. The [release specification](releasing.md) owns configuration, validation, and recovery details.

**Rationale:** A reviewable release PR keeps release timing under maintainer control while automating repetitive version and changelog work. Draft staging prevents users from seeing incomplete downloads. Immutable tags/assets and explicit retry validation preserve artifact identity.

Version identity, release-please configuration, canonical archives, native package
workflows, signed inventories and draft recovery are implemented. Bootstrap keeps
one explicit history boundary and an initial-version override which must be
removed in the first release PR. Publication uses a retained CI bundle, verifies
existing remote bytes, and never overwrites an asset. A published rerun is read-only.
The [release runbook](releasing.md#release-runbook-and-recovery-contract) owns
repository setup and the test-repository acceptance gate.

## ADR-021: Native distribution uses qualified system dependencies

**Status:** Planned.

**Decision:** Audit the actual Qt/libvips requirements before changing minimums. Qualify target distributions with their standard libraries and the existing feature set. Do not bundle private Qt/libvips, replace system libraries, or require third-party repositories for native packages. Exclude incompatible targets; plan Flatpak separately as a future runtime-based distribution channel.

**Implementation status:** Dependency evidence, regression tests and automated native Arch/Fedora 44 qualification are recorded in the [platform matrix](../packaging/platforms.json). Release automation and publication remain separate gates.

**Rationale:** Current version constraints have historical explanations but need API, behavior, and relevant-fix evidence before they define distribution coverage. Preserving native dependency management avoids a second private runtime maintenance burden. See [dependency qualification](releasing.md#dependency-qualification-and-native-support).

## ADR-022: Native recipes share installation and desktop identity

**Status:** Implemented for Arch/Fedora, including automated native qualification; publication pending. Debian/Ubuntu recipes remain deferred.

**Decision:** Use separate stable Arch, debhelper Debian/Ubuntu, and Fedora RPM recipes over common CMake install rules. Retain the root Arch VCS recipe. Adopt `io.github._0xf836.Insidious` for desktop/icon/AppStream and future Flatpak identity, escaping the owner's initial digit according to D-Bus naming rules, with Open With integration but no automatic default-association changes or application recent-item writes. Publish packages through GitHub Releases first; AUR and hosted package repositories remain later work.

**Rationale:** Native recipes provide distribution-specific dependency and package validation while shared install rules keep contents consistent. One desktop identity prepares future Flatpak integration without changing the existing settings namespace. See [package and desktop design](releasing.md#package-design-and-desktop-integration). [Native packaging](packaging.md) describes the implemented Arch/Fedora templates and desktop resources. Debian/Ubuntu recipes remain deferred pending compatible system dependencies; ADR-019 describes the retained VCS recipe.

## ADR-023: Supported formats require the distribution ImageMagick loader

**Status:** Accepted.

**Decision:** Require the system libvips ImageMagick loader in clean build environments and native runtime dependency lists: `imagemagick` on Arch and `vips-magick` on Fedora. Keep missing Magick module warnings visible. No private library, new image backend or format allowlist expansion is introduced.

**Rationale:** Clean candidate builds with the main libvips packages compiled successfully but failed all BMP/DIB decode checks (12 core cases). Arch ships the module with libvips but leaves its ImageMagick library optional; Fedora ships it as a separate subpackage. The viewer already promises these formats, so a successful host build with undeclared installed codecs is insufficient. [Continuous integration](ci.md) describes the candidate build workflows; native package qualification remains separate.
