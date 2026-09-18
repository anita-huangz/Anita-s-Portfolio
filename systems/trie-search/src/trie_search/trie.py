"""A trie that implements the MutableMapping interface.

Keys are folded to a 27-symbol alphabet: a-z plus one bucket for everything
else. That is lossy on purpose -- it is what makes wildcard search cheap -- but
it means the trie is case-insensitive and cannot distinguish "don't" from
"don_t". `original_keys()` is provided for when the caller needs the text as it
was inserted.
"""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from typing import Any

ALPHABET_SIZE = 26
OTHER = 26
WILDCARD = "?"


def character_to_key(char: str) -> int:
    """Map a character to [0, 26]. Letters go to 0-25; anything else to 26."""
    if len(char) != 1:
        raise ValueError(f"expected a single character, got {char!r}")
    lowered = char.lower()
    if "a" <= lowered <= "z":
        return ord(lowered) - ord("a")
    return OTHER


class TrieNode:
    __slots__ = ("children", "is_terminal", "key", "value")

    def __init__(self) -> None:
        self.children: dict[int, TrieNode] = {}
        self.is_terminal = False
        #: The key text as first inserted, so lossy folding is recoverable.
        self.key: str | None = None
        self.value: Any = None


class Trie(MutableMapping):
    """A prefix tree with wildcard search."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.root = TrieNode()
        self._size = 0
        for key, value in (data or {}).items():
            self[key] = value

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_key(key: Any) -> str:
        if not isinstance(key, str):
            raise TypeError(f"trie keys must be strings, got {type(key).__name__}")
        return key

    def _find(self, key: str) -> TrieNode | None:
        node = self.root
        for char in key:
            child = node.children.get(character_to_key(char))
            if child is None:
                return None
            node = child
        return node

    # ------------------------------------------------------------------ #
    # MutableMapping
    # ------------------------------------------------------------------ #

    def __getitem__(self, key: str) -> Any:
        node = self._find(self._check_key(key))
        if node is None or not node.is_terminal:
            raise KeyError(key)
        return node.value

    def __setitem__(self, key: str, value: Any) -> None:
        self._check_key(key)
        node = self.root
        for char in key:
            index = character_to_key(char)
            node = node.children.setdefault(index, TrieNode())
        if not node.is_terminal:
            node.is_terminal = True
            node.key = key
            self._size += 1
        node.value = value

    def __delitem__(self, key: str) -> None:
        node = self._find(self._check_key(key))
        if node is None or not node.is_terminal:
            raise KeyError(key)
        node.is_terminal = False
        node.key = None
        node.value = None
        self._size -= 1

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[str]:
        """Yield keys -- not (key, value) pairs.

        The previous version yielded tuples here. `MutableMapping` builds
        `items()`, `values()`, and `keys()` on top of `__iter__` by doing
        `self[key]` for each yielded element, so yielding a tuple made every
        one of those raise. `dict(trie)` did not work either.
        """
        yield from self._walk(self.root, "")

    def _walk(self, node: TrieNode, prefix: str) -> Iterator[str]:
        if node.is_terminal:
            yield prefix
        for index in sorted(node.children):
            char = chr(index + ord("a")) if index < ALPHABET_SIZE else "_"
            yield from self._walk(node.children[index], prefix + char)

    # ------------------------------------------------------------------ #
    # Extras
    # ------------------------------------------------------------------ #

    def original_keys(self) -> Iterator[str]:
        """Keys as they were inserted, before alphabet folding."""
        yield from self._walk_original(self.root)

    def _walk_original(self, node: TrieNode) -> Iterator[str]:
        if node.is_terminal and node.key is not None:
            yield node.key
        for index in sorted(node.children):
            yield from self._walk_original(node.children[index])

    def keys_with_prefix(self, prefix: str) -> Iterator[str]:
        """Every key beginning with `prefix`. This is what a trie is for."""
        self._check_key(prefix)
        node = self._find(prefix)
        if node is None:
            return
        folded = "".join(
            chr(character_to_key(c) + ord("a")) if character_to_key(c) < ALPHABET_SIZE else "_"
            for c in prefix
        )
        yield from self._walk(node, folded)

    def wildcard_search(self, pattern: str) -> Iterator[tuple[str, Any]]:
        """Search with `?` standing for exactly one character.

        `c?t` matches cat, cot, cut. `??` matches any two-character key.

        The previous implementation matched on `*` while the docstring and the
        project README both documented `?`, so every documented example
        returned nothing.
        """
        self._check_key(pattern)
        yield from self._match(self.root, "", pattern)

    def _match(self, node: TrieNode, prefix: str, pattern: str) -> Iterator[tuple[str, Any]]:
        if not pattern:
            if node.is_terminal:
                yield prefix, node.value
            return

        char, rest = pattern[0], pattern[1:]
        if char == WILDCARD:
            for index in sorted(node.children):
                next_char = chr(index + ord("a")) if index < ALPHABET_SIZE else "_"
                yield from self._match(node.children[index], prefix + next_char, rest)
        else:
            index = character_to_key(char)
            child = node.children.get(index)
            if child is not None:
                next_char = chr(index + ord("a")) if index < ALPHABET_SIZE else "_"
                yield from self._match(child, prefix + next_char, rest)

    def __repr__(self) -> str:
        return f"Trie({self._size} keys)"
