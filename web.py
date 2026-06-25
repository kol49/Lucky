import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


if __name__ == "__main__":
    uvicorn.run(
        "profitmap.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
