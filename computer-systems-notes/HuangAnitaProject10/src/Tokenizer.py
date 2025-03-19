import sys
import os

class Tokenizer:
    """
    Tokenizer for Jack programming language.
    This class reads a 'jack' file, removes comments, tokenizes the content, and
    outpur tokens in an XML format.
    """

    KEYWORDS = {
        "class", "constructor", "function", "method", "field", "static", "var",
        "int", "char", "boolean", "void", "true", "false", "null", "this",
        "let", "do", "if", "else", "while", "return"
    }
    SYMBOLS = {'{', '}', '(', ')', '[', ']', '.', ',', ';', '+', '-', '*', '/',
               '&', '|', '<', '>', '=', '~'}
    XML_ESCAPES = {"<": "&lt;", ">": "&gt;", "&": "&amp;"}

    def __init__(self, filename):
        """
        Initializes the tokenizer, reads the file, removes comments, and tokenizes.
        """
        # Open file and read the content
        self.filename = filename
        with open(filename, "r") as file:
            self.source_code = file.read()

        self.clean_code() # Remove comments from the source code
        self.tokens = self.tokenize() # Tokenize the cleaned code
        self.current_token = None # Current token starts as None

    def clean_code(self):
        """
        Removes comments and unnecessary whitespace from the code.
        """
        clean_lines = []
        inside_comment = False # Flag for multi-line comment state
        inside_string = False # Flag for string

        i = 0
        while i < len(self.source_code):
            if inside_comment:
                if self.source_code[i:i+2] == "*/":
                    inside_comment = False
                    i += 2
                    continue
            elif self.source_code[i:i+2] == "/*":
                inside_comment = True
                i += 2
                continue
            elif self.source_code[i:i+2] == "//":
                while i < len(self.source_code) and self.source_code[i] != "\n":
                    i += 1
            else:
                if self.source_code[i] == '"':
                    inside_string = not inside_string
                clean_lines.append(self.source_code[i])
            i += 1

        self.source_code = "".join(clean_lines) # store the output to desired place

    def tokenize(self):
        """
        Tokenizes the Jack source code into a list of pairs of token_type, value.
        """
        tokens = []
        current = ""
        inside_string = False # track if currently inside a string literal
        i = 0

        while i < len(self.source_code):
            char = self.source_code[i]

            if char == '"':  # Start or end of a string constant
                if inside_string:
                    tokens.append(("stringConstant", current))
                    current = ""
                inside_string = not inside_string
            elif inside_string:
                current += char
            elif char in self.SYMBOLS:  # Single-character symbols
                if current:
                    tokens.append(self.identify_token(current))
                    current = ""
                symbol_value = self.XML_ESCAPES.get(char, char)
                tokens.append(("symbol", symbol_value))
            elif char.isspace():  # Space between tokens
                if current:
                    tokens.append(self.identify_token(current))
                    current = ""
            else:
                current += char

            i += 1

        if current:
            tokens.append(self.identify_token(current))

        return tokens

    def identify_token(self, token):
        """ Determines if a token is a keyword, integer, or identifier. """
        if token in self.KEYWORDS:
            return ("keyword", token)
        elif token.isdigit():
            return ("integerConstant", token)
        else:
            return ("identifier", token)

    def has_more_tokens(self):
        """ Checks if there are more tokens to process. """
        return len(self.tokens) > 0

    def advance(self):
        """ Moves to the next token and returns it. """
        if self.has_more_tokens():
            self.current_token = self.tokens.pop(0)
            return self.current_token  # Ensure it returns (token_type, token_value)
        return None  # Return None if no tokens left

    def peek(self):
        """Returns the next token without consuming it."""
        if len(self.tokens) > 0:
            return self.tokens[0]  # Peek at the next token without removing it
        return None  # Return None if there are no more tokens

    def token_type(self):
        """ Returns the type of the current token. """
        return self.current_token[0] if self.current_token else None

    def token_value(self):
        """ Returns the value of the current token. """
        return self.current_token[1] if self.current_token else None

    def write_xml(self, output_file):
        """ Writes tokens to an XML file. """
        with open(output_file, "w") as file:
            file.write("<tokens>\n")
            for token_type, token_value in self.tokens:
                file.write(f"  <{token_type}> {token_value} </{token_type}>\n")
            file.write("</tokens>\n")
        print(f"Tokens written to {output_file}")

def main():
    """ Entry point for testing the tokenizer. """
    if len(sys.argv) != 2:
        print("Usage: python JackTokenizer.py <path_to_.jack_file>")
        return

    jack_file = sys.argv[1]
    if not os.path.isfile(jack_file):
        print(f"Error: {jack_file} not found.")
        return

    tokenizer = Tokenizer(jack_file)
    output_file = jack_file.replace(".jack", "T.xml")
    tokenizer.write_xml(output_file)

if __name__ == "__main__":
    main()
