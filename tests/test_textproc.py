"""Тесты форматирования текста. Запуск: python tests/test_textproc.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from textproc import Formatter  # noqa: E402


def run(phrases, **kw):
    f = Formatter(**kw)
    return "".join(f.feed(p) for p in phrases)


CASES = [
    (["привет как дела"], "Привет как дела"),
    (["привет запятая как дела вопросительный знак"], "Привет, как дела?"),
    (["привет", "как дела"], "Привет как дела"),
    (["это проверка точка", "всё работает восклицательный знак"],
     "Это проверка. Всё работает!"),
    (["это проверка", "точка", "дальше"], "Это проверка. Дальше"),
    (["моя точка зрения такая"], "Моя точка зрения такая"),
    (["первая строка новая строка вторая"], "Первая строка\nВторая"),
    (["сайт яндекс точка ру"], "Сайт яндекс.ru"),
    (["открыть скобку пример закрыть скобку текст"], "(Пример) текст"),
    (["слово открыть скобку пример закрыть скобку"], "Слово (пример)"),
    (["кто дефис то"], "Кто-то"),
    (["я тире программист"], "Я — программист"),
    (["открой кавычки цитата закрой кавычки"], "«Цитата»"),
    (["поставь точку отсчёта"], "Поставь точку отсчёта"),
    (["точка отсчёта здесь"], "Точка отсчёта здесь"),
    (["точка отсчета здесь"], "Точка отсчета здесь"),
    (["что многоточие ладно"], "Что… ладно"),
    (["", "   "], ""),
]


def main():
    failed = 0
    for phrases, expected in CASES:
        got = run(phrases)
        ok = got == expected
        failed += not ok
        print(("OK  " if ok else "FAIL"), repr(phrases), "->", repr(got),
              "" if ok else f"(ожидалось {expected!r})")

    # без голосовой пунктуации и без заглавных
    got = run(["привет запятая мир"], voice_punctuation=False, capitalize=False)
    assert got == "привет запятая мир", got
    # пользовательские замены (в т.ч. фразы и ё/е)
    got = run(["выложи на гитхаб точка"], replacements={"гитхаб": "GitHub"})
    assert got == "Выложи на GitHub.", got
    got = run(["гитхаб это сайт"], replacements={"гитхаб": "GitHub"})
    assert got == "GitHub это сайт", got
    got = run(["пишу на питон"], replacements={"питон": "python"})
    assert got == "Пишу на python", got
    got = run(["ещё раз"], replacements={"еще раз": "снова"})
    assert got == "Снова", got
    f = Formatter()
    assert f.finish() == ""
    f.feed("привет")
    assert f.finish() == " "
    f.feed("новая строка")
    assert f.finish() == ""
    f.feed("да точка")
    assert f.finish() == " "
    print("extra asserts OK")
    if failed:
        print(f"{failed} FAILED")
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    main()
