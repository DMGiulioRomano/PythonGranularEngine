# Granular Synthesis Engine

A compositional system for granular synthesis based on Csound. The pipeline takes a high-level YAML configuration file and produces audio output through a two-stage process: Python generates a Csound score (`.sco`), which is then rendered by Csound into an audio file (`.aif`).

```
configs/*.yml  →  [Python]  →  generated/*.sco  →  [Csound]  →  output/*.aif
```

---

## System Requirements

The following tools must be installed on your system before running `make setup`.

### macOS

```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install python@3.12 sox csound
```

### Linux (Debian / Ubuntu)

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv sox csound
```

> **Note on Csound on Linux:** the version available via `apt` may be older than the one available on the [Csound website](https://csound.com/download.html). If you need a recent version, download the `.deb` package directly from the official releases.

### For tired Manjaro Users (and Arch Linux based)

```bash
curl -fsSL https://pyenv.run | bash
pyenv install 3.12
pyenv local 3.12
```

### Verify installation

```bash
make check-system-deps
```

This will exit with an error message for any missing dependency, telling you what to install.

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd <repo-name>

# 2. Install system dependencies (see above)

# 3. Setup Python virtual environment
make setup

# 4. Build the default file
make all

# 5. Build a specific config file
make FILE=my-config all
```

---

## Project Structure

```
.
├── Makefile                  # Main entry point
├── make/
│   ├── build.mk              # Build pipeline: YAML -> SCO -> AIF
│   ├── test.mk               # Virtual environment and pytest
│   ├── utils.mk              # Open files, git sync, RX stop
│   ├── audioFile.mk          # Audio file trimming via sox
│   └── clean.mk              # Cleanup targets
├── src/                      # Python source (score generator)
├── csound/
│   └── main.orc              # Csound orchestra
├── configs/                  # YAML composition files
├── refs/                     # Source audio samples
├── generated/                # Generated .sco files (intermediate)
├── output/                   # Rendered .aif files
├── logs/                     # Csound build logs
└── tests/                    # Pytest test suite
```

---

## Make Targets

### Setup

| Command | Description |
|---|---|
| `make setup` | Full project setup: checks system deps, creates directories, sets up venv |
| `make venv-setup` | Setup Python virtual environment only |
| `make install-system-deps` | Install Csound, sox, Python via package manager |
| `make check-system-deps` | Verify system dependencies are present |

### Build

| Command | Description |
|---|---|
| `make all` | Build pipeline for the default file (`FILE=test-lez`) |
| `make FILE=name all` | Build a specific config file from `configs/name.yml` |
| `make all TEST=true` | Build all `.yml` files in `configs/` |
| `make all STEMS=true FILE=name` | Build one yml into multiple separate stem files |

### Testing

| Command | Description |
|---|---|
| `make tests` | Run pytest test suite |
| `make tests-cov` | Run tests with HTML coverage report |

### Utility

| Command | Description |
|---|---|
| `make open` | Open generated `.aif` files |
| `make pdf` | Open generated PDF visualizations |
| `make sync COMMIT="message"` | Git add, commit, pull, push |
| `make rx-stop` | Quit iZotope RX 11 (macOS only) |
| `make venv-info` | Print Python/pip/pytest versions |

### Cleanup

| Command | Description |
|---|---|
| `make clean` | Remove all generated files (`.sco`, `.aif`, logs) |
| `make clean-all` | Full cleanup including virtual environment |
| `make venv-clean` | Remove virtual environment only |

---

## Build Flags

All flags can be passed on the command line and override defaults:

| Flag | Default | Description |
|---|---|---|
| `FILE` | `test-lez` | Config filename (without `.yml` extension) |
| `AUTOKILL` | `true` | Auto-quit iZotope RX 11 before build (macOS) |
| `AUTOPEN` | `true` | Auto-open output audio file after build |
| `AUTOVISUAL` | `true` | Generate PDF score visualization |
| `SHOWSTATIC` | `true` | Show static analysis output |
| `PRECLEAN` | `true` | Run `clean` before each build |
| `TEST` | `false` | Build all configs when `true` |
| `STEMS` | `false` | Split output into per-stream files when `true` |
| `SKIP` | `0.0` | Start time in seconds for audio trim (`audioFile.mk`) |
| `DURATA` | `30.0` | Duration in seconds for audio trim (`audioFile.mk`) |

Example:

```bash
make FILE=my-piece AUTOPEN=false PRECLEAN=false all
```

---

## Audio Sample Trimming

The `audioFile.mk` module provides a utility to extract a segment from a source sample in `refs/`:

```bash
make INPUT=001 SKIP=5.0 DURATA=20.0 001-5_0-20_0.wav
```

This calls `sox` to trim `refs/001.wav` starting at 5.0 seconds for 20 seconds, and saves the result back to `refs/`.

---

## Platform Support

| Platform | Status |
|---|---|
| macOS (Apple Silicon / Intel) | Supported |
| Linux (Debian / Ubuntu) | Supported |
| Windows (native) | Not supported |
| Windows (WSL2) | Should work, not tested |

The build system detects the OS at runtime via `uname -s` and adapts accordingly. On Linux, `iZotope RX 11` integration is disabled automatically.

---

## Python Dependencies

Python dependencies are managed via `pip` inside a virtual environment in `.venv/`. The environment is created automatically by `make setup` or `make venv-setup`. To update or reinstall:

```bash
make venv-reinstall   # clean venv and reinstall from requirements.txt
make venv-upgrade     # upgrade all packages to latest compatible versions
```

---

## Optional: Pin Python Version with mise or asdf

If you work across multiple machines or projects with different Python versions, a version manager is recommended. Create a `.tool-versions` file in the project root:

```
python 3.12.3
```

Then run `mise install` or `asdf install` to get exactly that version. See [mise.jdx.dev](https://mise.jdx.dev) or [asdf-vm.com](https://asdf-vm.com).
