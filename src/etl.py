"""Compatibilidade com a fase 1: ``python src/etl.py`` continua funcionando.

A pipeline agora vive no pacote ``bcb_pipeline``; prefira::

    python -m bcb_pipeline executar
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bcb_pipeline.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["executar", *sys.argv[1:]]))
