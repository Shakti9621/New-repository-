"""
PDF Viewer - portable Windows PDF viewer built with PySide6 (Qt) and PyMuPDF.

* Pages are rendered as images, and the viewer has no click handling for
  links, so hyperlinks inside the document can never be followed.
* "Save cleaned copy" writes a NEW PDF with link annotations removed.
  The original file is never modified.
"""
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QScrollArea, QSpinBox, QStatusBar, QToolBar,
    QVBoxLayout, QWidget,
)

GAP = 14
ZOOM_CHOICES = ["Fit width", "Fit page", "50%", "75%", "100%", "125%", "150%", "200%", "300%"]


class PdfView(QScrollArea):
    """Continuous-scroll page view with lazy page rendering."""

    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.zoom = 1.0
        self.fit_mode = None
        self.labels = []
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background: #4a4a4a; border: none; }")
        self.container = QWidget()
        self.column = QVBoxLayout(self.container)
        self.column.setContentsMargins(GAP, GAP, GAP, GAP)
        self.column.setSpacing(GAP)
        self.setWidget(self.container)
        self.verticalScrollBar().valueChanged.connect(self._update_visible)

    # ---------- loading ----------
    def load(self, data, password=None):
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.needs_pass and not (password and doc.authenticate(password)):
            doc.close()
            raise PermissionError("password required")
        self._clear()
        self.doc = doc
        for _ in range(len(doc)):
            lbl = QLabel()
            lbl.setStyleSheet("background: white;")
            self.column.addWidget(lbl, 0, Qt.AlignmentFlag.AlignHCenter)
            self.labels.append(lbl)
        self.set_fit("width")

    def _clear(self):
        while self.column.count():
            item = self.column.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.labels = []
        if self.doc is not None:
            self.doc.close()
            self.doc = None

    # ---------- zoom ----------
    def set_fit(self, mode):
        self.fit_mode = mode
        self._apply_fit()

    def set_zoom(self, zoom):
        self.fit_mode = None
        self._set_zoom(zoom)

    def zoom_by(self, factor):
        self.set_zoom(self.zoom * factor)

    def _fit_zoom(self):
        r = self.doc[0].rect
        avail_w = self.viewport().width() - 2 * GAP - 2
        z = avail_w / r.width
        if self.fit_mode == "page":
            avail_h = self.viewport().height() - 2 * GAP - 2
            z = min(z, avail_h / r.height)
        return z

    def _apply_fit(self):
        if self.doc is not None and self.fit_mode:
            self._set_zoom(self._fit_zoom())

    def _set_zoom(self, zoom):
        if self.doc is None:
            return
        anchor = self.current_page()
        self.zoom = max(0.1, min(zoom, 6.0))
        for i, lbl in enumerate(self.labels):
            r = self.doc[i].rect
            lbl.setPixmap(QPixmap())
            lbl.setFixedSize(max(1, int(r.width * self.zoom)), max(1, int(r.height * self.zoom)))
        self.column.invalidate()
        QTimer.singleShot(0, lambda: self._restore(anchor))

    def _restore(self, anchor):
        self.go_to(anchor)
        self._update_visible()

    # ---------- navigation ----------
    def current_page(self):
        if not self.labels:
            return 0
        probe = self.verticalScrollBar().value() + self.viewport().height() // 3
        for i, lbl in enumerate(self.labels):
            if lbl.geometry().bottom() >= probe:
                return i
        return len(self.labels) - 1

    def go_to(self, index):
        if not self.labels:
            return
        index = max(0, min(index, len(self.labels) - 1))
        self.verticalScrollBar().setValue(max(0, self.labels[index].geometry().top() - GAP))

    # ---------- rendering ----------
    def _update_visible(self):
        if not self.labels:
            return
        vh = self.viewport().height()
        top = self.verticalScrollBar().value()
        lo, hi = top - vh, top + 2 * vh  # keep about two screens rendered
        for i, lbl in enumerate(self.labels):
            g = lbl.geometry()
            near = g.bottom() >= lo and g.top() <= hi
            pm = lbl.pixmap()
            loaded = pm is not None and not pm.isNull()
            if near and not loaded:
                self._render(i)
            elif not near and loaded:
                lbl.setPixmap(QPixmap())  # free memory for far-away pages
        self.page_changed.emit(self.current_page())

    def _render(self, index):
        dpr = self.devicePixelRatioF()
        scale = self.zoom * dpr
        pix = self.doc[index].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = QImage(pix.samples, pix.width, pix.height, pix.stride,
                       QImage.Format.Format_RGB888).copy()
        pm = QPixmap.fromImage(image)
        pm.setDevicePixelRatio(dpr)
        self.labels[index].setPixmap(pm)

    # ---------- events ----------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode:
            self._apply_fit()

    def wheelEvent(self, event):
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and self.doc is not None:
            self.zoom_by(1.1 if event.angleDelta().y() > 0 else 1 / 1.1)
            event.accept()
        else:
            super().wheelEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Viewer")
        self.resize(1100, 800)
        self.path = None
        self.raw = None
        self.password = None
        self._syncing = False

        self.view = PdfView()
        self.setCentralWidget(self.view)
        self.view.page_changed.connect(self._on_page_changed)
        self.setAcceptDrops(True)

        bar = QToolBar("Main")
        bar.setMovable(False)
        self.addToolBar(bar)
        self._action(bar, "Open...", "Ctrl+O", self.open_dialog)
        bar.addSeparator()
        self._action(bar, "< Prev", None, lambda: self.view.go_to(self.view.current_page() - 1))
        self.spin = QSpinBox()
        self.spin.setRange(1, 1)
        self.spin.setEnabled(False)
        self.spin.valueChanged.connect(self._spin_changed)
        bar.addWidget(self.spin)
        self.total = QLabel(" / 0 ")
        bar.addWidget(self.total)
        self._action(bar, "Next >", None, lambda: self.view.go_to(self.view.current_page() + 1))
        self._action(bar, "First", "Ctrl+Home", lambda: self.view.go_to(0))
        self._action(bar, "Last", "Ctrl+End", lambda: self.view.go_to(len(self.view.labels) - 1))
        bar.addSeparator()
        self._action(bar, "Zoom -", "Ctrl+-", lambda: self.view.zoom_by(1 / 1.25))
        self._action(bar, "Zoom +", "Ctrl+=", lambda: self.view.zoom_by(1.25))
        self.zoom_box = QComboBox()
        self.zoom_box.addItems(ZOOM_CHOICES)
        self.zoom_box.activated.connect(self._zoom_chosen)
        bar.addWidget(self.zoom_box)
        bar.addSeparator()
        self._action(bar, "Fullscreen", "F11", self.toggle_fullscreen)
        self._action(bar, "Save cleaned copy...", "Ctrl+Shift+S", self.save_clean_copy)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.exit_fullscreen)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Open a PDF with Ctrl+O, or drag one onto this window.")

    def _action(self, bar, text, shortcut, slot):
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        bar.addAction(act)
        self.addAction(act)  # keep shortcuts working even if the toolbar is hidden
        return act

    # ---------- opening ----------
    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF files (*.pdf)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            data = Path(path).read_bytes()
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not read file:\n{e}")
            return
        password = None
        while True:
            try:
                self.view.load(data, password)
                break
            except PermissionError:
                password, ok = QInputDialog.getText(
                    self, "Password required", "This PDF is password protected:",
                    QLineEdit.EchoMode.Password)
                if not ok:
                    return
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not open PDF:\n{e}")
                return

        self.path, self.raw, self.password = Path(path), data, password
        self.setWindowTitle(f"{self.path.name} - PDF Viewer")
        n = len(self.view.labels)
        self._syncing = True
        self.spin.setRange(1, n)
        self.spin.setValue(1)
        self.spin.setEnabled(True)
        self._syncing = False
        self.total.setText(f" / {n} ")

    def dragEnterEvent(self, event):
        if any(u.toLocalFile().lower().endswith(".pdf") for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.open_path(urls[0].toLocalFile())

    # ---------- navigation / view state ----------
    def _spin_changed(self, value):
        if not self._syncing:
            self.view.go_to(value - 1)

    def _on_page_changed(self, index):
        self._syncing = True
        self.spin.setValue(index + 1)
        self._syncing = False
        n = len(self.view.labels)
        if n:
            self.status.showMessage(
                f"Page {index + 1} of {n}      Zoom {round(self.view.zoom * 100)}%")

    def _zoom_chosen(self, index):
        text = self.zoom_box.itemText(index)
        if text == "Fit width":
            self.view.set_fit("width")
        elif text == "Fit page":
            self.view.set_fit("page")
        else:
            self.view.set_zoom(int(text.rstrip("%")) / 100)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    # ---------- cleaned copy ----------
    def save_clean_copy(self):
        if self.raw is None:
            QMessageBox.information(self, "No file", "Open a PDF first.")
            return
        suggested = str(self.path.with_name(f"{self.path.stem}_no_links.pdf"))
        out, _ = QFileDialog.getSaveFileName(
            self, "Save cleaned copy as", suggested, "PDF files (*.pdf)")
        if not out:
            return
        out_path = Path(out)
        if out_path.suffix.lower() != ".pdf":
            out_path = out_path.with_suffix(".pdf")
        if out_path.resolve() == self.path.resolve():
            QMessageBox.warning(
                self, "Refused",
                "Choose a different file name. The original PDF is never overwritten.")
            return
        removed = 0
        try:
            doc = fitz.open(stream=self.raw, filetype="pdf")
            if doc.needs_pass:
                doc.authenticate(self.password or "")
            for page in doc:
                for link in page.get_links():
                    page.delete_link(link)
                    removed += 1
            doc.save(str(out_path), garbage=3, deflate=True)
            doc.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save cleaned copy:\n{e}")
            return
        QMessageBox.information(
            self, "Saved",
            f"Removed {removed} link annotation(s).\n\n"
            f"Cleaned copy: {out_path}\nOriginal file: unchanged.")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        win.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
