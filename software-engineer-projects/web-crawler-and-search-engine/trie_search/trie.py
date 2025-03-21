from typing import Any, Iterable
from collections.abc import MutableMapping


def character_to_key(char: str) -> int:
    """
    Given a character return a number between [0, 26] inclusive.

    Letters a-z should be given their position in the alphabet 0-25, regardless of case:
        a/A -> 0
        z/Z -> 25

    Any other character should return 26.
    """
    if not char or len(char) != 1:
        return 26

    if char.isalpha():
        return ord(char.lower()) - ord('a')
    return 26

class TrieNode:
    """
    Represents a node with children (dict) and optional value.
    """
    def __init__(self):
        self.children = {}
        self.is_terminal = False
        self.value = None

class Trie(MutableMapping):
    """
    Implementation of a trie class where each node in the tree can
    have up to 27 children based on next letter of key.
    (Using rules described in character_to_key.)

    Must implement all required MutableMapping methods,
    as well as wildcard_search.
    """

    def __init__(self):
        """Initializes the Trie with an empty root node and size counter."""
        self.root = TrieNode()
        self.size = 0

    # Helper function
    def _ensure_string_key(self, key: Any) -> None:
        """
        Helper method to ensure the key is a string.
        
        Raises:
            Key(Value)Error: If the key is not a string.
        """
        if not isinstance(key, str):
            raise KeyError(f"Key must be a string: {key}")

    # Helper function
    def _traverse(self, key: str) -> TrieNode:
        """Traverse the Trie for a given key. 
        Returns the last node if key exists."""
        node = self.root
        for char in key:
            idx = character_to_key(char)
            if idx not in node.children:
                raise KeyError(f"Key '{key}' not found.")
            node = node.children[idx]
        return node

    # Helper function
    def _insert(self, key: str) -> TrieNode:
        """Traverse the Trie and insert nodes as needed for the key."""
        node = self.root
        for char in key:
            idx = character_to_key(char)
            if idx not in node.children:
                node.children[idx] = TrieNode()
            node = node.children[idx]
        return node


    def __getitem__(self, key: str) -> Any:
        """
        Given a key, return the value associated with it in the trie.

        If the key has not been added to this trie, raise `KeyError(key)`.
        If the key is not a string, raise `ValueError(key)`
        """
        self._ensure_string_key(key)
        node = self._traverse(key)
        if node.is_terminal:
            return node.value
        raise KeyError(f"Key '{key}' not found.")


    def __setitem__(self, key: str, value: Any) -> None:
        """
        Given a key and value, store the value associated with key.

        Like a dictionary, will overwrite existing data if key already exists.

        If the key is not a string, raise `ValueError(key)`
        """
        self._ensure_string_key(key)
        node = self._insert(key)
        if not node.is_terminal:
            self.size += 1
        node.is_terminal = True
        node.value = value


    def __delitem__(self, key: str) -> None:
        """
        Remove data associated with `key` from the trie.

        If the key is not a string, raise `ValueError(key)`
        """
        self._ensure_string_key(key)
        node = self._traverse(key)
        if node.is_terminal:
            node.is_terminal = False
            node.value = None
            self.size -= 1
        else:
            raise KeyError(f"Key '{key}' not found.")


    def __len__(self) -> int:
        """
        Return the total number of entries currently in the trie.
        """
        return self.size


    # Helper function
    def _iter_search(self, node: TrieNode, prefix: str) -> Iterable[Any]:
        """
        Traverses the Trie to yield all key-value pairs starting from the given node.

        Yields Key-value pairs from terminal nodes 
        """
        if node.is_terminal:
            yield prefix, node.value

        for idx, child in sorted(node.children.items()):
            next_char = chr(idx + ord('a')) if idx < 26 else '_'
            yield from self._iter_search(child, prefix + next_char)


    def _wild_card_match(self, node: TrieNode, prefix: str, pattern: str) -> Iterable[Any]:
        """
        Searches the Trie for key-value pairs matching a wildcard pattern.

        Yields Key-value pairs matching the pattern 
        """
        # If the node is terminal and the pattern is fully matched or None, yield it
        if len(pattern) == 0:
            if node.is_terminal:
                yield prefix, node.value
            return

        # Get the current character and remaining pattern
        char, remaining_pattern = pattern[0], pattern[1:]

        if char == '*':  # Match exactly one character
            for idx, child in sorted(node.children.items()):
                next_char = chr(idx + ord('a')) if idx < 26 else '_'
                yield from self._wild_card_match(child, prefix + next_char, remaining_pattern)

        else:  # Match specific character
            idx = character_to_key(char)
            if idx in node.children:
                yield from self._wild_card_match(node.children[idx],
                                                 prefix + char, remaining_pattern)


    def __iter__(self) -> Iterable[tuple[str, Any]]:
        """
        Return an iterable of (key, value) pairs for every entry in the trie in alphabetical order.
        """
        yield from self._iter_search(self.root, prefix='')


    def wildcard_search(self, key: str) -> Iterable[tuple[str, Any]]:
        """
        Search for keys that match a wildcard pattern where a '?' can represent any character.

        For example:
            - c?t would match 'cat', 'cut', 'cot', etc.
            - ?? would match any two-letter string.

        Returns: Iterable of (key, value) pairs meeting the given condition.
        """
        self._ensure_string_key(key)  # Ensure valid string input
        yield from self._wild_card_match(self.root, prefix='', pattern=key)
