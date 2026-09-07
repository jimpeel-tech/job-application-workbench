from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager

ConnectionFactory = Callable[[], AbstractContextManager[sqlite3.Connection]]
