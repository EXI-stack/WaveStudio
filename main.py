import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from ui_components import WaveStudioWindow


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = WaveStudioWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()