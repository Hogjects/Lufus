import sys


class StdoutRedirector:
    def __init__(self, log_fn):
        # redirect stdout to log window
        self._log_fn = log_fn
        self._real_stdout = sys.stdout
        self._buf = ""

    def write(self, text):
        # write to real stdout and buffer for logging :D
        self._real_stdout.write(text)
        self._buf += text
        while "\n" in self._buf:
            # split by newlines and log each line
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if line:
                self._log_fn(line)

    def flush(self):
        # flush the real stdout
        self._real_stdout.flush()

    def fileno(self):
        # return real stdout file descriptor
        return self._real_stdout.fileno()

    def isatty(self):
        # not a tty when redirected
        return False
