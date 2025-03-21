Project 8: VM Translator
=======================

Description:
This program is a VM translator that converts VM language commands into Hack assembly code (.asm). 

- The translator reads a VM file, processes the commands, and outputs an assembly file containing the translated instructions. 
- If multiple .vm files are provided (inside a directory), the translator merges them into a single .asm file, ensuring proper function linkage and bootstrap initialization (Sys.init).

How to Run:
1. Unzip the package. Open the folder Files directory (folder) "HuangAnitaProject8" in your IDE 
2. Open a terminal/command line
3. Input the command as shown below: 
	If the input is one .vm file: 
		python3 src/project8.py <full path to the input file>.vm 
	If the input is a directory / folder: 
		python3 src/project8.py <full path to the input folder>
4. Please use the .vm files in the folder to test

Output:
- For a single .vm file: Generates a corresponding .asm file in the same directory.
- For multiple .vm files (in a directory): Generates a single .asm file, merging all .vm files into one program. 

Requirements:
- Python 3.x environment 

What Works:
- Reads and parses .vm file while removing comments and whitespace. 
- Translates push and pop commands for segments like constant, local, argument, this, that, temp, pointer, and static 
- Translates arithmetic commands like add, sub, neg, eq, gt, lt, and, or, and not
- Translates branching and function calling commands 
- Generates a valid .asm file as output to be tested 

What Doesn't Work:
- The program assumes the .vm files works fine without any errors 
- The script must be run from the same directory as the input file 
