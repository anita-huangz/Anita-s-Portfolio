import os

# Defines the different types of commands in VM language
class CommandType:
    C_ARITHMETIC = "C_ARITHMETIC"
    C_PUSH = "C_PUSH"
    C_POP = "C_POP"
    C_LABEL = "C_LABEL"
    C_GOTO = "C_GOTO"
    C_IF = "C_IF"
    C_FUNCTION = "C_FUNCTION"
    C_RETURN = "C_RETURN"
    C_CALL = "C_CALL"

# **Parser Class**: Reads and parses each command in a `.vm` file
class Parser:
    def __init__(self, input_file):
        """Initializes the parser with the given input file."""
        self.lines = [line.split("//")[0].strip() for line in input_file.readlines() 
                      if line.strip() and not line.startswith("//")]
        self.current_index = -1

    def advance(self):
        """Moves to the next valid command, skipping empty lines."""
        while self.current_index + 1 < len(self.lines):
            self.current_index += 1
            self.current_command = self.lines[self.current_index].strip()

            # Skip if current_command is empty
            if self.current_command:
                return  # Exit once a valid command is found

    def command_type(self):
        """Determines the type of the current command."""
        command = self.lines[self.current_index].split(" ")[0]
        if command == "push":
            return CommandType.C_PUSH
        elif command == "pop":
            return CommandType.C_POP
        elif command == "label":
            return CommandType.C_LABEL
        elif command == "goto":
            return CommandType.C_GOTO
        elif command == "if-goto":
            return CommandType.C_IF
        elif command == "function":
            return CommandType.C_FUNCTION
        elif command == "return":
            return CommandType.C_RETURN
        elif command == "call":
            return CommandType.C_CALL
        else:
            return CommandType.C_ARITHMETIC

    def arg1(self):
        """Returns the first argument of the command."""
        parts = self.lines[self.current_index].split(" ")
        if self.command_type() == CommandType.C_RETURN:
            return None
        if self.command_type() == CommandType.C_ARITHMETIC:
            return parts[0].lower() if parts[0] else None  # Ensure non-empty return
        return parts[1] if len(parts) > 1 else None  # Ensure it doesn't return ''


    def arg2(self):
        """Returns the second argument if applicable (used for push/pop commands)."""
        if self.command_type() in {CommandType.C_PUSH, CommandType.C_POP, 
                                    CommandType.C_FUNCTION, CommandType.C_CALL}:
            return int(self.lines[self.current_index].split(" ")[2])
        return None

