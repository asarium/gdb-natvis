# This exposes a function which writes to the GDB log if available and to stdout otherwise
try:
    import gdb


    def log_message(msg: str):
        gdb.write(msg + "\n", gdb.STDLOG)
except ImportError:
    def log_message(msg: str):
        print(msg)
