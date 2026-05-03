"""Run the full UUV simulation test suite."""

from __future__ import annotations

import sys
import unittest


def main() -> int:
    """Discover and run all tests under the tests directory."""
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    if result.wasSuccessful():
        print("\nCompletion: PASS")
        return 0
    print("\nCompletion: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
