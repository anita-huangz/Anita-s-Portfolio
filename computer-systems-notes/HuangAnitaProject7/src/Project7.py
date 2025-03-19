import os

# Defines the different types of commands in VM language
class CommandType:
    C_ARITHMETIC = "C_ARITHMETIC"
    C_PUSH = "C_PUSH"
    C_POP = "C_POP"

# **Parser Class**: Reads and parses each command in a `.vm` file
class Parser:
    def __init__(self, input_file):
        """Initializes the parser with the given input file."""
        self.lines = [line.split("//")[0].strip() for line in input_file.readlines() 
                      if line.strip() and not line.startswith("//")]
        self.current_index = -1

    def advance(self):
        """Moves to the next command."""
        self.current_index += 1

    def command_type(self):
        """Determines the type of the current command."""
        command = self.lines[self.current_index].split(" ")[0]
        if command == "push":
            return CommandType.C_PUSH
        elif command == "pop":
            return CommandType.C_POP
        return CommandType.C_ARITHMETIC 

    def arg1(self):
        """Returns the first argument of the command."""
        parts = self.lines[self.current_index].split(" ")
        return parts[0] if self.command_type() == CommandType.C_ARITHMETIC else parts[1]

    def arg2(self):
        """Returns the second argument if applicable (used for push/pop commands)."""
        if self.command_type() in {CommandType.C_PUSH, CommandType.C_POP}:
            return int(self.lines[self.current_index].split(" ")[2])
        return None

# **CodeWriter Class**: Translates parsed VM commands into Hack Assembly
class CodeWriter:
    def __init__(self, file_path):
        """Initializes the CodeWriter and prepares the output file."""
        self.file_name = os.path.splitext(os.path.basename(file_path))[0]
        self.output_file = open(f"{self.file_name}.asm", "w")
        self.label_count = 0

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
            self.write_compare_logic({"eq": "JEQ", "gt": "JGT", "lt": "JLT"}[command])

    def write_push_pop(self, command_type, segment, index):
        """Translates push/pop commands into Hack assembly."""
        self.output_file.write(f"// {command_type.lower()} {segment} {index}\n")

        segment_map = {"local": "LCL", "argument": "ARG", "this": "THIS", "that": "THAT"}

        if command_type == CommandType.C_PUSH:
            if segment == "constant":
                self.output_file.write(f"@{index}\nD=A\n")
            elif segment in segment_map:
                self.output_file.write(f"@{segment_map[segment]}\nD=M\n@{index}\nA=D+A\nD=M\n")
            elif segment == "pointer":
                self.output_file.write(f"@R{3 + index}\nD=M\n")
            elif segment == "temp":
                self.output_file.write(f"@R{5 + index}\nD=M\n")
            elif segment == "static":
                self.output_file.write(f"@{self.file_name}.{index}\nD=M\n")
            self.push_d_to_stack()

        elif command_type == CommandType.C_POP:
            if segment in segment_map:
                self.output_file.write(f"@{segment_map[segment]}\nD=M\n@{index}\nD=D+A\n")
            elif segment == "pointer":
                self.output_file.write(f"@R{3 + index}\nD=A\n")
            elif segment == "temp":
                self.output_file.write(f"@R{5 + index}\nD=A\n")
            elif segment == "static":
                self.output_file.write(f"@{self.file_name}.{index}\nD=A\n")
            self.output_file.write("@R13\nM=D\n")  # Store target address
            self.pop_stack_to_d()
            self.output_file.write("@R13\nA=M\nM=D\n")  # Store popped value

    def write_compare_logic(self, jump_command):
        """Handles `eq`, `gt`, and `lt` comparisons."""
        self.pop_stack_to_d()
        self.output_file.write("@SP\nM=M-1\nA=M\nD=M-D\n")  # Compute difference
        self.output_file.write(f"@TRUE{self.label_count}\nD;{jump_command}\n")  # Jump if condition met
        self.output_file.write("@SP\nA=M\nM=0\n")  # False case (set top of stack to 0)
        self.output_file.write(f"@END{self.label_count}\n0;JMP\n")
        self.output_file.write(f"(TRUE{self.label_count})\n@SP\nA=M\nM=-1\n")  # True case (set top of stack to -1)
        self.output_file.write(f"(END{self.label_count})\n@SP\nM=M+1\n")  # Move SP forward
        self.label_count += 1

    def pop_stack_to_d(self):
        """Pops the stack's top value into register D."""
        self.output_file.write("@SP\nM=M-1\nA=M\nD=M\n")

    def push_d_to_stack(self):
        """Pushes D-register value to the stack."""
        self.output_file.write("@SP\nA=M\nM=D\n@SP\nM=M+1\n")

    def close(self):
        """Closes the output file."""
        self.output_file.close()

def main(input_path):
    """Main function to process VM files and translate them into Hack Assembly."""
    files = [os.path.join(input_path, f) for f in os.listdir(input_path) if f.endswith(".vm")] if os.path.isdir(input_path) else [input_path]

    for file in files:
        with open(file, "r") as input_file:
            parser, code_writer = Parser(input_file), CodeWriter(file)

            while parser.current_index + 1 < len(parser.lines):  # Simplified loop
                parser.advance()
                if parser.command_type() == CommandType.C_ARITHMETIC:
                    code_writer.write_arithmetic(parser.arg1())
                else:
                    code_writer.write_push_pop(parser.command_type(), parser.arg1(), parser.arg2())

            code_writer.close()

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
