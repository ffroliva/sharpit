import pytest

from sharpit.fastapi.signals import dev_server_signal

UVICORN = "C:/venv/Lib/site-packages/uvicorn/__main__.py"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([UVICORN, "m:app", "--reload"], "uvicorn --reload"),
        ([UVICORN, "m:create_app", "--factory", "--reload", "--port", "8001"], "uvicorn --reload"),
        ([UVICORN, "m:app", "--reload", "--workers", "2"], "uvicorn --reload"),
        ([UVICORN, "m:app", "--workers", "2"], None),
        (["fastapi", "dev", "main.py"], "fastapi dev"),
        (["C:\\venv\\Scripts\\fastapi.exe", "dev"], "fastapi dev"),
        (["fastapi", "run", "main.py"], None),
        (["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "m:app"], None),
        (["main.py"], None),  # programmatic uvicorn.run(reload=True) is not detected (spec 7.4)
        (["C:/venv/Lib/site-packages/fastapi/__main__.py", "dev"], "fastapi dev"),  # python -m fastapi dev
        ([], None),
    ],
)
def test_dev_server_signal(argv: list[str], expected: str | None):
    assert dev_server_signal(argv) == expected
