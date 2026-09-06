#!/usr/bin/env python3
"""Подготовка текста для Telegram MarkdownV2.

Проблема, ради которой это написано: в MarkdownV2 нужно экранировать полтора
десятка символов, включая точку и дефис. Забыл один — сообщение либо не уйдёт,
либо разъедется. Руками это не выдерживается.

Как пользоваться: пишем текст, размечая ТОЛЬКО нужное, в понятном виде:

    **жирный**      → станет *жирным* (одна звёздочка, как требует Telegram)
    __курсив__      → станет _курсивом_
    `код`           → останется кодом
    > цитата        → останется цитатой
    [текст](адрес)  → останется ссылкой

Всё остальное экранируется. То есть пишем как обычно, а разметку задаём
привычным двойным синтаксисом — скрипт переведёт в то, что Telegram понимает.

    python3 tg.py "Готово: *24 полосы*."          # из аргумента
    python3 tg.py < письмо.txt                     # из файла

Вывод — готовая строка для параметра text при format="markdownv2".
"""
import re
import sys

# Экранируются все спецсимволы MarkdownV2, кроме тех, что мы сами вставляем
# как разметку на последнем шаге.
SPECIAL = r"_*[]()~`>#+-=|{}.!"


def escape(text: str) -> str:
    return "".join("\\" + c if c in SPECIAL else c for c in text)


def convert(src: str) -> str:
    """Вынимаем разметку, экранируем остальное, возвращаем разметку на место."""
    slots: list[str] = []

    def stash(markup: str) -> str:
        slots.append(markup)
        return f"\x00{len(slots) - 1}\x00"

    # Порядок важен: сначала то, что содержит другие символы внутри.
    def block(m):           # ```многострочный блок``` — вынимаем раньше всего,
        body = m.group(1)   # иначе одиночные кавычки растащат его на куски
        body = body.replace("\\", "\\\\").replace("`", "\\`")
        return stash(f"```{body}```")

    def code(m):            # `код` — внутри экранируются только ` и \
        body = m.group(1).replace("\\", "\\\\").replace("`", "\\`")
        return stash(f"`{body}`")

    def link(m):            # [текст](адрес)
        return stash(f"[{escape(m.group(1))}]({m.group(2)})")

    def bold(m):            # **жирный** → *жирный*
        return stash(f"*{escape(m.group(1))}*")

    def italic(m):          # __курсив__ → _курсив_
        return stash(f"_{escape(m.group(1))}_")

    out = src
    out = re.sub(r"```(.+?)```", block, out, flags=re.S)
    out = re.sub(r"`([^`\n]+)`", code, out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", link, out)
    out = re.sub(r"\*\*([^*\n]+)\*\*", bold, out)
    out = re.sub(r"__([^_\n]+)__", italic, out)

    # Цитаты: символ > в начале строки — разметка, в середине — обычный символ.
    lines = []
    for line in out.split("\n"):
        if line.lstrip().startswith(">"):
            body = line.lstrip()[1:].lstrip()
            lines.append(stash(">") + escape(body))
        else:
            lines.append(escape(line))
    out = "\n".join(lines)

    # Возвращаем разметку. Плейсхолдер после экранирования выглядит как \x000\x00.
    def restore(m):
        return slots[int(m.group(1))]

    return re.sub(r"\x00(\d+)\x00", restore, out)


def main():
    src = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    if not src.strip():
        print(__doc__)
        raise SystemExit(1)
    sys.stdout.write(convert(src.rstrip("\n")) + "\n")


if __name__ == "__main__":
    main()
