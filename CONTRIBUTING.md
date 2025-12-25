# Contributing to Debate Workflow

Thank you for your interest in contributing to Debate Workflow! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for all contributors.

## Getting Started

### 1. Fork and Clone

```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/debate-workflow.git
cd debate-workflow

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/debate-workflow.git
```

### 2. Set Up Development Environment

```bash
# Run the setup script
./scripts/setup.sh

# Or set up manually
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 3. Create a Branch

```bash
# Update your fork
git checkout main
git pull upstream main

# Create a feature branch
git checkout -b feature/your-feature-name
```

## Development Workflow

### Making Changes

1. **Write code** following our style guidelines
2. **Add tests** for new functionality
3. **Update documentation** if needed
4. **Run tests** to ensure nothing breaks
5. **Commit changes** with clear messages

### Code Style

We use automated tools for code formatting and linting:

```bash
# Format code
ruff format .

# Check for issues
ruff check .

# Type checking
mypy debate/

# Run all checks
ruff check . && ruff format --check . && mypy debate/
```

#### Python Style Guidelines

- Follow [PEP 8](https://pep8.org/)
- Use type hints for function signatures
- Maximum line length: 100 characters
- Use descriptive variable names
- Add docstrings for public functions/classes

Example:

```python
def calculate_consensus(
    findings: list[Finding],
    threshold: float = 80.0,
) -> ConsensusBreakdown:
    """Calculate consensus score between agent findings.

    Args:
        findings: List of findings from multiple agents
        threshold: Minimum consensus percentage required

    Returns:
        Detailed consensus breakdown with scores

    Raises:
        ValueError: If findings list is empty
    """
    if not findings:
        raise ValueError("Findings list cannot be empty")

    # Implementation...
```

### Testing

We use pytest for testing:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_consensus.py

# Run with coverage
pytest --cov=debate --cov-report=html

# Run tests with verbose output
pytest -v

# Run only tests matching a pattern
pytest -k "consensus"
```

#### Writing Tests

- Place tests in `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use descriptive test names
- Include docstrings explaining what is tested

Example:

```python
import pytest
from debate.consensus import ConsensusCalculator

def test_consensus_with_identical_findings():
    """Test consensus calculation when agents have identical findings."""
    calc = ConsensusCalculator()

    findings1 = [create_finding(category="security", file="auth.py")]
    findings2 = [create_finding(category="security", file="auth.py")]

    score = calc.calculate(findings1, findings2)

    assert score.overall_score == 100.0
```

### Database Changes

When making database schema changes:

1. **Create a migration**:
   ```bash
   uv run alembic revision -m "Add user_preferences table"
   ```

2. **Edit the migration** in `alembic/versions/`

3. **Test the migration**:
   ```bash
   # Apply migration
   uv run alembic upgrade head

   # Test rollback
   uv run alembic downgrade -1

   # Re-apply
   uv run alembic upgrade head
   ```

4. **Update models** in `debate/models.py` if needed

### Documentation

Update documentation when you:

- Add new features
- Change existing behavior
- Add configuration options
- Introduce breaking changes

Documentation locations:

- **README.md**: Overview and quick start
- **docs/architecture.md**: System design
- **docs/setup.md**: Installation guide
- **docs/configuration.md**: Config reference
- **examples/**: Usage examples
- **Docstrings**: In-code documentation

## Pull Request Process

### Before Submitting

1. **Update your branch**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run full test suite**:
   ```bash
   pytest
   ruff check .
   mypy debate/
   ```

3. **Update CHANGELOG** (if applicable)

4. **Review your changes**:
   ```bash
   git diff upstream/main
   ```

### Submitting PR

1. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Open Pull Request** on GitHub

3. **Fill out PR template**:
   - Describe what changed
   - Explain why the change is needed
   - Link related issues
   - Add screenshots for UI changes
   - List breaking changes

4. **Request review** from maintainers

### PR Guidelines

**Good PR Title**:
- ✓ `Add consensus threshold configuration option`
- ✓ `Fix database connection leak in worker processes`
- ✗ `Update code`
- ✗ `Fixes`

**PR Description Should Include**:
- **What**: What does this PR do?
- **Why**: Why is this change needed?
- **How**: How does it work?
- **Testing**: How was it tested?
- **Screenshots**: For UI changes
- **Breaking Changes**: If any

**Example**:

```markdown
## What
Adds configurable consensus threshold for debate resolution.

## Why
Different projects may require different levels of agreement.
Fixed threshold of 80% is too rigid for some use cases.

## How
- Added `DEBATE_CONSENSUS_THRESHOLD` config option
- Updated `ConsensusCalculator` to use configured value
- Added validation (must be 0-100)

## Testing
- Added unit tests for threshold validation
- Tested with values: 50, 80, 95
- Verified backward compatibility (defaults to 80)

## Breaking Changes
None - backward compatible with default value.
```

### Review Process

- Maintainers will review your PR
- Address feedback by pushing new commits
- Once approved, maintainers will merge

## Types of Contributions

### Bug Fixes

1. **Check existing issues** for duplicates
2. **Create an issue** describing the bug
3. **Submit PR** with fix and test

### New Features

1. **Open an issue** to discuss the feature first
2. **Get approval** from maintainers
3. **Implement** the feature
4. **Add tests** and documentation
5. **Submit PR**

### Documentation

- Fix typos or unclear sections
- Add examples
- Improve setup instructions
- No prior approval needed for docs-only changes

### Performance Improvements

- Include benchmarks showing improvement
- Explain the optimization technique
- Ensure no functionality breaks

## Commit Message Guidelines

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting changes
- `refactor`: Code restructuring
- `perf`: Performance improvement
- `test`: Adding tests
- `chore`: Maintenance tasks

### Examples

```
feat(consensus): add configurable threshold for consensus detection

Allow users to customize consensus threshold via DEBATE_CONSENSUS_THRESHOLD
environment variable. Default remains 80% for backward compatibility.

Closes #123
```

```
fix(worker): prevent database connection leak

Workers were not properly closing database connections after task
completion, leading to connection pool exhaustion. Added proper
cleanup in finally block.

Fixes #456
```

## Release Process

(For maintainers)

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create release tag: `git tag -a v0.2.0 -m "Release 0.2.0"`
4. Push tag: `git push upstream v0.2.0`
5. GitHub Actions will build and publish

## Getting Help

- **Questions**: Open a [Discussion](https://github.com/owner/debate-workflow/discussions)
- **Bugs**: Open an [Issue](https://github.com/owner/debate-workflow/issues)
- **Security**: Email security@example.com

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Given credit in related documentation

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to Debate Workflow! Your efforts help make AI-assisted development better for everyone.
