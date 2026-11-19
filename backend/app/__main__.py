"""`python -m app`: serve API + built frontend on loopback only (SPEC §3, §5.5)."""

import os

import uvicorn

HOST = "127.0.0.1"  # deliberately not configurable: this app is for local use only
PORT = int(os.environ.get("DIAGRAMMA_PORT", "8787"))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT)
