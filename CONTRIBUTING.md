# Contributing to Archilles

Thank you for your interest in contributing to Archilles! This document provides guidelines for contributing to the project.

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md). We're committed to providing a welcoming and inclusive community.

## How to Contribute

### Reporting Bugs

**Before submitting a bug report:**
- Check the [FAQ](docs/FAQ.md) and [Troubleshooting](docs/TROUBLESHOOTING.md) guides
- Search [existing issues](https://github.com/archilles/archilles/issues) to avoid duplicates

**When reporting a bug, include:**
- Clear, descriptive title
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, Archilles version)
- Error messages (full traceback if applicable)
- Sample data if relevant (anonymized)

### Suggesting Features

Feature requests are welcome! Open an issue with:
- Clear use case description
- Why this feature would be valuable
- Any alternative solutions you've considered
- Your willingness to contribute implementation

### Pull Requests

We welcome pull requests! Here's the process:

1. **Fork the repository**
   ```bash
   git clone https://github.com/archilles/archilles.git
   cd archilles
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Follow existing code style
   - Add tests if applicable
   - Update documentation

4. **Commit with clear messages**
   ```bash
   git commit -m "Feature: Add support for X"
   ```

5. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Development Setup

```bash
# Clone repository
git clone https://github.com/archilles/archilles.git
cd archilles

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Install development dependencies
pip install pytest black flake8
```

## Code Style

- **Python**: Follow PEP 8
- **Formatting**: Use `black` for code formatting
- **Linting**: Run `flake8` before committing
- **Type hints**: Encouraged but not required
- **Docstrings**: Use for public APIs

```bash
# Format code
black src/ scripts/

# Lint
flake8 src/ scripts/
```

## Testing

```bash
# Run tests
pytest

# Run specific test
pytest tests/test_calibre_db.py

# With coverage
pytest --cov=src tests/
```

## Documentation

- Update relevant documentation in `docs/`
- Update README.md if adding user-facing features
- Add docstrings for new functions/classes
- Include usage examples where helpful

## Areas for Contribution

### High Priority

- **Test coverage**: Unit tests for core components
- **Documentation**: Expand user guides, add examples
- **Bug fixes**: See [issues labeled "bug"](https://github.com/archilles/archilles/issues?q=is%3Aissue+is%3Aopen+label%3Abug)
- **Performance**: Profile and optimize slow operations

### Medium Priority

- **Format support**: Additional e-book formats
- **Language detection**: Improve accuracy
- **Chunking strategies**: Alternative approaches
- **UI/UX**: Command-line interface improvements

### Future Features

- **Annotations extraction**: PDF/EPUB highlights
- **Incremental indexing**: Update only changed books
- **Graph RAG**: Entity relationships
- **Web UI**: Browser-based interface

## Project Structure

```
archilles/
├── docs/              # Documentation
├── scripts/           # CLI scripts
│   └── rag_demo.py   # Main entry point
├── src/
│   ├── calibre_db.py      # Calibre integration
│   └── extractors/        # Text extraction
├── tests/             # Test suite
├── requirements.txt   # Dependencies
└── README.md         # Main documentation
```

## Commit Message Guidelines

Use clear, descriptive commit messages:

```
Feature: Add support for MOBI format
Fix: Correct page number extraction in PDFs
Docs: Update installation guide for Windows
Refactor: Simplify metadata extraction logic
Test: Add unit tests for BM25 indexing
```

## Release Process

(For maintainers)

1. Update version in `setup.py`
2. Update `CHANGELOG.md`
3. Tag release: `git tag -a v1.0.0 -m "Release v1.0.0"`
4. Push tag: `git push origin v1.0.0`
5. Create GitHub release with notes

## Questions?

- **General questions**: [GitHub Discussions](https://github.com/archilles/archilles/discussions)
- **Bugs/Features**: [GitHub Issues](https://github.com/archilles/archilles/issues)
- **Security**: [hello@archilles.org](mailto:hello@archilles.org)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to Archilles!** 🚀
