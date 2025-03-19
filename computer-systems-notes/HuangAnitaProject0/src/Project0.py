import sys 
import os 

def clean_file(input_file):
    """
    Process the given file to remove blank lines and leading white space, 
    and removing all comments. 
    Output the file and save in the same directory as the input. 
    """

    try:
        # Validate input file extension
        if not input_file.endswith(".in"):
            raise ValueError("Input file must have a .in extension")
        
        # Output file path 
        output_file = input_file[:-3] + ".out"

        # Initalization variables for multi-line comment handling 
        in_multiline = False 

        # Read input and write to output file 
        with open(input_file, "r") as infile, open(output_file, "w") as outfile:
            for line in infile:
                line = line.strip() # Remove leading/trailing whitespaces 

                if not line: # skip empty lines 
                    continue 

                if in_multiline: # skip lines inside multi-line comments
                    if "*/" in line:
                        in_multiline = False
                        line = line.split("*/", 1)[1]
                    else:
                        continue
                
                if "/*" in line: # detect start of multi-line comment 
                    in_multiline = True 
                    line = line.split("/*", 1)[0]
                
                if "//" in line: # Remove single line comments 
                    line = line.split("//", 1)[0]
                
                if line.strip(): # Write non-empty and clean lines to output
                    outfile.write(line + "\n")
            
            print(f"Processed file saved as {output_file}")
        
    except FileNotFoundError:
        print(f"Error: File '{input_file} not found")
    except ValueError as ve:
        print(f"A value error occured: {ve}")
    except Exception as e:
        print(f"An error occured: {e}")

if __name__ == "__main__":
    # Check for correct usage
    if len(sys.argv) != 2:
        print("Usage: python 3 project0.py <filename>.in")
        sys.exit(1)
    
    clean_file(sys.argv[1])