import tkinter as tk
from gui import WordPressPublisherApp


def main():
    root = tk.Tk()
    root.title("WordPress Publisher")
    root.geometry("900x650")
    root.minsize(800, 600)
    WordPressPublisherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
