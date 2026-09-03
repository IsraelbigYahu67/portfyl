"""Route manifest for owner-only features in the local edition."""

from fastapi import APIRouter

from routers.analytics import tax_report
from routers.market import stock_screener


router = APIRouter()
router.add_api_route(
    "/analytics/tax-report",
    tax_report,
    methods=["GET"],
    tags=["analytics"],
)
router.add_api_route(
    "/market/screener",
    stock_screener,
    methods=["GET"],
    tags=["market"],
)
