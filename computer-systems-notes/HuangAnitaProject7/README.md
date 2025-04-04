Project 7: VM to Hack Translator
=======================

Description:
This program is a VM translator that converts VM language commands into Hack assembly code (.asm). The translator reads a VM file, processes the commands, and outputs an assembly file containing the translated instructions. 

How to Run:
1. Open a terminal/command line.
2. Navigate to the Files directory (folder).
3. Run the program with the command: python3 project7.py BasicTest.vm (for example)

Output:
The assembler will produce a .hack file with the same name as the input .asm file.
Each line in the output .hack file represents a 16-bit binary instruction corresponding to the Hack machine code.

Requirements:
- Python 3.x environment 

What Works:
- Reads and parses .vm file while removing comments and whitespace. 
- Translates arithmetic, logical, push, and pop commands 
- Generates a valid .asm file as output to be tested 

What Doesn't Work:
- The program assumes the .vm files works fine without any errors 
- The script must be run from the same directory as the input file 
