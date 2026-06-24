import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication

from profitmap.db.session import init_database
from profitmap.ui.main_window import MainWindow


def main() -> int:
    load_dotenv()
    app = QApplication(sys.argv)
    app.setApplicationName("ProfitMap")
    app.setOrganizationName("ProfitMap")

    db_path = Path.home() / "profitmap.sqlite3"
    session_factory = init_database(db_path)

    window = MainWindow(session_factory=session_factory)
    if "--smoke-test" in sys.argv:
        print("ProfitMap smoke test ok")
        window.close()
        return 0

    window.resize(1440, 900)
    window.show()
    return app.exec()
