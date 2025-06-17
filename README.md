# ConnectionBreaker

<p align="center">
  <img src="https://github.com/user-attachments/assets/ae6d5ab4-f152-4dd8-866f-e0a0820fa75b" alt="ConnectionBreaker Logo" width="150"/>
</p>

<h3 align="center">A slick utility to selectively sever network connections for any running process.</h3>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Qt-6-green.svg" alt="Qt Version">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
</p>

---

ConnectionBreaker is a lightweight yet powerful tool for Windows designed to give you precise control over your applications' network access. With a single hotkey press, you can instantly terminate all network connections of a pre-selected application. It's perfect for gamers who need to create a solo public lobby, developers testing connection-loss scenarios, or anyone needing to firewall an app on the fly without complex rules.

## Features

- **Selective Connection Severing**: Target any running process and terminate its network connections without affecting other applications.
- **Global Hotkey**: Set a custom global hotkey to trigger the connection cut instantly, even when the app is minimized.
- **Process Picker**: An easy-to-use dialog to find and select the target application from a list of currently running processes.
- **System Tray Integration**: Runs discreetly in the system tray, staying out of your way until you need it.
- **Slick UI**: A modern, clean interface built with PyQt6, featuring a custom title bar and a dynamic video background.
- **Lightweight & Portable**: Packaged into a single executable, requiring no installation.

## Technology Stack

ConnectionBreaker is built with Python and leverages several powerful libraries:

- **Programming Language**: [Python 3](https://www.python.org/)
- **GUI Framework**: [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) for the user interface.
- **System Interaction**:
    - [psutil](https://github.com/giampaolo/psutil): For fetching the list of running processes.
    - [pygetwindow](https://github.com/asweigart/pygetwindow): For window management.
    - [keyboard](https://github.com/boppreh/keyboard): For capturing global hotkeys.
- **Core Functionality**:
    - The app dynamically uses [cports.exe (CurrPorts)](https://www.nirsoft.net/utils/cports.html) by NirSoft, a command-line utility to view and close TCP/IP connections. This tool is bundled with the application.
- **Packaging**: [PyInstaller](https://pyinstaller.org/en/stable/) is used to package the application into a standalone executable.

## How to Use

1.  **Download the latest release** from the [Releases](https://github.com/depressedamaged/ConnectionBreaker/releases) page.
2.  Unzip the archive.
3.  Run `ConnectionBreaker.exe`.
4.  The first time you run it, you may be prompted by your firewall. Ensure you allow it access.
5.  Click the "Select Process" button to choose the application you want to target (e.g., `GTA5.exe`).
6.  Click on the hotkey text to set a new global hotkey.
7.  Minimize the application. It will continue running in the system tray.
8.  Press your configured hotkey to sever the network connections for the selected process.

## How to Build from Source

If you want to build the project yourself, follow these steps:

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/depressedamaged/ConnectionBreaker.git
    cd ConnectionBreaker
    ```

2.  **Create a virtual environment:**
    ```sh
    python -m venv venv
    venv\Scripts\activate
    ```

3.  **Install dependencies:**
    The project dependencies are located in `source/requirements.txt`.
    ```sh
    pip install -r source/requirements.txt
    ```

4.  **Run the application from source:**
    ```sh
    python source/src/main.py
    ```

5.  **Build the executable:**
    The project uses PyInstaller. The spec file `ConnectionBreaker.spec` is already configured. It properly bundles the `cports.exe` utility and the `icon.ico` from the `assets` folder.
    ```sh
    pyinstaller ConnectionBreaker.spec
    ```
    The final standalone executable will be located in the `dist/` directory.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 