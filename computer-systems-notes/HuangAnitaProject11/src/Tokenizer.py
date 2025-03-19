import sys
import os
import re  # Added for regex-based tokenization

class Tokenizer:
    """
    Tokenizer for Jack programming language.
    This class reads a .jack file, removes comments, tokenizes the content, and
    outputs tokens in an XML format.
    """

    KEYWORDS = {
        "class", "constructor", "function", "method", "field", "static", "var",
        "int", "char", "boolean", "void", "true", "false", "null", "this",
        "let", "do", "if", "else", "while", "return"
    }
    SYMBOLS = {'{', '}', '(', ')', '[', ']', '.', ',', ';', '+', '-', '*', '/',
               '&', '|', '<', '>', '=', '~'}

    XML_ESCAPES = {"<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;"}

    # Added regex-based tokenization patterns for better accuracy
    TOKEN_PATTERN = re.compile(
        r'(\"[^\n\"]*\")|'               # String constants (inside double quotes)
        r'(\d+)|'                        # Integer constants
        r'([a-zA-Z_]\w*)|'               # Identifiers (must start with a letter or underscore)
        r'([\{\}\(\)\[\]\.,;\+\-\*/&|<>=~])'  # Symbols (single-character tokens)
    )

    def __init__(self, filename):
        """
        Initializes the tokenizer, reads the file, removes comments, and tokenizes.
        """
        # Open file and read the content
        self.filename = filename
        with open(filename, "r") as file:
            self.source_code = file.read()

        self.clean_code()  
        self.tokens = self.tokenize()  
        self.current_token = None  # Current token starts as None

    def clean_code(self):
        """
        Removes comments while preserving string literals.
        """
        clean_lines = []
        inside_comment = False  # Tracks multi-line comment state
        inside_string = False   # Tracks whether inside a string literal

        i = 0
        while i < len(self.source_code):
            if inside_comment:
                if self.source_code[i:i+2] == "*/":
                    inside_comment = False
                    i += 2
                    continue
            elif self.source_code[i:i+2] == "/*" and not inside_string:
                inside_comment = True
                i += 2
                continue
            elif self.source_code[i:i+2] == "//" and not inside_string:
                while i < len(self.source_code) and self.source_code[i] != "\n":
                    i += 1
            else:
                if self.source_code[i] == '"':
                    inside_string = not inside_string
                clean_lines.append(self.source_code[i])
            i += 1

        self.source_code = "".join(clean_lines)  

    def tokenize(self):
        """
        Tokenizes the Jack source code into a list of (token_type, value) pairs.
        """
        tokens = []
        for match in self.TOKEN_PATTERN.finditer(self.source_code):
            token = match.group(0)  # Extract the matched token
            tokens.append(self.identify_token(token))

        return tokens

    def identify_token(self, token):
        """
        Determines if a token is a keyword, integer, string, symbol, or identifier.
        """
        if token in self.KEYWORDS:
            return ("keyword", token)
        elif token in self.SYMBOLS:
            return ("symbol", token)
        elif token.startswith('"') and token.endswith('"'):
            return ("stringConstant", token[1:-1])  
        elif token.isdigit():
            # ✅ Check for leading zeros (Jack does not allow numbers like 0123)
            if token != "0" and token.startswith("0"):
                raise ValueError(f"Invalid integer constant with leading zero: {token}")
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
            return self.current_token
        return None  # Return None if no tokens left

    def peek(self):
        """Returns the next token without consuming it."""
        return self.tokens[0] if self.tokens else None

    def token_type(self):
        """ Returns the type of the current token. """
        return self.current_token[0] if self.current_token else None

    def token_value(self):
        """ Returns the value of the current token. """
        return self.current_token[1] if self.current_token else None

    def write_xml(self, output_file):
        """ Writes tokens to an XML file with proper escaping. """
        with open(output_file, "w") as file:
            file.write("<tokens>\n")
            for token_type, token_value in self.tokens:
                escaped_value = self.XML_ESCAPES.get(token_value, token_value)  # ✅ Apply escaping here
                file.write(f"  <{token_type}> {escaped_value} </{token_type}>\n")
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
