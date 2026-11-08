"""HTTP surface: the JSON API and the static pages.

`Settings` and `create_app` load lazily, so the context routers can import `riso.api.deps`
without importing the app factory, which imports them."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from riso.api.app import Settings, create_app

__all__ = ["Settings", "create_app"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from riso.api import app

        return getattr(app, name)
    raise AttributeError(f"module 'riso.api' has no attribute {name!r}")
