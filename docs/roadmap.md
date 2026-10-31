# Roadmap

This roadmap is a living statement of direction, not a release schedule or compatibility promise. Current capabilities are documented in the [README](../README.md), [user guide](user-guide.md), and [project evolution](project-evolution.md).

## Next

### Password-protected archive opening

- Reproduce and fix the reported failure when opening a password-protected archive.
- Verify successful opening with a correct password, retry after an incorrect password, and cancellation without losing navigation state. Keep passwords in memory only and do not extract entries to disk.

### High zoom levels

- Reproduce and fix the reported inability to reach high zoom levels.
- Check zoom limits, region rendering, and render-memory budget handling so supported zoom levels remain usable without bypassing memory safeguards.

### Quick Jump polish

- Make the fullscreen search surface more compact.
- Route `Up` and `Down` to the result list while the search field has focus.

### Fullscreen restoration under tiling window managers

- Reproduce and isolate the lower-edge artifact observed after leaving fullscreen with the dark theme under i3wm.
- Ensure fullscreen entry and exit restore the exact normal layout without stale overlay or backing-store artifacts.

### Archive performance characterization

- Reproduce tiny BMP archive decode failure and headerless DIB streaming limitations; current file and archive loaders differ.
- Benchmark navigation through large ZIP, 7z, and RAR sources.
- Measure repeated header traversal and format-specific access costs.
- Revisit speculative archive prefetch only after the access pattern is understood.

## Later

### Rendering and interaction

- Research display-profile and monitor-profile matching as a separate color-management layer.
- Consider a temporary magnifier mode that follows the cursor while the left button is held and restores the previous view on release.

### Comparison

- Evaluate additional comparison modes only when they solve a concrete workflow not covered by Row, Grid, Carousel, Hover Switch, and alignment presets.

### Formats

- Expand the supported format allowlist to include AVIF, JPEG 2000, JPEG XL, HEIC, GIF, and other libvips-supported formats that fit the existing viewer and decoder architecture without major rework.
- Inventory additional candidates, including TIFF, and verify loader availability, target-distribution codec dependencies, rendering correctness, and memory behavior before enabling each format.
- Define still-frame or page selection behavior for animated and multi-page inputs before enabling them; full animation playback is a separate scope decision.
- Treat RAW as a separate research effort because it requires preview policy, color processing, and heavier dependencies.

### Input customization

- Extend shortcut editing beyond core viewer commands if users need it.
- Add shortcut profiles, import/export, or scopes only after concrete demand establishes their semantics.

### Distribution

Follow the [release specification](releasing.md) for distribution design and acceptance criteria. Dependency requirements, version identity, [CI](ci.md), desktop integration, [Arch/Fedora package qualification](packaging.md) and release automation are implemented. The simplified publication workflow needs a hosted test-repository trial before production enablement. Remaining work:

6. Qualify and publish the first release through the maintainer runbook.
7. Design Flatpak for systems excluded from native support. Keep AUR publication, hosted apt/RPM repositories, and ARM64 as separate future work.

Revisit native Debian/Ubuntu recipes when dependency exclusions are resolved.

### Memory auditing

- Add thumbnail generation and cache scenarios before increasing thumbnail cache size or preload range.

## Explicit non-goals

- Persistent recent-file, recent-folder, or recent-archive history.
- Persistent thumbnail or decoded-image caches by default.
- Persistent comparison sessions or selected comparison paths.
- Archive extraction to disk during normal viewing.
- Archive password storage.
- File logging during normal use.
- Silent support for every format exposed by the system image stack.
