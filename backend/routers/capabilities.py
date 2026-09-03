"""Runtime edition capabilities consumed by shared frontend surfaces."""

from fastapi import APIRouter

from edition import Edition, capability_payload


def build_router(edition: Edition) -> APIRouter:
    router = APIRouter(tags=["capabilities"])

    @router.get("/capabilities")
    def get_capabilities():
        return capability_payload(edition)

    return router
