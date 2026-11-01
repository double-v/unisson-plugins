"""Petits outils partagés des tests."""

import asyncio
import socket
import time


async def attendre(condition, delai: float = 3.0):
    fin = time.monotonic() + delai
    while not condition():
        if time.monotonic() > fin:
            raise AssertionError("condition jamais remplie")
        await asyncio.sleep(0.01)


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
