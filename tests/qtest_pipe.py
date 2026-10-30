"""One reply from qtest on a pipe, within a timeout.  select() takes no pipe on Windows, so a thread waits."""

import threading


def read_reply(stream, timeout: float) -> str:
    lines = []
    reader = threading.Thread(target=lambda: lines.append(stream.readline()), daemon=True)
    reader.start()
    reader.join(timeout)
    assert lines, "QEMU qtest timed out"
    return lines[0].decode().strip()
