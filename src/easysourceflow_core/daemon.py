"""Command entrypoint for the EasySourceFlow daemon."""

from __future__ import annotations

import logging

from .config import load_settings
from .http_api import build_server


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    server = build_server(settings)
    logging.getLogger(__name__).info("easysourceflowd listening", extra={"base_url": settings.base_url})
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("easysourceflowd interrupted")
        pass
    finally:
        server.server_close()
        logging.getLogger(__name__).info("easysourceflowd stopped")


if __name__ == "__main__":
    main()