# **CodeWriter Class**: Translates parsed VM commands into Hack Assembly
class CodeWriter:
    def __init__(self, file_path):
        """Initializes the CodeWriter and prepares the output file."""
        self.file_name = os.path.splitext(os.path.basename(file_path))[0]
        self.output_file = open(f"{self.file_name}.asm", "w")
        self.label_count = 0
    
    def write_init(self):
        # if more than one file, then bootstrap code
        self.output_file.write("// Bootstrap code\n")
        # initialize SP to 256
        self.output_file.write("@256\nD=A\n@SP\nM=D\n")
        # call Sys.init
        self.write_call("Sys.init", 0)

    def write_arithmetic(self, command):
        """Translates arithmetic commands into Hack assembly."""
        self.output_file.write(f"// {command}\n")

        arithmetic_ops = {
            "add": "M=D+M",
            "sub": "M=M-D",
            "and": "M=D&M",
            "or": "M=D|M"
        }

        if command in arithmetic_ops:
            self.pop_stack_to_d()
            self.output_file.write("@SP\nM=M-1\nA=M\n" + arithmetic_ops[command] + "\n@SP\nM=M+1\n")
        elif command in {"neg", "not"}:
            self.output_file.write("@SP\nM=M-1\nA=M\nM=" + ("-M" if command == "neg" else "!M") + "\n@SP\nM=M+1\n")
        elif command in {"eq", "gt", "lt"}:
            self.write_compare_logic(command)  # FIXED: Pass "eq", "gt", "lt" directly

    # Newly added functions from Project 8 
    def write_label(self, label):
        self.output_file.write(f"({label})\n")

    def write_goto(self, label):
        self.output_file.write(f"@{label}\n0;JMP\n")

    def write_if(self, label):
        self.pop_stack_to_d()
        self.output_file.write(f"@{label}\nD;JNE\n")

    def write_function(self, function_name, num_locals):
        self.output_file.write(f"({function_name})\n")
        for _ in range(num_locals):
            self.output_file.write("@0\nD=A\n")
            self.push_d_to_stack()
            
    def write_call(self, function_name, num_args):
        return_label = f"{function_name}$ret.{self.label_count}"
        self.label_count += 1

        # push return address
        self.output_file.write(f"@{return_label}\nD=A\n")
        self.push_d_to_stack()

        # push LCL, ARG, THIS, THAT of the calling function
        for segment in ["LCL", "ARG", "THIS", "THAT"]:
            self.output_file.write(f"@{segment}\nD=M\n")
            self.push_d_to_stack()

        # ARG = SP - num_args - 5
        self.output_file.write(f"@SP\nD=M\n@{num_args + 5}\nD=D-A\n@ARG\nM=D\n")
        
        # LCL = SP
        self.output_file.write("@SP\nD=M\n@LCL\nM=D\n")
        
        # goto function
        self.output_file.write(f"@{function_name}\n0;JMP\n")
        
        # (return_label)
        self.output_file.write(f"({return_label})\n")

    def write_return(self):
        self.output_file.write("// return\n")
        # FRAME = LCL
        self.output_file.write("@LCL\nD=M\n@R13\nM=D\n")
        # RET = *(FRAME - 5)
        self.output_file.write("@5\nA=D-A\nD=M\n@R14\nM=D\n")
        # *ARG = pop()
        self.pop_stack_to_d()
        self.output_file.write("@ARG\nA=M\nM=D\n")
        # SP = ARG + 1
        self.output_file.write("@ARG\nD=M+1\n@SP\nM=D\n")
        # THAT = * (FRAME - 1)
        self.output_file.write("@R13\nAM=M-1\nD=M\n@THAT\nM=D\n")
        # THIS = * (FRAME - 2)
        self.output_file.write("@R13\nAM=M-1\nD=M\n@THIS\nM=D\n")
        # ARG = * (FRAME - 3)
        self.output_file.write("@R13\nAM=M-1\nD=M\n@ARG\nM=D\n")
        # LCL = * (FRAME - 4)
        self.output_file.write("@R13\nAM=M-1\nD=M\n@LCL\nM=D\n")
        # goto RET
        self.output_file.write("@R14\nA=M\n0;JMP\n")

    # Edited for better readability based of Project 7 & added new features from Project 8 

    def write_push_pop(self, command_type, segment, index):
        self.output_file.write(f"// {command_type} {segment} {index}\n")
        if command_type == CommandType.C_PUSH:
            if segment == "constant":
                self.output_file.write(f"@{index}\nD=A\n")
            else:
                self.load_segment(segment, index)
                self.output_file.write("D=M\n")
            self.push_d_to_stack()
        elif command_type == CommandType.C_POP:
            self.load_segment(segment, index)
            self.output_file.write("D=A\n@R13\nM=D\n")
            self.pop_stack_to_d()
            self.output_file.write("@R13\nA=M\nM=D\n")

    def close(self):
        self.output_file.close()

    def increment_stack_pointer(self):
        self.output_file.write("@SP\nM=M+1\n")

    def decrement_stack_pointer(self):
        self.output_file.write("@SP\nM=M-1\n")

    def pop_stack_to_d(self):
        self.decrement_stack_pointer()
        self.output_file.write("A=M\nD=M\n")

    def push_d_to_stack(self):
        self.load_stack_pointer_to_a()
        self.output_file.write("M=D\n")
        self.increment_stack_pointer()

    def load_stack_pointer_to_a(self):
        self.output_file.write("@SP\nA=M\n")

    def write_compare_logic(self, command):
        """Handles comparison logic like eq, gt, lt."""
        # print(f"DEBUG: command received in write_compare_logic -> '{command}'")  # Debugging

        self.pop_stack_to_d()
        self.decrement_stack_pointer()
        self.load_stack_pointer_to_a()
        self.output_file.write("D=M-D\n")

        label_true = f"TRUE_{self.label_count}"
        label_end = f"END_{self.label_count}"

        jump_command = {"eq": "JEQ", "gt": "JGT", "lt": "JLT"}.get(command.lower(), None)  # Ensure valid lookup
        # if jump_command is None:
        #     raise ValueError(f"Invalid comparison command: '{command}'")  # Explicit error handling

        self.output_file.write(f"@{label_true}\nD;{jump_command}\n")
        self.load_stack_pointer_to_a()
        self.output_file.write("M=0\n")
        self.output_file.write(f"@{label_end}\n0;JMP\n")
        self.output_file.write(f"({label_true})\n")
        self.load_stack_pointer_to_a()
        self.output_file.write("M=-1\n")
        self.output_file.write(f"(END_{self.label_count})\n")
        self.increment_stack_pointer()
        self.label_count += 1

    def load_segment(self, segment, index):
        segment_base = {
            "local": "LCL",
            "argument": "ARG",
            "this": "THIS",
            "that": "THAT",
            "pointer": 3,
            "temp": 5
        }
        if segment == "constant":
            self.output_file.write(f"@{index}\n")
        elif segment in ["pointer", "temp"]:
            self.output_file.write(f"@R{segment_base[segment] + index}\n")
        elif segment == "static":
            self.output_file.write(f"@{self.file_name}.{index}\n")
        else:
            self.output_file.write(f"@{segment_base[segment]}\nD=M\n@{index}\nA=D+A\n")

