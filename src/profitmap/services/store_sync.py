from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from profitmap.db.models import Product
from profitmap.services.inventory import calculate_supply_summary

LOGGER = logging.getLogger(__name__)


def store_sync_enabled() -> bool:
    return bool(os.getenv("STORE_STOCK_SYNC_URL") and os.getenv("STORE_STOCK_SYNC_TOKEN"))


def stock_for_product(product: Product) -> int:
    has_supplies = bool(product.supplies)
    if has_supplies:
        return max(calculate_supply_summary(product).remaining_quantity, 0)
    return max(int(product.stock or 0), 0)


def stock_item_for_product(product: Product) -> dict[str, Any] | None:
    sku = (product.sku or "").strip()
    if not sku:
        return None
    return {"sku": sku, "stock": stock_for_product(product)}


def sync_products_to_store(products: list[Product]) -> dict[str, Any]:
    items = [item for product in products if (item := stock_item_for_product(product))]
    return sync_stock_items_to_store(items)


def sync_product_to_store(product: Product) -> dict[str, Any]:
    item = stock_item_for_product(product)
    return sync_stock_items_to_store([item] if item else [])


def sync_stock_items_to_store(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {"ok": True, "skipped": "no_items"}
    if not store_sync_enabled():
        return {"ok": False, "skipped": "not_configured"}

    url = os.environ["STORE_STOCK_SYNC_URL"]
    token = os.environ["STORE_STOCK_SYNC_TOKEN"]
    timeout = float(os.getenv("STORE_STOCK_SYNC_TIMEOUT", "8"))
    payload = json.dumps({"items": items}).encode("utf-8")
    request = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ProfitMap/0.1 stock-sync",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {"ok": True}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        LOGGER.warning("Store stock sync failed with HTTP %s: %s", exc.code, detail)
        return {"ok": False, "status": exc.code, "error": detail}
    except (OSError, URLError, TimeoutError) as exc:
        LOGGER.warning("Store stock sync failed: %s", exc)
        return {"ok": False, "error": str(exc)}
