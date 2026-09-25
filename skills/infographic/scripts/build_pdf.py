#!/usr/bin/env python3
"""build_pdf.py — собрать страницы инфографики (PNG/JPG) в один PDF, страница = картинка.

    python3 build_pdf.py "Название · инфографика.pdf" 01-cover.png 02-....png ...

Порядок страниц — порядок аргументов (называйте файлы 01-, 02-, … и передавайте *.png).
Картинки 2K весят по 5–8 МБ: сохраняем в JPEG-качестве 88, PDF выходит в 5–10 раз легче
и открывается на телефоне. Нужен Pillow (в образе компаньона есть).
"""
import sys
from PIL import Image


def main(a):
    if len(a) < 2:
        sys.exit(__doc__)
    out, files = a[0], a[1:]
    pages = [Image.open(f).convert("RGB") for f in files]
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], quality=88, resolution=150)
    print("ok", out, "страниц:", len(pages))


if __name__ == "__main__":
    main(sys.argv[1:])
