# Documentation

The documentation is organized by audience and responsibility. Each topic has one canonical home; other documents should link to it instead of copying detailed behavior.

## For users

- [User guide](user-guide.md) explains how to open sources, browse folders and archives, control the viewer, compare images, use fullscreen, and configure preferences.
- [Requirements](requirements.md) records the precise behavioral and privacy guarantees behind the user-facing workflow.
- [Roadmap](roadmap.md) lists future work and known areas of investigation. It is not a release promise.
- [Native packaging](packaging.md) describes stable Arch/Fedora recipes, source validation and package checks.
- [Arch Linux package](arch-linux.md) documents the `makepkg` workflow and package boundaries.

## Product context

- [Product principles](product.md) defines the purpose, target experience, core values, and deliberate non-goals.
- [Project evolution](project-evolution.md) preserves the context of the original viewer foundation and explains how the product expanded beyond it.
- [Glossary](glossary.md) defines project-specific terms used across product and engineering documentation.

## For maintainers and coding agents

- [Architecture](architecture.md) describes stable layer boundaries, source abstractions, threading, rendering, caching, and privacy design.
- [Current implementation](implementation.md) maps those concepts to the current files, classes, build targets, and data flows.
- [Architecture decisions](decisions.md) records important choices, their status, and their rationale.
- [Versioning, releases, and Linux distribution](releasing.md) documents version identity, CI, release automation and recovery, dependency qualification, native packaging and the production release runbook.
- [Continuous integration](ci.md) describes reusable validation/build workflows, required checks, artifacts, local execution and repository policy.
- [Platform matrix](../packaging/README.md) explains the machine-readable target inventory, qualification and exclusions.
- [Dependency compatibility audit](dependency-audit.md) records the current Qt/libvips minimum rationale, Ubuntu 26.04 experiments, and remaining native-platform qualification limits.
- [Technical risks](technical-risks.md) tracks unresolved engineering risks and active mitigations.
- [Total peak memory audit](memory-audit.md) documents the developer-only memory measurement workflow and baseline.
- [AGENTS.md](../AGENTS.md) contains repository-wide implementation rules for coding agents.
- [PLANS.md](../PLANS.md) defines when and how to write an execution plan.

## Maintenance rules

- Keep public descriptions in `README.md` concise and link here for details.
- Update `requirements.md` when observable behavior, supported inputs, or privacy guarantees change.
- Update `user-guide.md` when controls or workflows change.
- Update `architecture.md`, `implementation.md`, and `decisions.md` when structure, data flow, dependencies, or architectural policy changes.
- Update `roadmap.md` when priorities change; completed work belongs in the current-feature documentation or project evolution, not in an ever-growing completed backlog.
- Keep all project documentation in English and keep user-visible strings ready for localization.
