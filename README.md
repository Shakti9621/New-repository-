# PDF Viewer (Portable, Windows)

A small, offline PDF viewer. It runs from a single folder with no installation.

## Running it

1. Extract the `PDFViewer-Portable` folder anywhere (USB drive, Desktop, etc.).
2. Double-click `PDFViewer.exe`.
3. Press **Ctrl+O** to open a PDF, or drag a PDF onto the window.

No Python, no runtime, and no internet connection is needed.
Windows may show a SmartScreen warning because the program is unsigned. Click
**More info**, then **Run anyway**.

## Features

- Continuous scrolling, with previous / next page buttons and a page number box
- Zoom: Ctrl+= / Ctrl+-, Ctrl+mouse wheel, or the zoom menu (Fit width, Fit page, 50%-300%)
- Fullscreen: F11 (exit with Esc)
- Ctrl+Home / Ctrl+End jump to first / last page
- Links are not clickable in the viewer. Nothing is opened from inside a PDF.
- **Save cleaned copy** (Ctrl+Shift+S): saves a NEW PDF with all link annotations removed.
  You choose the file name. The original PDF is never changed.

Note: the cleaned copy removes every link annotation, including internal jumps such as
table-of-contents links, not only web links.

## Building the .exe yourself (no local installs)

The project is set up to build on GitHub's free Windows machines:

1. Create a free account at github.com and click **New repository**.
2. Upload all files in this folder, including the hidden `.github` folder.
   (If the browser skips `.github`, create the file `.github/workflows/build-windows.yml`
   manually and paste its contents.)
3. Open the **Actions** tab, enable workflows if asked, and click
   **Build Windows portable EXE → Run workflow**.
4. Wait about 5 minutes. Open the finished run and download the **PDFViewer-Portable** artifact.
5. Extract the zip. The folder contains `PDFViewer.exe` and `README.txt`.

## Project files

- `main.py`: the whole application (PySide6 interface, PyMuPDF rendering)
- `requirements.txt`: pinned dependencies
- `.github/workflows/build-windows.yml`: builds the portable Windows executable
