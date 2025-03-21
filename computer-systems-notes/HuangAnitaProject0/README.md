Project 0: File Cleaner
=======================

Description:
This function processes a text file (.in) to remove blank lines, leading/trailing whitespace,
single-line comments (//), and multi-line comments (/* */). The cleaned content will then be 
saved in a new file with the same name but with a .out extension in the same directory.

How to Run:
1. Open a terminal/command line.
2. Navigate to the Files directory (folder).
3. Run the program with the command: python3 project0.py project0example.in

Example:
python3 project0.py project0example.in

Output:
The cleaned file will be saved as `project0example.out` in the same directory 
as `project0example.in`.

Requirements:
- Python 3.x environment 

What Works:
- Removes blank lines, leading/trailing spaces, single-line comments, and multi-line comments.
- Creates a cleaned output file with .out in the same directory. 

What Doesn't Work:
- The program will not work if the input file path is in the wrong directory and 
the extensions (e.g., .in files) are not ".in".
