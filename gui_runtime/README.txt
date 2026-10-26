Local Tk font support

The _tkinter CPython 3.11 extension was copied from an already installed local
CPython 3.11 environment's lib/python3.11/lib-dynload/ directory.
It is unchanged and uses the system libtk8.6.so and libtcl8.6.so. Ubuntu's Tk
supports Xft/fontconfig and the installed Noto CJK fonts; the standalone Python
runtime's bundled Tk did not support those fonts.

The playback environment remains independent of Conda. Only this local extension
is loaded, using the same CPython 3.11 ABI; no source environment paths are needed
at runtime. If this extension or its system libraries are unavailable, the GUI
falls back to Python's bundled Tk. Headless runs do not load the GUI.

The extension is part of CPython and covered by the Python license in this folder.
