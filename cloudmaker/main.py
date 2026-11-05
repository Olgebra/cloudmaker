"""Точка входа CloudMaker."""

from fastapi import FastAPI

from cloudmaker import __version__

app = FastAPI(title="CloudMaker", version=__version__)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def main() -> None:
    import os

    import uvicorn

    host = os.environ.get("CLOUDMAKER_HOST", "0.0.0.0")
    port = int(os.environ.get("CLOUDMAKER_PORT", "8000"))
    uvicorn.run("cloudmaker.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
