from fastapi import FastAPI, Request, HTTPException


def setup_api_gateway_middleware(app: FastAPI) -> None:
    """
    Register API gateway concerns as FastAPI middlewares.

    - Rate limiting (placeholder)
    - Basic request validation (placeholder)
    - API key check (placeholder)
    - CORS headers (can be replaced/extended with FastAPI CORSMiddleware)
    """

    @app.middleware("http")
    async def api_gateway_middleware(request: Request, call_next):
        # TODO: plug in real implementations for:
        # - rate limiting
        # - structured input validation
        # - auth / API-key checking

        # Example API key check shell
        api_key = request.headers.get("X-API-Key")
        if api_key is not None and not _is_valid_api_key(api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")

        response = await call_next(request)

        # Minimal CORS header (replace with CORSMiddleware in production)
        response.headers.setdefault("Access-Control-Allow-Origin", "*")
        response.headers.setdefault(
            "Access-Control-Allow-Methods",
            "GET, POST, PUT, DELETE, OPTIONS",
        )
        return response


def _is_valid_api_key(api_key: str) -> bool:
    # Placeholder: plug in your real API-key validation here
    return True

