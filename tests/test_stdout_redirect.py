"""Tests for the thread-safe stdout redirect in archilles_service."""

import io
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from src.service.archilles_service import _redirect_stdout_to_stderr


def test_simple_redirect_restores_stdout():
    """Single sequential use restores stdout."""
    real = sys.stdout
    with _redirect_stdout_to_stderr():
        assert sys.stdout is sys.stderr
    assert sys.stdout is real


def test_nested_redirect_restores_only_at_outermost_exit():
    """Nested context managers restore only when the outermost exits."""
    real = sys.stdout
    with _redirect_stdout_to_stderr():
        assert sys.stdout is sys.stderr
        with _redirect_stdout_to_stderr():
            assert sys.stdout is sys.stderr
        # inner exit must NOT restore yet
        assert sys.stdout is sys.stderr
    assert sys.stdout is real


def test_parallel_redirect_restores_stdout():
    """
    Concurrent enters/exits across many threads must always restore the
    *real* stdout when the last holder exits — never leak the stderr value
    into sys.stdout permanently (regression test for bug_012).
    """
    real = sys.stdout
    barrier = threading.Barrier(8)

    def worker():
        # Force overlap between save/restore windows
        barrier.wait()
        with _redirect_stdout_to_stderr():
            # While inside, stdout must be diverted
            assert sys.stdout is sys.stderr
            # Tiny busy wait so multiple threads overlap
            for _ in range(1000):
                pass

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker) for _ in range(8)]
        for f in futures:
            f.result()

    # After all workers exit, sys.stdout MUST be the original stream,
    # never the stderr it was diverted to.
    assert sys.stdout is real


def test_repeated_parallel_rounds_keep_stdout_clean():
    """Many sequential rounds of parallel use must still leave stdout intact."""
    real = sys.stdout
    for _ in range(20):
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(lambda: _do_redirect()) for _ in range(4)
            ]
            for f in futures:
                f.result()
        assert sys.stdout is real


def _do_redirect():
    with _redirect_stdout_to_stderr():
        assert sys.stdout is sys.stderr


def test_exception_in_block_still_restores():
    """An exception inside the block must still restore stdout."""
    real = sys.stdout
    try:
        with _redirect_stdout_to_stderr():
            assert sys.stdout is sys.stderr
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert sys.stdout is real


def test_replacement_target_during_redirect_is_stderr():
    """While redirected, sys.stdout writes must land on stderr."""
    real = sys.stdout
    captured_stderr = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = captured_stderr
    try:
        with _redirect_stdout_to_stderr():
            sys.stdout.write("hello-from-rag\n")
        assert "hello-from-rag" in captured_stderr.getvalue()
    finally:
        sys.stderr = real_stderr
        # stdout must be back to the original stream regardless
        assert sys.stdout is real
