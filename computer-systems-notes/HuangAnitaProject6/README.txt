Project 6: Hack Assembler
=======================

Description:
This program is a Hack Assembler that translates Hack assembly language (.asm) into Hack machine code (.hack). The assembler reads an assembly file, processes, and outputs a binary file containing the translated instructions.

How to Run:
1. Open a terminal/command line.
2. Navigate to the Files directory (folder).
3. Run the program with the command: python3 project6.py Add.asm (for example)

Output:
The assembler will produce a .hack file with the same name as the input .asm file.
Each line in the output .hack file represents a 16-bit binary instruction corresponding to the Hack machine code.

Requirements:
- Python 3.x environment 

What Works:
- Parses .asm file and removes the comments and whitespace during the passes
- Translates A and C instructions based on the requirements 
- Handles the symbols as needed
- Generates a valid .hack file as output 

What Doesn't Work:
- The program assumes the .asm files works fine without any errors 
- The script must be run from the same directory as the input file 
