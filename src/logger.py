# This exposes a function which writes to the GDB log if available and to stdout otherwise
try:
    from gdb import write
    import gdb


    def log_message(msg: str):
        write(str(msg) + "\n", gdb.STDLOG)
except ImportError:
    def log_message(msg: str):
        print(msg)
