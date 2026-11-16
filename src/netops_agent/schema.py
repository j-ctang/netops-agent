"""Bind tools to a client and describe them as OpenAI-style function schemas."""

from __future__ import annotations

import functools
import inspect
import typing
from collections.abc import Callable
from typing import Any

from pydantic import create_model

from .client import MerakiClient


def bind(fn: Callable[..., Any], client: MerakiClient) -> Callable[..., Any]:
    """Return fn with the client argument filled in and removed from its signature."""
    hints = typing.get_type_hints(fn)
    sig = inspect.signature(fn)
    params = [p for name, p in sig.parameters.items() if name != "client"]

    @functools.wraps(fn)
    def wrapper(**kwargs: Any) -> Any:
        return fn(client, **kwargs)

    wrapper.__signature__ = sig.replace(  # type: ignore[attr-defined]
        parameters=[p.replace(annotation=hints[p.name]) for p in params],
        return_annotation=hints.get("return", sig.return_annotation),
    )
    wrapper.__annotations__ = {k: v for k, v in hints.items() if k != "client"}
    del wrapper.__wrapped__  # stop inspect from seeing the original signature
    return wrapper


def openai_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    fields = {
        name: (p.annotation, ... if p.default is inspect.Parameter.empty else p.default)
        for name, p in sig.parameters.items()
    }
    params = create_model(f"{fn.__name__}_args", **fields).model_json_schema()  # type: ignore[call-overload]
    params.pop("title", None)
    for prop in params.get("properties", {}).values():
        prop.pop("title", None)
    return {
        "type": "function",
        "function": {"name": fn.__name__, "description": (fn.__doc__ or "").strip(), "parameters": params},
    }
