import tkinter as tk
from gui import WordPressPublisherApp


def main():
    root = tk.Tk()
    root.title("WordPress Publisher")
    root.geometry("1100x700")
    root.minsize(1000, 650)
    WordPressPublisherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
