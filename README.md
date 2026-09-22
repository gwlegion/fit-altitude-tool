# FIT Altitude Tool 🛰️⛰️

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

**English** | [Français](README_FR.md)

**FIT Altitude Tool** is a standalone Windows desktop application designed to easily fix, enrich, and correct elevation data in `.FIT` activity files (Garmin, Amazfit, Wahoo, Coros, Strava, Suunto) using high-precision **Copernicus GLO-30 (COP30 30-meter DEM)** elevation data fetched via the **OpenTopography API**.

It preserves all original fitness metrics (heart rate, cadence, power, speed, timestamps) and only replaces or fixes missing/inaccurate elevation data in your GPS tracks.

---

## ✨ Features

- 📁 **Drag & Drop**: Easily drop `.fit` files or entire folders directly into the user interface.
- 🗺️ **High-Resolution Elevation (Copernicus COP30)**: Correct inaccurate barometric or GPS elevation data with official 30-meter global elevation models.
- ⚡ **Local SQLite Cache & Bilinear Interpolation**: GeoTIFF DEM tiles are cached locally (`%LOCALAPPDATA%\FITAltitudeTool\altitude_cache.db`). Exact elevation values are interpolated locally without redundant network requests.
- 🔑 **API Key Management**: Easy built-in guided setup for your free OpenTopography API key.
- 📦 **Standalone Windows Executable**: One-click `.exe` download with no Python installation required for end-users.

---

## 📥 Download Executable

You can download the pre-compiled **Windows `.exe`** binary directly from the **Releases** page on GitHub.

1. Download `FIT_Altitude_Tool.exe` from the latest release.
2. Double-click to launch (no installer required).

---

## 🔑 Getting an OpenTopography API Key

Accessing COP30 elevation data requires a free personal API key from **OpenTopography**:

1. Create a free account at [portal.opentopography.org](https://portal.opentopography.org/myopentopo).
2. Go to **MyOpenTopo** > **myTopography Authorizations / API Key**.
3. Generate your API key.
4. In **FIT Altitude Tool**, go to **Options > OpenTopography API Key...**, paste your key, and click **Save**.

> *Note: You can also export `OPENTOPO_API_KEY` as an environment variable.*

---

## 🚀 Development Setup

### Prerequisites
- **Python 3.10+**

### 1. Clone repository & install dependencies
```powershell
git clone https://github.com/votre-utilisateur/fit-altitude-tool.git
cd fit-altitude-tool

# Create a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Run Application
```powershell
python app.py
```

### 3. Build Windows Executable (`.exe`)
```powershell
.\build_exe.bat
```

---

## 🧪 Running Unit Tests

```powershell
py -m unittest discover tests
```

---

## �� Project Structure

```text
fit-altitude-tool/
├── app.py                 # Tkinter Application Entry Point
├── build_exe.bat          # PyInstaller Windows build script
├── FIT Altitude Tool.spec # PyInstaller configuration
├── requirements.txt       # Python dependencies
├── LICENSE                # MIT License
├── README.md              # Documentation (English)
├── README_FR.md           # Documentation (French)
├── src/                   # Core application source code
│   ├── __init__.py
│   ├── ui.py              # User Interface (Tkinter / TkinterDND)
│   ├── fit_processor.py   # FIT file reader, altitude updating & writer
│   ├── altitude_provider.py# OpenTopography API integration & bilinear interpolation
│   ├── cache.py           # Local SQLite storage & GeoTIFF tile management
│   └── settings.py        # User settings & configuration manager
└── tests/                 # Automated unit tests
    └── test_fit_processor.py
```

---

## 📜 License & Attributions

Distributed under the [MIT License](LICENSE).

- **Elevation Data**: Copernicus DEM GLO-30 provided by the European Space Agency (ESA).
- **API Service**: [OpenTopography](https://opentopography.org/).