def main(input_path):
    """Main function to process VM files and translate them into a single Hack Assembly file."""
    
    # If input_path is a directory, process all .vm files and generate a single output file
    if os.path.isdir(input_path):
        output_file = os.path.join(input_path, os.path.basename(input_path) + ".asm")
        vm_files = [os.path.join(input_path, f) for f in os.listdir(input_path) if f.endswith(".vm")]
        needs_bootstrap = True
    else:  # Single .vm file
        output_file = input_path.replace(".vm", ".asm")
        vm_files = [input_path]
        needs_bootstrap = False
    
    # Create a single CodeWriter instance for all files
    code_writer = CodeWriter(output_file)
    
    # Include bootstrap code if needed
    if needs_bootstrap:
        code_writer.write_init()

    # Process each .vm file in the directory
    for file in vm_files:
        with open(file, "r") as input_file:
            parser = Parser(input_file)
            code_writer.file_name = os.path.splitext(os.path.basename(file))[0] 

            while parser.current_index + 1 < len(parser.lines):  # Process each command
                parser.advance()
                command_type = parser.command_type()
                
                if command_type == CommandType.C_ARITHMETIC:
                    code_writer.write_arithmetic(parser.arg1())
                elif command_type in {CommandType.C_PUSH, CommandType.C_POP}:
                    code_writer.write_push_pop(command_type, parser.arg1(), parser.arg2())
                elif command_type == CommandType.C_LABEL:
                    code_writer.write_label(parser.arg1())
                elif command_type == CommandType.C_GOTO:
                    code_writer.write_goto(parser.arg1())
                elif command_type == CommandType.C_IF:
                    code_writer.write_if(parser.arg1())
                elif command_type == CommandType.C_FUNCTION:
                    code_writer.write_function(parser.arg1(), parser.arg2())
                elif command_type == CommandType.C_RETURN:
                    code_writer.write_return()
                elif command_type == CommandType.C_CALL:
                    code_writer.write_call(parser.arg1(), parser.arg2())

    # Close the single output file
    code_writer.close()
    # print(f"Translation complete! Output written to {output_file}")

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
