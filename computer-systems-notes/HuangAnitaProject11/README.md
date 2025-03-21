Project 11: Jack Compiler - Part II. Code Generation
=======================

Description:
- Tokenizer.py: A tokenizer that processes Jack programming language source files and converts them into a stream of tokens.
- Parser.py: A parser that takes the tokenized output and converts it into a desired program structure.
- SymbolTable.py: Manages identifier definitions and their attributes (such as scope and type) to support parsing.
- CodeWriter.py: Converts parsed Jack code into VM instructions, ensuring correct compilation output.

How to Run:
1. Unzip the package 
2. Run Python3 Parser.py /path/to/input_file.jack 
3. Load the generated vm file from the prior step into the online IDE VM Emulator, and see if the output is as desired. 

Requirements:
- Python 3.x & Java 
- Ensure that the input Jack files are correctly formatted 

What Works:
- The tokenizer correctly converts Jack source files into a stream of tokens following the Jack grammar.
- The symbol table accurately tracks variable declarations and references. 
- The compiler generates VM code that can be executed in the VM emulator. 
- All test programs run successfully with expected behavior in the VM emulator.

What Doesn't Work:
- The tokenizer may not handle malformed Jack files correctly, leading to parsing errors.
- Some complex Jack language features may require further debugging for full support in VM code generation.
