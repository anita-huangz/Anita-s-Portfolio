class CodeWriter:
    def __init__(self, output_file):
        self.output_file = open(output_file, 'w')
        self.label_count = 0

    def write_bootstrap(self):
        """Writes the bootstrap code, initializing the stack and calling Sys.init."""
        self.output_file.write("// Bootstrap Code\n")
        self.write_init_stack_pointer()
        self.write_call("Sys.init", 0)

    def write_init_stack_pointer(self):
        """Sets the stack pointer to 256."""
        self.output_file.write("push constant 256\n")
        self.output_file.write("pop pointer 0\n")

    def write_arithmetic(self, command):
        """Writes the assembly code for an arithmetic command."""
        if command in {"add", "sub", "neg", "eq", "gt", "lt", "and", "or", "not"}:
            self.output_file.write(f"{command}\n")

    def write_push(self, segment, index):
        """ push command"""
        self.output_file.write(f"push {segment} {index}\n")

    def write_pop(self, segment, index):
        """ pop command"""
        self.output_file.write(f"pop {segment} {index}\n")

    def write_label(self, label):
        """Writes a label command."""
        self.output_file.write(f"label {label}\n")

    def write_goto(self, label):
        """Writes a goto command."""
        self.output_file.write(f"goto {label}\n")

    def write_if_goto(self, label):
        """Writes an if-goto command."""
        self.output_file.write(f"if-goto {label}\n")

    def write_function(self, name, n_locals):
        """Writes a function definition."""
        self.output_file.write(f"function {name} {n_locals}\n")

    def write_call(self, name, n_args):
        """Writes a function call."""
        self.output_file.write(f"call {name} {n_args}\n")

    def write_return(self):
        """Writes a return command."""
        self.output_file.write("return\n")

    def close(self):
        """Closes the output file."""
        self.output_file.close()
