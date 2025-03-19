import sys

# Mapping tables for instruction translation
COMP_TABLE = {
    "0": "0101010", "1": "0111111", "-1": "0111010",
    "D": "0001100", "A": "0110000", "M": "1110000",
    "!D": "0001101", "!A": "0110001", "!M": "1110001",
    "-D": "0001111", "-A": "0110011", "-M": "1110011",
    "D+1": "0011111", "A+1": "0110111", "M+1": "1110111",
    "D-1": "0001110", "A-1": "0110010", "M-1": "1110010",
    "D+A": "0000010", "D+M": "1000010", "D-A": "0010011",
    "D-M": "1010011", "A-D": "0000111", "M-D": "1000111",
    "D&A": "0000000", "D&M": "1000000", "D|A": "0010101", "D|M": "1010101"
}

DEST_TABLE = {
    None: "000", "M": "001", "D": "010", "MD": "011",
    "A": "100", "AM": "101", "AD": "110", "AMD": "111"
}

JUMP_TABLE = {
    None: "000", "JGT": "001", "JEQ": "010", "JGE": "011",
    "JLT": "100", "JNE": "101", "JLE": "110", "JMP": "111"
}

class SymbolTable:
    """
    Manages symbol lookups for labels and variables in Hack assembly code.
    Keeps track of predefined symbols, user-defined labels, and variable allocations.
    """
    def __init__(self):
        # Predefined symbols and registers
        self.symbols = {
            'SP': 0, 'LCL': 1, 'ARG': 2, 'THIS': 3, 'THAT': 4,
            'R0': 0, 'R1': 1, 'R2': 2, 'R3': 3, 'R4': 4, 'R5': 5, 'R6': 6, 'R7': 7,
            'R8': 8, 'R9': 9, 'R10': 10, 'R11': 11, 'R12': 12, 'R13': 13, 'R14': 14, 'R15': 15,
            'SCREEN': 16384, 'KBD': 24576
        }
        self.next_var_address = 16  # Next available memory location for variables

    def define_label(self, label, address):
        """Stores a label in the symbol table with its corresponding memory address."""
        if label not in self.symbols:
            self.symbols[label] = address

    def define_variable(self, var):
        """Allocates a memory address for a new variable and returns its address."""
        if var not in self.symbols:
            self.symbols[var] = self.next_var_address
            self.next_var_address += 1
        return self.symbols[var]

    def resolve_address(self, symbol):
        """Retrieves the memory address of a given symbol, if available."""
        return self.symbols.get(symbol)

class CodeTranslator:
    """
    Handles the translation of Hack assembly instructions into binary machine code.
    Converts both A-instructions and C-instructions using predefined mappings.
    """
    def __init__(self, symbol_table):
        self.symbol_table = symbol_table

    def translate(self, instruction):
        """Determines whether the instruction is an A-instruction or C-instruction and translates."""
        return self._translate_a(instruction[1:]) if instruction.startswith('@') else self._translate_c(instruction)

    def _translate_a(self, symbol):
        """
        Translates an A-instruction into binary format.
        """
        if symbol.isdigit():
            address = int(symbol)
        else:
            address = self.symbol_table.resolve_address(symbol)
            if address is None:
                address = self.symbol_table.define_variable(symbol)
        return "0" + f"{address:015b}"

    def _translate_c(self, instruction):
        """
        Translates a C-instruction into its binary equivalent.
        """
        dest, comp, jump = None, instruction, None

        # Handle destination (dest=...)
        if '=' in instruction:
            dest, comp = instruction.split('=')

        # Handle jump (...;jump)
        if ';' in comp:
            comp, jump = comp.split(';')

        return "111{}{}{}".format(
            COMP_TABLE[comp],
            DEST_TABLE[dest],
            JUMP_TABLE[jump]
        )

def parse_assembly(file_name, symbol_table):
    """
    Parses a Hack assembly file, removes comments and whitespace, and extracts instructions.
    """
    parsed_instructions = []
    line_num = 0  # Keeps track of actual instruction lines (excluding labels)

    with open(file_name, "r") as file:
        for line in file:
            # Remove inline comments and whitespace
            line = line.strip().split("//")[0].strip()  
            
            if not line:  
                continue  # Ignore empty lines
            
            # Handle label declarations (e.g., (LOOP))
            if line.startswith("(") and line.endswith(")"):
                symbol_table.define_label(line[1:-1], line_num)
                continue  # Labels do not count as executable instructions

            parsed_instructions.append(line)
            line_num += 1  # Increment only for actual instructions
    
    return parsed_instructions

def assemble(file_name):
    """
    Coordinates the assembly process:
    1. Parses the input .asm file and builds the symbol table.
    2. Translates the instructions into binary format.
    3. Writes the translated instructions to a .hack output file.
    """
    symbol_table = SymbolTable()
    instructions = parse_assembly(file_name, symbol_table)

    output_file_name = file_name.replace(".asm", ".hack")

    with open(output_file_name, "w") as output:
        translator = CodeTranslator(symbol_table)
        for instruction in instructions:
            output.write(translator.translate(instruction) + "\n")

if __name__ == "__main__":
    """
    Ensures the correct number of arguments are provided before executing the assembler.
    """
    if len(sys.argv) != 2:
        print("Usage: python assembler.py <file.asm>")
    else:
        assemble(sys.argv[1])
