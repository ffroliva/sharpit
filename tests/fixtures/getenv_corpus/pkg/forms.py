import os
from os import environ, getenv

A = os.getenv("FORM_A", "default-a")
B = os.environ.get("FORM_B")
C = os.environ["FORM_C"]
D = environ.get("FORM_D", "default-d")
F = getenv("FORM_E")

dynamic = "X"
IGNORED = os.getenv(dynamic)
NON_LITERAL_DEFAULT = os.getenv("FORM_F", str(1 + 1))
