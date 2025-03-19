from Tokenizer import Tokenizer
from SymbolTable import SymbolTable
from CodeWriter import CodeWriter
import sys
import os

class Parser:

    binaryOp = {'+', '-', '*', '/', '|', '=', '<', '>', '&'}
    unaryOp = {'-', '~'}
    keywordConstant = {'true', 'false', 'null', 'this'}

    def __init__(self, input, output):
        """
        Initializes the Parser with input and output file paths.

        Args:
            input (str): The path to the .jack source file.
            output (str): The path to the output XML file.
        """
        self.tokenizer = Tokenizer(input)
        self.writer = CodeWriter(output)
        self.symbolTable = SymbolTable()
        self.className = ''
        self.name = ''

    def advance(self):
        """"
        Advances the tokenizer to the next token and
        writes it as a terminal XML element.
        """
        return self.tokenizer.advance()

    def checkNextToken(self, value=None, token=None, values=None):
        """
        Checks the next token against a specified condition.

        Args:
            value (str, optional): Checks if the next token's value matches this.
            token (str, optional): Checks if the next token's type matches this.
            values (set, optional): Checks if the next token's value is in this set.

        Returns:
            bool: True if the condition is met, otherwise False.
        """
        next_token, next_value = self.tokenizer.peek()

        if value is not None:
            return next_value == value
        if token is not None:
            return next_token == token
        if values is not None:
            return next_value in values

        return False

    # Class Parsing
    def compileClass(self):
        """
        Compiles a complete class.
        """
        # self.doStartingBracket('class')
        self.advance()  # Consume 'class' keyword
        self.className = self.advance()[1]  # Consume class name
        self.advance()  # Consume '{' symbol

        if self.checkNextToken(values={"static", "field"}):
            self.compileClassVarDec()
        while self.checkNextToken(values={"constructor", "method", "function"}):
            self.compileSubroutine()

        self.advance()  # '}'
        self.writer.close()
        # self.doClosingBracket()
        # self.outputFile.close()

    def compileClassVarDec(self):
        """
        compiles a static declaration or a field declaration.
        """
        # self.doStartingBracket('classVarDec')
        while self.checkNextToken(values={"static", "field"}):
            self.writeClassVarDec()
        # self.doClosingBracket()

    def writeClassVarDec(self):
        """
        Writes a single class variable declaration to the symbol table.
        """
        kind = self.advance()[1]  # Consume 'static' or 'field'
        type = self.advance()[1]  # Consume var type
        name = self.advance()[1]  # Consume var name
        self.symbolTable.define(name, type, kind)
        while self.checkNextToken(value=","):
            self.advance()  # Consume ',' symbol
            name = self.advance()[1]  # Consume var name
            self.symbolTable.define(name, type, kind)
        self.advance()  # Consume ';' symbol

    def compileSubroutine(self):
        """
        compiles a complete method, function, or constructor.
        """
        funcType = self.advance()  # Consume subroutine type / 'constructor'
        self.advance()  # Consume subroutine return type / class name
        self.name = self.className + '.' + self.advance()[1]  # Consume subroutine name / 'new'
        self.symbolTable.start_subroutine(self.name)
        self.symbolTable.set_scope(self.name)
        self.advance()  # Consume '(' symbol
        self.compileParameterList(funcType)
        self.advance()  # Consume ')' symbol
        self.compileSubroutineBody(funcType)

    def compileParameterList(self, funcType):
        """
        Compiles a parameter list, excluding enclosing '()'.
        """
        # self.doStartingBracket('parameterList')
        if funcType[1] == "method":
            self.symbolTable.define("this", "self", 'arg')

        while not self.checkNextToken(token="symbol"):
            self.writeParam()
        # self.doClosingBracket()

    def writeParam(self):
        type = self.advance()[1]  # Consume parameter type
        name = self.advance()[1]  # Consume parameter name
        self.symbolTable.define(name, type, 'arg')

        if self.checkNextToken(value=","):
            self.advance()  # ','

    def compileSubroutineBody(self, funcType):
        """
        Compiles the body of a subroutine.
        """
        # self.doStartingBracket('subroutineBody')
        self.advance()  # '{'

        while self.checkNextToken(value="var"):
            self.compileVarDec()

        nVars = self.symbolTable.varCount('var')
        self.writer.write_function(self.name, nVars)
        self.loadPointer(funcType)

        self.compileStatements()
        self.advance()  # '}'
        self.symbolTable.set_scope('global')

        # self.doClosingBracket()

    def loadPointer(self, funcType):
        # Newly added function
        if funcType[1] == "method":
            self.writer.write_push('argument', 0)
            self.writer.write_pop('pointer', 0)
        if funcType[1] == 'constructor':
            globalVars = self.symbolTable.globalsCount('field')
            self.writer.write_push('constant', globalVars)
            self.writer.write_call('Memory.alloc', 1)
            self.writer.write_pop('pointer', 0)

    def compileVarDec(self):
        """
        Compiles a var declaration.
        """
        # self.doStartingBracket('varDec')
        kind = self.advance()[1]  # Consume 'var' keyword
        type = self.advance()[1]  # Consume var type
        name = self.advance()[1]  # Consume var name
        self.symbolTable.define(name, type, kind)

        while self.checkNextToken(value=","):
            self.advance()  # ','
            name = self.advance()[1]  # Consume next var name
            self.symbolTable.define(name, type, kind)

        self.advance()  # ';'
        # self.doClosingBracket()

    # Compile a sequence of statements
    def compileStatements(self):
        """
        compiles a sequence of statements, not including the enclosing "{}".
        """

        while self.checkNextToken(values={"do", "let", "if", "while", "return"}):
            if self.checkNextToken(value="do"):
                self.compileDo()
            elif self.checkNextToken(value="let"):
                self.compileLet()
            elif self.checkNextToken(value="if"):
                self.compileIf()
            elif self.checkNextToken(value="while"):
                self.compileWhile()
            elif self.checkNextToken(value="return"):
                self.compileReturn()

    def compileDo(self):
        """
        compiles a do statement
        """
        # self.doStartingBracket('doStatement')
        self.advance()  # get 'do' keyword
        self.compileSubroutineCall()
        self.writer.write_pop('temp', 0)
        self.advance()  # get ';' symbol
        # self.doClosingBracket()

    def compileLet(self):
        """
        compiles a let statement
        """
        # self.doStartingBracket('letStatement')
        self.advance()  # get 'let' keyword
        isArray = False
        name = self.advance()[1]  # Consume var name

        if self.checkNextToken(value="["): #case of varName[expression]
            isArray = True
            self.compileArrayIndex(name) # new function

        self.advance()  # get '='
        self.compileExpression()

        if isArray:
            self.writer.write_pop("temp", 0)
            self.writer.write_pop("pointer", 1)
            self.writer.write_push("temp", 0)
            self.writer.write_pop("that", 0)
        else:
            self.writePop(name)

        self.advance()  # get ';' symbol
        # self.doClosingBracket()

    def compileIf(self):
        """
        Compiles an 'if' statement, possibly with an 'else' block.
        """
        # self.doStartingBracket('ifStatement')
        currentCounter = self.symbolTable.counters["if"]
        ifTrueLabel = f'IF_TRUE{currentCounter}'
        ifFalseLabel = f'IF_FALSE{currentCounter}'
        endLabel = f'END_{currentCounter}'
        self.symbolTable.counters["if"] += 1  # Increment the counter

        self.advance()
        self.advance()
        self.compileExpression()
        self.advance()

        # Write conditional jump (negate condition)
        self.writer.write_arithmetic("not")
        self.writer.write_if_goto(ifFalseLabel)  # Updated from `writeIf`

        # True block
        self.advance()
        self.compileStatements() # compile the statements in the true block
        self.advance()

        # After true block, jump to the end label
        self.writer.write_goto(endLabel)  # Ensure false block is skipped if condition is true

        # False block
        self.writer.write_label(ifFalseLabel)

        if self.checkNextToken(value="else"):
            self.advance()
            self.advance()
            self.compileStatements() # compile the statements in the false block
            self.advance()

        # End block
        self.writer.write_label(endLabel)

        # self.doClosingBracket()

    def compileWhile(self):
        """
        Compiles a while statement.
        Generates labels for loop start and end using the counters in SymbolTable.
        """
        # Retrieve the while counter for unique labels
        whileCount = self.symbolTable.counters["while"]
        continueLabel = f'WHILE_END{whileCount}'
        topLabel = f'WHILE_EXP{whileCount}'

        # Increment the while counter to ensure unique labels
        self.symbolTable.counters["while"] += 1

        # Top label for while loop
        self.writer.write_label(topLabel)

        self.advance()  # Consume 'while'
        self.advance()  # Consume '('

        # Compile expression (loop condition)
        self.compileExpression()

        # Negate the condition
        self.writer.write_arithmetic('not')

        # If condition is false, jump to continue label
        self.writer.write_if_goto(continueLabel)

        self.advance()  # Consume ')'
        self.advance()  # Consume '{'

        # Compile statements in the loop body
        self.compileStatements()

        self.advance()  # Consume '}'

        # Unconditional jump back to the top of the loop
        self.writer.write_goto(topLabel)

        # Continue label (loop exit)
        self.writer.write_label(continueLabel)


    def compileReturn(self):
        """
        compiles a return statement.
        """
        # self.doStartingBracket('returnStatement')
        self.advance()  # get 'return' keyword
        returnEmpty = True  # Flag to check if the return statement is empty

        while self.existExpression():
            returnEmpty = False  # Expression exists, update flag
            self.compileExpression() # also calling this from below

        if returnEmpty:
            # Empty return statement; push 0 as a placeholder for the return value
            self.writer.write_push('constant', 0)

        # Generate VM code for the return command
        self.writer.write_return()
        self.advance()  # get ';' symbol
        # self.doClosingBracket()


    # ----- Supporting Functions -----
    def compileSubroutineCall(self):
        # Support CompileDo
        firstName = lastName = fullName = ''
        nLocals = 0
        firstName = self.advance()[1]  # Consume class/subroutine/var name

        if self.checkNextToken(value="."):  # case of className.subroutineName
            self.advance()  # get '.' symbol
            lastName = self.advance()[1]  # Consume subroutine name

            if firstName in self.symbolTable.current_scope or firstName in self.symbolTable.global_scope:
                self.writePush(firstName, lastName)
                fullName = self.symbolTable.type_of(firstName) + '.' + lastName
                nLocals += 1
            else:
                fullName = firstName + '.' + lastName

        else:
            self.writer.write_push('pointer', 0)
            nLocals += 1
            fullName = self.className + '.' + firstName
        self.advance()  # Consume '(' symbol
        nLocals += self.compileExpressionList()
        self.writer.write_call(fullName, nLocals)
        self.advance()  # Consume ')' symbol

    def compileExpressionList(self):
        """
        Compiles an expression list.
        """
        # self.doStartingBracket('expressionList')
        counter = 0
        if self.existExpression():
            self.compileExpression()
            counter += 1
        while self.checkNextToken(value=","):  # case of multiple expressions
            self.advance()  # get ',' symbol
            self.compileExpression()
            counter += 1
        return counter
        # self.doClosingBracket()


    def compileArrayIndex(self, name):
        self.writeArrayIndex()
        if name in self.symbolTable.current_scope:
            if self.symbolTable.kind_of(name) == 'var':
                self.writer.write_push('local', self.symbolTable.index_of(name))
            elif self.symbolTable.kind_of(name) == 'arg':
                self.writer.write_push('argument', self.symbolTable.index_of(name))
        else:
            if self.symbolTable.kind_of(name) == 'static':
                self.writer.write_push('static', self.symbolTable.index_of(name))
            else:
                self.writer.write_push('this', self.symbolTable.index_of(name))
        self.writer.write_arithmetic('add')
        # print("test if any add in CompileArrayIndex")

    def writeArrayIndex(self):
        # Write Array index
        self.advance()  # get '[' symbol
        self.compileExpression()
        self.advance()  # get ']' symbol

    def compileExpression(self):
        # Needed from if, while, return
        """
        Compiles an expression.
        """
        # self.doStartingBracket('expression')
        self.compileTerm() # calling from below
        # print(f"Current token: {self.tokenizer.peek()}, binaryOp: {self.binaryOp}")

        while self.checkNextToken(values=self.binaryOp):
            op = self.advance()[1]  # get op symbol
            self.compileTerm()

            if op == '+':
                self.writer.write_arithmetic('add')  # Fixed method name
            elif op == '-':
                self.writer.write_arithmetic('sub')
            elif op == '*':
                self.writer.write_call('Math.multiply', 2)  # Fixed method name
            elif op == '/':
                self.writer.write_call('Math.divide', 2)  # Fixed method name
            elif op == '|':
                self.writer.write_arithmetic('or')
            elif op == '&':
                self.writer.write_arithmetic('and')
            elif op == '=':
                self.writer.write_arithmetic('eq')
            elif op == '<':
                self.writer.write_arithmetic('lt')
            elif op == '>':
                self.writer.write_arithmetic('gt')

        # self.doClosingBracket()

    def existExpression(self):
        return self.existTerm()

    def existTerm(self):
        return self.checkNextToken(token="integerConstant") or \
               self.checkNextToken(token="stringConstant") or \
               self.checkNextToken(token="identifier") or \
               self.checkNextToken(values=self.unaryOp) or \
               self.checkNextToken(values=self.keywordConstant) or \
               self.checkNextToken(value="(")

    def compileTerm(self):
        """
        Compiles a term.
        """
        # self.doStartingBracket('term')
        array = False  # Tracks if the current term is an array element
        # print("array = False")

        # if self.checkNextToken(token="integerConstant") or \
        # self.checkNextToken(token="stringConstant") or \
        # self.checkNextToken(values=self.keywordConstant):
        #     self.advance()  # Get constant

        # print("1. Identifier",array)

        if self.checkNextToken(token="integerConstant"):
            # Handle integer constants
            value = self.advance()[1]
            self.writer.write_push("constant", value)  # Fixed function reference

        elif self.checkNextToken(token="stringConstant"):
            # Handle string constants by creating a new string object
            value = self.advance()[1]
            self.writer.write_push("constant", len(value))
            self.writer.write_call("String.new", 1)
            for letter in value:
                self.writer.write_push("constant", ord(letter))
                self.writer.write_call("String.appendChar", 2)
        
        elif self.checkNextToken(values=self.keywordConstant):
            # Handle keyword constants like `true`, `false`, `null`, or `this`
            value = self.advance()[1]
            if value == "this":
                self.writer.write_push("pointer", 0)
            else:
                self.writer.write_push("constant", 0)
                if value == "true":
                    self.writer.write_arithmetic("not")  # Negate to represent true

        elif self.checkNextToken(token="identifier"):

            # Handle variables, array elements, or subroutine calls
            nLocals = 0
            name = self.advance()[1]
            # self.advance()  # Get class/var name
            # print("2. Identifier",array)

            if self.checkNextToken(value="["):  # Case of varName[expression]
                # print("2.1 Identifier",array)
                # print("array = True")
                array = True
                self.compileArrayIndex(name)
                # print("2.2 Identifier",array)
                # exit(0)

            # elif self.checkNextToken(value="("):  # Case of function call
            if self.checkNextToken(value="("):  # Case of function call
                nLocals += 1
                self.writer.write_push('pointer', 0)  # Push the current object
                self.advance()  # Skip '('
                nLocals += self.compileExpressionList()
                self.advance()  # Skip ')'
                self.writer.write_call(self.className + '.' + name, nLocals)

            elif self.checkNextToken(value="."):  # Case of subroutine call
                self.advance()  # Skip '.'
                lastName = self.advance()[1]
                if name in self.symbolTable.current_scope or name in self.symbolTable.global_scope:
                    self.writePush(name, lastName)
                    name = self.symbolTable.type_of(name) + "." + lastName
                    nLocals += 1
                else:
                    name = name + "." + lastName
                self.advance()  # Skip '('
                nLocals += self.compileExpressionList()
                self.advance()  # Skip ')'
                self.writer.write_call(name, nLocals)

            else:  # Handle variable or array element
                # print("3. Identifier",array)
                if array:
                    self.writer.write_pop("pointer", 1)
                    self.writer.write_push("that", 0)
                    # print("Did I came here with pointer and that?")
                elif name in self.symbolTable.current_scope:
                    if self.symbolTable.kind_of(name) == "var":
                        self.writer.write_push("local", self.symbolTable.index_of(name))
                    elif self.symbolTable.kind_of(name) == "arg":
                        self.writer.write_push("argument", self.symbolTable.index_of(name))
                else:
                    if self.symbolTable.kind_of(name) == "static":
                        self.writer.write_push("static", self.symbolTable.index_of(name))
                    else:
                        self.writer.write_push("this", self.symbolTable.index_of(name))

        elif self.checkNextToken(values=self.unaryOp):
            # Handle unary operators
            op = self.advance()[1]
            self.compileTerm()
            if op == "-":
                self.writer.write_arithmetic("neg")
            elif op == "~":
                self.writer.write_arithmetic("not")

        elif self.checkNextToken(value="("):
            # Handle parenthesized expressions
            self.advance()  # Get '(' symbol
            self.compileExpression()
            self.advance()  # Get ')' symbol

        # self.doClosingBracket()

    # Needly Added Function:
    def writePush(self, name, lastName):
        """
        Generates a push command for a variable or field.
        """
        if name in self.symbolTable.current_scope:
            if self.symbolTable.kind_of(name) == 'var':
                self.writer.write_push('local', self.symbolTable.index_of(name))
            elif self.symbolTable.kind_of(name) == 'arg':
                self.writer.write_push('argument', self.symbolTable.index_of(name))
        else:
            if self.symbolTable.kind_of(name) == 'static':
                self.writer.write_push('static', self.symbolTable.index_of(name))
            else:
                self.writer.write_push('this', self.symbolTable.index_of(name))

    def writePop(self, name):
        """
        Generates a pop command for a variable or field.
        """
        if name in self.symbolTable.current_scope:
            if self.symbolTable.kind_of(name) == 'var':
                self.writer.write_pop('local', self.symbolTable.index_of(name))
            elif self.symbolTable.kind_of(name) == 'arg':
                self.writer.write_pop('argument', self.symbolTable.index_of(name))
        else:
            if self.symbolTable.kind_of(name) == 'static':
                self.writer.write_pop('static', self.symbolTable.index_of(name))
            else:
                self.writer.write_pop('this', self.symbolTable.index_of(name))

def main():
    userInput = sys.argv[1]
    userInput = os.path.abspath(userInput)  # Ensure full absolute path

    if os.path.isdir(userInput):  # If input is a directory
        if not userInput.endswith("/"):
            userInput += "/"
        files = os.listdir(userInput)
        for file in files:
            if file.endswith(".jack"):
                fileName = os.path.splitext(file)[0]  # Get filename without extension
                parser = Parser(os.path.join(userInput, file), os.path.join(userInput, fileName + ".vm"))
                parser.compileClass()
                parser.writer.close()  # Ensure VM file is properly saved
    elif os.path.isfile(userInput):  # If input is a file
        fileName = os.path.splitext(userInput)[0]  # Get filename without extension
        parser = Parser(userInput, fileName + ".vm")
        parser.compileClass()
        parser.writer.close()  # Ensure VM file is properly saved
    else:
        raise Exception("The input is not valid, please try again")

if __name__ == "__main__":
    main()



