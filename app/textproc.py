"""Превращает «сырой» вывод Vosk (строчные слова без знаков) в текст для ввода.

Модуль не зависит от Windows и тестируется отдельно (tests/test_textproc.py).

Что умеет:
  * голосовые знаки препинания: «точка», «запятая», «вопросительный знак»,
    «новая строка» и т.д. (можно выключить в config.json);
  * заглавная буква в начале диктовки и после . ! ?;
  * правильные пробелы между фразами и вокруг знаков;
  * пользовательские замены из config.json («гитхаб» -> «GitHub»).
"""
from __future__ import annotations

from dataclasses import dataclass

# Типы токенов
WORD = "word"        # обычное слово: пробел перед ним, если нужен
PUNCT = "punct"      # . , ! ? ) » — прилипает к предыдущему слову
OPEN = "open"        # ( « — пробел перед, но не после
JOIN = "join"        # дефис — без пробелов с обеих сторон
NEWLINE = "newline"  # перевод строки (печатается как Shift+Enter)

SENTENCE_END = {".", "!", "?"}

# Голосовые команды. Ключи — то, что выдаёт Vosk (строчные, «е» и «ё» — оба варианта).
VOICE_COMMANDS: dict[str, tuple[str, str]] = {
    "точка": (PUNCT, "."),
    "запятая": (PUNCT, ","),
    "точка с запятой": (PUNCT, ";"),
    "двоеточие": (PUNCT, ":"),
    "вопросительный знак": (PUNCT, "?"),
    "знак вопроса": (PUNCT, "?"),
    "восклицательный знак": (PUNCT, "!"),
    "знак восклицания": (PUNCT, "!"),
    "многоточие": (PUNCT, "…"),
    "тире": (WORD, "—"),
    "дефис": (JOIN, "-"),
    "открыть скобку": (OPEN, "("),
    "открой скобку": (OPEN, "("),
    "открывающая скобка": (OPEN, "("),
    "закрыть скобку": (PUNCT, ")"),
    "закрой скобку": (PUNCT, ")"),
    "закрывающая скобка": (PUNCT, ")"),
    "открыть кавычки": (OPEN, "«"),
    "открой кавычки": (OPEN, "«"),
    "закрыть кавычки": (PUNCT, "»"),
    "закрой кавычки": (PUNCT, "»"),
    "новая строка": (NEWLINE, "\n"),
    "с новой строки": (NEWLINE, "\n"),
    "новый абзац": (NEWLINE, "\n\n"),
    "с нового абзаца": (NEWLINE, "\n\n"),
    "точка ру": (PUNCT, ".ru"),
    "точка ком": (PUNCT, ".com"),
    "точка рф": (PUNCT, ".рф"),
    "точка орг": (PUNCT, ".org"),
}

# Устойчивые выражения со словом «точка», которые НЕ надо превращать в знак.
_KEEP_PHRASES = [
    "точка зрения", "точка доступа", "точка опоры", "точка отсчета",
    "точка отсчёта", "точка входа", "точка выхода", "точка росы",
    "точка кипения", "точка плавления", "точка замерзания",
    "точка невозврата", "точка продаж", "точка роста", "точка сборки",
    "точка останова", "точка соприкосновения", "точка пересечения",
    "точка интереса", "точка назначения",
]
for _p in _KEEP_PHRASES:
    VOICE_COMMANDS[_p] = (WORD, _p)


@dataclass
class FormatState:
    last: str = "start"      # start | word | punct | open | join | newline
    cap_next: bool = True


class Formatter:
    """Форматирует фразы одной сессии диктовки (от нажатия до выключения)."""

    def __init__(self, voice_punctuation: bool = True, capitalize: bool = True,
                 replacements: dict[str, str] | None = None):
        self.capitalize = capitalize
        self.table: dict[tuple[str, ...], tuple[str, str]] = {}
        if voice_punctuation:
            for phrase, val in VOICE_COMMANDS.items():
                self.table[tuple(phrase.split())] = val
        for phrase, text in (replacements or {}).items():
            key = tuple(str(phrase).lower().replace("ё", "е").split())
            if key:
                self.table[key] = (WORD, str(text))
                # вариант с «ё», если Vosk вдруг его выдаст
                self.table[tuple(str(phrase).lower().split())] = (WORD, str(text))
        self.max_len = max((len(k) for k in self.table), default=1)
        self.state = FormatState(cap_next=capitalize)

    def reset(self) -> None:
        self.state = FormatState(cap_next=self.capitalize)

    def finish(self) -> str:
        """Хвост в конце диктовки: пробел, чтобы следующая диктовка не слиплась."""
        return " " if self.state.last in ("word", "punct") else ""

    # --- разбор -----------------------------------------------------------
    def tokenize(self, text: str) -> list[tuple[str, str]]:
        words = text.lower().split()
        out: list[tuple[str, str]] = []
        i = 0
        while i < len(words):
            for n in range(min(self.max_len, len(words) - i), 0, -1):
                key = tuple(words[i:i + n])
                hit = self.table.get(key)
                if hit is None and "ё" in " ".join(key):
                    hit = self.table.get(tuple(w.replace("ё", "е") for w in key))
                if hit is not None:
                    out.append(hit)
                    i += n
                    break
            else:
                out.append((WORD, words[i]))
                i += 1
        return out

    # --- сборка -----------------------------------------------------------
    def feed(self, text: str) -> str:
        """Принимает финальный текст фразы от Vosk, возвращает строку для ввода."""
        st = self.state
        parts: list[str] = []
        for kind, tok in self.tokenize(text):
            if kind in (WORD, OPEN):
                if st.last in ("word", "punct"):
                    parts.append(" ")
                if kind == WORD and st.cap_next and tok[:1].isalpha():
                    # «GitHub», «iPhone» — не трогаем стилизованные замены
                    if not any(c.isupper() for c in tok):
                        tok = tok[:1].upper() + tok[1:]
                    st.cap_next = False
                parts.append(tok)
                st.last = "word" if kind == WORD else "open"
            elif kind == PUNCT:
                parts.append(tok)
                st.last = "punct"
                if tok in SENTENCE_END:
                    st.cap_next = True
            elif kind == JOIN:
                parts.append(tok)
                st.last = "join"
            elif kind == NEWLINE:
                parts.append(tok)
                st.last = "newline"
                st.cap_next = True
        return "".join(parts)


def tail(text: str, max_chars: int) -> str:
    """Хвост строки для показа в плашке."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return "…" + text[-(max_chars - 1):]
