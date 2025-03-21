# Project Overview 
The Search Trie Project involves building a full-text search engine that crawls web pages, indexes words using a trie data structure, and implements a search interface. The project consists of multiple components, including character-to-key conversion, trie implementation, web crawling, and search functionality. This project showcases my skills in web scraping, data structures, and full-stack development.

# Project Sections 
## 1. Character-to-Key Conversion (Helper Function) 
**Objective:**
Implemented a helper function, character_to_key, to convert characters (letters and underscores) into numeric keys. This conversion is essential for storing and searching strings efficiently in the trie data structure.
**Key Features:**
- Handles both lowercase and uppercase characters.
- Maps special characters and punctuation to a unique key.
- Supports robust testing to ensure accurate conversion for all edge cases.

## 2. Trie Data Structure Implementation
**Objective:** 
Developed a custom Trie data structure to store words and their corresponding URLs for efficient search operations. The trie allows for fast lookups, insertions, and deletions, as well as advanced features like wildcard searches.
**Key Features:**
- Implemented the trie as a subclass of abc.MutableMapping to provide standard dictionary-like behavior (e.g., __getitem__, __setitem__, __delitem__).
- Integrated a wildcard_search method for fuzzy matching of search queries.
- Designed a scalable structure that handles large datasets efficiently.

## 3. Search Interface
**Objective:** 
Created an interactive search interface that allows users to search for words across the indexed web pages. The interface provides a user-friendly way to query the trie and display the results.
**Key Features:**
- Terminal Interface: Built a terminal-based user interface using the rich library for a smooth user experience.
- Web Interface (Optional): Alternatively, developed a web interface using Flask to present search results in a browser.
- The interface dynamically displays search results in a table format, showing the matched words and their associated URLs.