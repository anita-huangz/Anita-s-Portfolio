Project 10: Jack Compiler - Part I. Syntax Analysis
=======================

Description:
- Tokenizer.py: A tokenizer that processes Jack programming language source files and converts them into a stream of tokens.
- Parser.py: A parser that takes the tokenized output and converts it into an XML representation of the program structure.

How to Run:
1. Unzip the package 
2. Generate the tokenized output: python3 /path/to/Tokenizer.py /path/to/input_file.jack 
3. Test whether the generated "xxxT.xml" output matches the expected output: /path/to/TextComparer.sh outputT.xml expected_output.xml
4. Generate the parsed output: python3 /path/to/Parser.py /path/to/input_file.jack 
5. Test whether the generated "xxx.xml" output matches the expected output: /path/to/TextComparer.sh output.xml expected_output.xml

** Example test case: 
python3 Parser.py /path/to/SquareGame.jack
/path/to/TextComparer.sh /path/to/SquareGame.xml /path/to/SampleOutput/SquareGame.xml

Requirements:
- Python 3.x & Java 
- Ensure that the input Jack files are correctly formatted 

What Works:
- The tokenizer correctly converts Jack source files into a stream of tokens following the Jack grammar.
- The parser successfully converts tokenized input into a structured XML representation.
- The XML output matches expected sample outputs when tested with TextComparer.sh.

What Doesn't Work:
- The tokenizer may not handle malformed Jack files correctly, leading to parsing errors.
- Error handling for invalid Jack syntax is minimal, and unexpected input could cause crashes.
