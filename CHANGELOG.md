# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial public release preparation
- Comprehensive documentation structure
- Example scripts for common use cases
- Contributing guidelines
- Agent prompt templates in `agent/` directory
- opencode integration documentation

## [0.1.0] - 2025-12-25

### Added
- Multi-agent debate orchestration system
- PostgreSQL-backed state management
- Redis-based task queue and rate limiting
- Support for Claude, Gemini, and Codex agents
- Consensus detection algorithm
- Task triage and complexity assessment
- Cost tracking across agent invocations
- Rich CLI with progress tracking
- Database migrations via Alembic
- Worker processes for distributed execution
- Comprehensive test suite
- Project documentation

### Features
- **Orchestration**: Coordinate multiple AI agents in structured debates
- **State Management**: Persistent task, round, and analysis tracking
- **Consensus Building**: Automatic agreement detection across agents
- **Workflow Phases**: Exploration, planning, debate, implementation, verification
- **Configuration**: Environment-based configuration system
- **CLI**: Command-line interface for task management
- **Workers**: Distributed worker architecture for scalability

### Documentation
- Architecture overview
- Setup and installation guide
- Configuration reference
- Usage examples
- Contributing guidelines
- API documentation

## Release Notes

### Version 0.1.0

Initial release of Debate Workflow, a sophisticated multi-agent orchestration system for AI-assisted code analysis and implementation.

**Key Features:**
- Multi-agent debate workflow with consensus detection
- PostgreSQL and Redis for state management
- Rich CLI for task management
- Worker-based architecture for scalability
- Comprehensive documentation and examples

**Known Limitations:**
- Currently supports three agents (Claude, Gemini, Codex)
- Consensus algorithm may need tuning for specific use cases
- Documentation is in progress

**Upgrade Notes:**
This is the initial release, no upgrade path needed.

---

## Types of Changes

- `Added` for new features
- `Changed` for changes in existing functionality
- `Deprecated` for soon-to-be removed features
- `Removed` for now removed features
- `Fixed` for any bug fixes
- `Security` for vulnerability fixes

## Links

[Unreleased]: https://github.com/yourusername/multi-agent-orchestration/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/multi-agent-orchestration/releases/tag/v0.1.0
