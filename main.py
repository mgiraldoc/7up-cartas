from __future__ import annotations

import asyncio
import sys

from src.main import main, main_async


if sys.platform == "emscripten":
    asyncio.run(main_async())
else:
    main()
