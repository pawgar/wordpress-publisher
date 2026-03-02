import sys

try:
    from tkinterdnd2 import TkinterDnD
    root = TkinterDnD.Tk()
except ImportError:
    import tkinter as tk
    root = tk.Tk()

from gui import WordPressPublisherApp


def main():
    root.title("WordPress Publisher")
    root.geometry("1200x750")
    root.minsize(1050, 700)
    WordPressPublisherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
