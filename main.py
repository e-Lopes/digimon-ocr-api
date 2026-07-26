"""Entrada do container Docker/Hugging Face.

A implementação vive em api/index.py, a mesma usada pela Vercel. Manter uma
única fonte evita divergências de modelo, prompt e normalização.
"""

from api.index import app

__all__ = ["app"]
