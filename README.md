# gdb-natvis
This implements [Natvis](https://msdn.microsoft.com/en-us/library/jj620914.aspx) based pretty printing in GDB.
GDB exposes a python API for writing pretty printers of certain types which is used by this project.

This project will allow creating custom pretty printers for GDB without having to write and deploy python code
for every type. It will also allow using the existing visualizers written for Visual Studio without changes.

## Dependencies
- GDB built with Python 3.6
- libclang (tested with version 5.0) with Python bindings

## Installation
Clone this repository somewhere and add the following to your `.gdbinit`:
```python
python
sys.path.insert(0, "/path/to/gdb-natvis/src")
try:
    import printer
except ImportError:
    printer = None
    import traceback
    traceback.print_exc()
else:
    printer.add_natvis_printers()
end
```

This will automatically try to load natvis files if GDB tries to pretty-print a type. The auto-discovery of natvis
files works by determining the file of the type being printed and then examining every parent directory for `.natvis`
files. This will obviously not work in all cases so this also adds a `add-nativs` command to GDB.

This command can be called with the path to one or more `.natvis` files which will then be loaded and used by subsequent
pretty printing operations.

## Supported Features
This already supports a wide array of features available in the Natvis system:
- Type name matching with template parameters (including wildcards)
- `DisplayString` with embedded expressions. Format specifiers are parsed but not used at the moment
- `Condition` for most XML elements
- Most `Expand` items are supported
  - `Item` is fully supported
  - `ArrayItems` is supported for the simple case (`Size` and `ValuePointer`)
  - `IndexListItems` including `$i` parameters
  - `ExpandedItem`
  - Limited support for `Synthetic`. Only the display string part is supported since synthetic items are not possible
  with the current GDB API

## Known issues
- The expression parser does not support all syntax elements yet
- Global variables are not resolved
- GDB issue: MI clients (such as CDT or CLion) do not receive the `to_string` value of a python pretty printer. This hides the `DisplayString` value since that uses `to_string`. As a workaround, the display string is added as a child instead. There is a GDB patch that fixes this issue: https://sourceware.org/bugzilla/show_bug.cgi?id=11335
