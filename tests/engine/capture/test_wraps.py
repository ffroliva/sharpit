"""The shared class-method wrap helper: idempotent, restores only its own wrapper, never raises into the host."""

from __future__ import annotations

import functools
import inspect
import threading
from collections.abc import Callable
from typing import Any

from sharpit.engine.capture.wraps import wrap


def passthrough(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return ("wrapped", original(*args, **kwargs))

    return wrapper


def make_client() -> type:
    class Client:
        def send(self, x: int) -> int:
            return x

        @staticmethod
        def ping(x: int) -> int:
            return x

        @classmethod
        def build(cls, x: int) -> tuple[str, int]:
            return (cls.__name__, x)

        async def fetch(self, x: int) -> int:
            return x

    return Client


def test_wrap_replaces_a_plain_method_and_the_remover_restores_it() -> None:
    client = make_client()
    original = client.__dict__["send"]
    remover = wrap(client, "send", passthrough, tag="t")
    assert remover is not None
    assert client().send(2) == ("wrapped", 2)
    assert client.__dict__["send"].__sharpit_original__ is original
    assert remover() is True
    assert client.__dict__["send"] is original


def test_the_same_tag_twice_wraps_once() -> None:
    client = make_client()
    assert wrap(client, "send", passthrough, tag="t") is not None
    first = client.__dict__["send"]
    assert wrap(client, "send", passthrough, tag="t") is None
    assert client.__dict__["send"] is first


def test_a_different_tag_wraps_again() -> None:
    client = make_client()
    original = client.__dict__["send"]
    assert wrap(client, "send", passthrough, tag="a") is not None
    remove_b = wrap(client, "send", passthrough, tag="b")
    assert remove_b is not None
    assert client().send(1) == ("wrapped", ("wrapped", 1))
    assert remove_b() is True
    assert client.__dict__["send"].__sharpit_original__ is original


def test_a_foreign_wrapper_installed_after_ours_is_left_alone() -> None:
    client = make_client()
    original = client.__dict__["send"]
    remover = wrap(client, "send", passthrough, tag="t")
    assert remover is not None
    assert hasattr(client.__dict__["send"], "__sharpit_original__")
    foreign = functools.wraps(client.__dict__["send"])(lambda self, x: ("foreign", x))  # copies our marker too
    client.send = foreign  # type: ignore[method-assign]
    assert remover() is False
    assert client.__dict__["send"] is foreign
    assert original is not foreign


def test_wrapping_over_a_foreign_wrapper_restores_the_foreign_one() -> None:
    client = make_client()

    def foreign(self: Any, x: int) -> tuple[str, int]:
        return ("foreign", x)

    client.send = foreign  # type: ignore[method-assign]
    remover = wrap(client, "send", passthrough, tag="t")
    assert remover is not None
    assert client().send(3) == ("wrapped", ("foreign", 3))
    assert remover() is True
    assert client.__dict__["send"] is foreign


def test_a_foreign_wrapper_copying_our_marker_is_not_taken_for_ours() -> None:
    client = make_client()
    assert wrap(client, "send", passthrough, tag="t") is not None
    assert hasattr(client.__dict__["send"], "__sharpit_original__")
    client.send = functools.wraps(client.__dict__["send"])(lambda self, x: ("foreign", x))  # type: ignore[method-assign]
    assert wrap(client, "send", passthrough, tag="t") is not None


def test_an_inherited_attribute_answers_none_and_leaves_both_classes() -> None:
    client = make_client()
    child = type("Child", (client,), {})
    assert wrap(child, "send", passthrough, tag="t") is None
    assert "send" not in child.__dict__
    assert client().send(1) == 1


def test_a_missing_attribute_answers_none() -> None:
    assert wrap(make_client(), "nope", passthrough, tag="t") is None


def test_a_staticmethod_stays_a_staticmethod() -> None:
    client = make_client()
    remover = wrap(client, "ping", passthrough, tag="t")
    assert remover is not None
    assert isinstance(client.__dict__["ping"], staticmethod)
    assert client.ping(4) == ("wrapped", 4)
    assert client().ping(4) == ("wrapped", 4)
    assert wrap(client, "ping", passthrough, tag="t") is None
    assert remover() is True
    assert client.ping(4) == 4


def test_a_classmethod_stays_a_classmethod() -> None:
    client = make_client()
    remover = wrap(client, "build", passthrough, tag="t")
    assert remover is not None
    assert isinstance(client.__dict__["build"], classmethod)
    assert client.build(5) == ("wrapped", ("Client", 5))
    assert wrap(client, "build", passthrough, tag="t") is None
    assert remover() is True
    assert client.build(5) == ("Client", 5)


def test_an_async_method_stays_a_coroutine_function() -> None:
    client = make_client()

    def make_async(original: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return ("wrapped", await original(*args, **kwargs))

        return wrapper

    assert wrap(client, "fetch", make_async, tag="t") is not None
    assert hasattr(client.__dict__["fetch"], "__sharpit_original__")
    assert inspect.iscoroutinefunction(client.__dict__["fetch"])


def test_a_c_type_answers_none_without_raising() -> None:
    assert wrap(int, "__add__", passthrough, tag="t") is None
    assert wrap(dict, "get", passthrough, tag="t") is None


def test_a_type_that_refuses_setattr_answers_none() -> None:
    class Locked(type):
        def __setattr__(cls, key: str, value: Any) -> None:
            raise TypeError("locked")

    class Closed(metaclass=Locked):
        def send(self) -> int:
            return 1

    original = Closed.__dict__["send"]
    assert wrap(Closed, "send", passthrough, tag="t") is None
    assert Closed.__dict__["send"] is original


def test_a_make_that_raises_answers_none_and_leaves_the_owner() -> None:
    client = make_client()
    original = client.__dict__["send"]

    def boom(_original: Callable[..., Any]) -> Callable[..., Any]:
        raise RuntimeError("no")

    assert wrap(client, "send", boom, tag="t") is None
    assert client.__dict__["send"] is original


def test_the_remover_twice_is_harmless() -> None:
    client = make_client()
    original = client.__dict__["send"]
    remover = wrap(client, "send", passthrough, tag="t")
    assert remover is not None
    assert remover() is True
    assert remover() is False
    assert client.__dict__["send"] is original


def test_two_threads_wrapping_at_once_end_with_one_wrapper() -> None:
    client = make_client()
    barrier = threading.Barrier(8)
    results: list[Any] = []

    def go() -> None:
        barrier.wait()
        results.append(wrap(client, "send", passthrough, tag="t"))

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r is not None for r in results) == 1
    assert client().send(1) == ("wrapped", 1)
