# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.3.0] - 2026-05-01

### Added

- Bundle macOS/Windows double-click launcher scripts
- Prompt for connection details when launched without args
- Default to wss:// when no scheme is given


### Fixed

- Use --unreleased, not --current, in the changelog gate


## [0.2.0] - 2026-05-01

### Fixed

- Include self-sends in SentEvent emission


## [0.1.0] - 2026-05-01

### Added

- Add persistent event log file
- Vim hjkl scrolling and tmux-safe tab bindings
- Add command input with item/location autocomplete
- Live Hints tab backed by DataStorage subscription


### Changed

- Migrate to websockets asyncio client API


### Dependencies

- Tighten textual and websockets lower bounds


### Documentation

- Document the persistent event log
- Reflow README tables to aligned column widths
- Publish platform requirements and refreshed bindings


### Other

- Initial commit

[0.3.0]: https://github.com/Joxtacy/ap-ledger/compare/v0.2.0..v0.3.0
[0.2.0]: https://github.com/Joxtacy/ap-ledger/compare/v0.1.0..v0.2.0
[0.1.0]: https://github.com/Joxtacy/ap-ledger/releases/tag/v0.1.0

