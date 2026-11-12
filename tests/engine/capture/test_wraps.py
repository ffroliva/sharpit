"""The shared class-method wrap helper: idempotent, restores only its own wrapper, never raises into the host."""

from __future__ import annotations

import asyncio
import functools
import inspect
import threading
import time
from collections.abc import Callable
from typing import Any
from unittest import mock

import pytest

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
    assert asyncio.run(client().fetch(7)) == ("wrapped", 7)


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

    def slow(original: Callable[..., Any]) -> Callable[..., Any]:
        time.sleep(0.01)  # lets the threads interleave inside make, so only the lock keeps it to one wrapper
        return passthrough(original)

    def go() -> None:
        barrier.wait()
        results.append(wrap(client, "send", slow, tag="t"))

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r is not None for r in results) == 1
    assert client().send(1) == ("wrapped", 1)


class Wrapt:
    """A stand-in for a wrapt FunctionWrapper: callable, with a descriptor ``__get__`` that binds for itself."""

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return "wrapt"


@pytest.mark.parametrize(
    "make_entry",
    [
        lambda: mock.MagicMock(),
        lambda: len,
        lambda: functools.partial(int, "7"),
        lambda: Wrapt(),
        lambda: staticmethod(Wrapt()),
        lambda: classmethod(len),
    ],
    ids=["mock", "builtin", "partial", "wrapt-style", "static-over-wrapt", "classmethod-over-builtin"],
)
def test_a_non_function_callable_answers_none(make_entry: Callable[[], Any]) -> None:
    client = make_client()
    entry = make_entry()
    client.thing = entry  # type: ignore[attr-defined]
    assert wrap(client, "thing", passthrough, tag="t") is None
    assert client.__dict__["thing"] is entry


def test_a_wrapt_style_wrapper_answers_none_and_is_untouched() -> None:
    client = make_client()
    entry = Wrapt()
    client.send = entry  # type: ignore[method-assign,assignment]
    assert wrap(client, "send", passthrough, tag="t") is None
    assert client.__dict__["send"] is entry
    assert vars(entry) == {}
    assert client().send(1) == "wrapt"


def test_host_code_on_an_attribute_object_never_runs() -> None:
    calls: list[str] = []

    class Spy:
        def __getattr__(self, attr: str) -> Any:
            calls.append(attr)
            raise AttributeError(attr)

        @property
        def __class__(self) -> Any:  # type: ignore[override]
            calls.append("__class__")
            return Spy

        def __call__(self) -> None:
            return None

    client = make_client()
    client.spy = Spy()  # type: ignore[attr-defined]
    client.boxed = staticmethod(Spy())  # type: ignore[attr-defined]
    calls.clear()  # staticmethod() itself copies attributes off its argument
    assert wrap(client, "spy", passthrough, tag="t") is None
    assert wrap(client, "boxed", passthrough, tag="t") is None
    assert calls == []


def test_a_nested_class_answers_none() -> None:
    client = make_client()

    class Inner:
        pass

    client.Inner = Inner  # type: ignore[attr-defined]
    assert wrap(client, "Inner", passthrough, tag="t") is None
    assert client.__dict__["Inner"] is Inner


def test_a_property_answers_none() -> None:
    client = make_client()
    prop = property(lambda self: 1)
    client.prop = prop  # type: ignore[attr-defined]
    assert wrap(client, "prop", passthrough, tag="t") is None
    assert client.__dict__["prop"] is prop


def test_a_staticmethod_subclass_answers_none() -> None:
    class Sub(staticmethod):  # type: ignore[type-arg]
        pass

    client = make_client()
    entry = Sub(lambda x: x)
    client.sub = entry  # type: ignore[attr-defined]
    assert wrap(client, "sub", passthrough, tag="t") is None
    assert client.__dict__["sub"] is entry


def test_a_setattr_that_does_nothing_answers_none() -> None:
    class Silent(type):
        def __setattr__(cls, key: str, value: Any) -> None:
            return None

    class Quiet(metaclass=Silent):
        def send(self) -> int:
            return 1

    assert wrap(Quiet, "send", passthrough, tag="t") is None
    assert Quiet().send() == 1


def test_a_setattr_that_transforms_the_value_answers_none_and_restores_the_original() -> None:
    """Council r2 nit: a metaclass that stores something else must not leave the owner changed with no remover."""

    class Transforming(type):
        def __setattr__(cls, key: str, value: Any) -> None:  # replaces sharpit's wrapper, keeps anything else
            marked = "__sharpit_tag__" in getattr(value, "__dict__", {})
            super().__setattr__(key, (lambda self: "transformed") if marked else value)

    class Odd(metaclass=Transforming):
        def send(self) -> int:
            return 1

    original = Odd.__dict__["send"]
    assert wrap(Odd, "send", passthrough, tag="t") is None
    assert Odd.__dict__["send"] is original


def test_an_entry_whose_metaclass_defines_eq_runs_no_host_code() -> None:
    """Council r2 nit: classifying the entry never compares its type with ``==`` (a metaclass ``__eq__`` would run)."""
    calls: list[object] = []

    class Comparing(type):
        def __eq__(cls, other: object) -> bool:
            calls.append(other)
            return False

        __hash__ = type.__hash__

    class Odd(metaclass=Comparing):
        pass

    class Owner:
        send = Odd()

    assert wrap(Owner, "send", passthrough, tag="t") is None
    assert calls == []


def test_a_make_that_returns_the_function_itself_answers_none_and_stamps_nothing() -> None:
    client = make_client()
    original = client.__dict__["send"]
    assert wrap(client, "send", lambda func: func, tag="t") is None
    assert client.__dict__["send"] is original
    assert not hasattr(original, "__sharpit_original__")
    assert "__sharpit_tag__" not in vars(original)


def test_removing_the_inner_wrapper_first_leaves_the_outer_working() -> None:
    client = make_client()
    remove_a = wrap(client, "send", passthrough, tag="a")
    remove_b = wrap(client, "send", passthrough, tag="b")
    assert remove_a is not None
    assert remove_b is not None
    outer = client.__dict__["send"]
    assert remove_a() is False
    assert client.__dict__["send"] is outer
    assert client().send(1) == ("wrapped", ("wrapped", 1))
