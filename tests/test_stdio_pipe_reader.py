"""The stdio loop must not park in a blocking read on Windows.

Observed 2026-10-25: the model-preload thread started at 10:54:55 and was
still inside an import 3.5 hours later. A thread blocked in the C runtime's
read() on stdin holds that descriptor's lock; scipy's Fortran runtime,
loaded through sentence-transformers, makes a CRT call on stdin and waited
for the next request to release it. The reader peeks first and reads
through the Win32 handle, so the descriptor is never held.
"""

import os
import sys
import threading
import time

import pytest

import mcp_server

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows pipes")


@pytest.fixture
def pipe():
    import msvcrt

    r, w = os.pipe()
    yield r, w, mcp_server._PipeLineReader(msvcrt.get_osfhandle(r))
    for fd in (r, w):
        try:
            os.close(fd)
        except OSError:
            pass


def _readline_in_thread(reader):
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("line", reader.readline()), daemon=True)
    t.start()
    return t, out


class TestPipeLineReader:
    def test_two_lines_in_one_write_come_out_one_by_one(self, pipe):
        r, w, reader = pipe
        os.write(w, b'{"id": 0}\n{"id": 1}\n')

        assert reader.readline() == '{"id": 0}\n'
        assert reader.readline() == '{"id": 1}\n'

    def test_a_line_split_across_writes_is_joined(self, pipe):
        r, w, reader = pipe
        word = "Straßengewalt".encode("utf-8")
        cut = word.index(b"\xc3") + 1  # inside the two bytes of "ß"
        t, out = _readline_in_thread(reader)

        os.write(w, word[:cut])
        time.sleep(0.2)
        os.write(w, word[cut:] + b"\n")
        t.join(2)

        assert out["line"] == "Straßengewalt\n"

    def test_a_closed_pipe_ends_with_the_rest_then_empty(self, pipe):
        r, w, reader = pipe
        os.write(w, b"tail")
        os.close(w)

        assert reader.readline() == "tail"
        assert reader.readline() == ""

    def test_waiting_for_input_leaves_the_descriptor_free(self, pipe):
        r, w, reader = pipe
        waiting, _ = _readline_in_thread(reader)
        time.sleep(0.3)

        def crt_call():
            try:
                os.lseek(r, 0, os.SEEK_CUR)  # blocked behind a pending read()
            except OSError:
                pass  # a pipe cannot seek; returning at all is the point

        probe = threading.Thread(target=crt_call, daemon=True)
        probe.start()
        probe.join(2)
        os.write(w, b"\n")
        waiting.join(2)

        assert not probe.is_alive(), "a CRT call on stdin waited for the reader"


class TestStdinLineReader:
    def test_a_pipe_gets_the_polling_reader(self, pipe):
        r, w, _ = pipe
        with os.fdopen(os.dup(r), "rb") as stream:
            assert isinstance(mcp_server._stdin_line_reader(stream), mcp_server._PipeLineReader)

    def test_a_stream_without_a_descriptor_is_kept(self):
        class Fake:
            def readline(self):
                return ""

        fake = Fake()
        assert mcp_server._stdin_line_reader(fake) is fake
