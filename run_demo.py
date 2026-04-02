import logging
import sys

from app.server import run

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    run(port=8000)
