# Contributing to Smart Screenshot Organizer

Thank you for your interest in contributing to Smart Screenshot Organizer!

We welcome contributions from developers of all experience levels. Whether you're fixing bugs, improving documentation, enhancing the interface, or introducing new features, your contributions are appreciated.

## Ways to Contribute

- Report bugs and suggest improvements.
- Fix existing GitHub issues.
- Improve documentation and installation instructions.
- Enhance screenshot classification and OCR accuracy.
- Improve the Streamlit dashboard and accessibility.
- Add automated tests.
- Suggest new features and supported languages.

## Getting Started

1. Browse the repository's GitHub Issues.
2. Look for issues labeled `good first issue` or `help wanted`.
3. Comment on the issue you'd like to work on.
4. Wait for maintainer feedback before beginning significant changes.
5. Fork the repository and create a dedicated feature branch.
6. Implement and test your changes.
7. Submit a pull request referencing the issue.

## Development Setup

**Requirements**

- Windows 10/11
- Python 3.12+
- Tesseract OCR
- Git

Clone your fork and open the project directory.

Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Verify your setup:

```powershell
python main.py check
python -m pytest -q
```

## Contribution Guidelines

- Keep changes focused on the relevant issue.
- Follow existing project conventions.
- Preserve existing functionality and backward compatibility.
- Add tests for new features and bug fixes.
- Avoid unnecessary dependencies.
- Maintain local-first screenshot processing.
- Do not introduce external services or upload OCR data without maintainer approval.
- Never commit personal screenshots, OCR history, databases, logs, credentials, or private paths.
- Use synthetic screenshots when demonstrating or testing changes.
- Preserve duplicate detection, filename collision protection, and privacy safeguards.
- Preserve manual dry-run defaults and copy-only background automation.
- Discuss changes involving file deletion, moving, or overwriting before implementation.

## Testing

Before submitting a pull request, run:

```powershell
python -m pytest -q
```

For relevant changes, also check:

- OCR and screenshot classification
- Filename generation
- Duplicate detection
- Folder monitoring
- Background processing
- Streamlit dashboard functionality

Test using synthetic data rather than personal screenshots.

## Pull Request Process

1. Create a descriptive branch name.
2. Make your changes.
3. Run the relevant tests.
4. Explain what changed and why.
5. Reference the related GitHub issue.
6. Include sanitized screenshots for visual changes.
7. Submit your pull request for maintainer review.

The maintainer may request changes before merging.

## Reporting Bugs

Please include:

- A clear description of the problem.
- Steps to reproduce it.
- Expected and actual behavior.
- Windows and Python versions.
- Relevant error messages with private details removed.

## Suggesting Features

Explain the problem, your proposed solution, and how the improvement would benefit users.

## Community Guidelines

Please communicate respectfully and constructively. Beginners and experienced developers are equally welcome.

## Maintainer

**Iqra Nawaz**

Thank you for helping make Smart Screenshot Organizer better!