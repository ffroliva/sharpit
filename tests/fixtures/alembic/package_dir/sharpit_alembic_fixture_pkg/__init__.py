"""Importing this package is a test failure: sharpit must resolve ``package:dir`` without importing it."""

raise RuntimeError("sharpit imported the migrations package")
