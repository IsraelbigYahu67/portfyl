"""Route manifest for owner-only features in the local edition."""

from fastapi import APIRouter

from routers.analytics import tax_report
from routers.market import (
    cancel_screener_job,
    create_screener_job,
    get_screener_job,
    stock_screener,
)


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
router.add_api_route(
    "/market/screener/jobs",
    create_screener_job,
    methods=["POST"],
    tags=["market"],
    status_code=202,
)
router.add_api_route(
    "/market/screener/jobs/{job_id}",
    get_screener_job,
    methods=["GET"],
    tags=["market"],
)
router.add_api_route(
    "/market/screener/jobs/{job_id}",
    cancel_screener_job,
    methods=["DELETE"],
    tags=["market"],
)
