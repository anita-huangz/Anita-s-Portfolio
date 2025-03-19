from Tokenizer import Tokenizer
import sys
import os

class Parser:

    binaryOp = {'+', '-', '*', '/', '|', '=', '&lt;', '&gt;', '&amp;'}
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
        self.parsedRules = []
        self.outputFile = open(output, 'w')
        self.indent = ""


    # Indentation management
    def increaseIndent(self):
        self.indent += "  "

    def removeIndent(self):
        self.indent = self.indent[:-2]

    def doStartingBracket(self, rule):
        """
        Writes the opening tag for a non-terminal XML element.
        """
        self.outputFile.write(self.indent+"<"+rule+">\n")
        self.parsedRules.append(rule)
        self.increaseIndent()

    def doClosingBracket(self):
        """
        Writes the closing tag for the most recent non-terminal XML element.
        """
        self.removeIndent()
        rule = self.parsedRules.pop()
        self.outputFile.write(self.indent+"</"+rule+">\n")

    def writeTerminal(self, token, value):
        """
        Writes a terminal XML element for a token and its value.
        """
        self.outputFile.write(self.indent+"<"+token+"> "+value+" </"+token+">\n")

    def advance(self):
        """"
        Advances the tokenizer to the next token and
        writes it as a terminal XML element.
        """
        token_value = self.tokenizer.advance()
        if token_value:  # Ensure there is a token to unpack
            token, value = token_value
        else:
            raise Exception("Unexpected end of tokens in advance()")
        self.writeTerminal(token, value)

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
        self.doStartingBracket('class')
        self.advance()  # 'class'
        self.advance()  # Class name
        self.advance()  # '{'

        while self.checkNextToken(values={"static", "field"}):
            self.compileClassVarDec()

        while self.checkNextToken(values={"constructor", "method", "function"}):
            self.compileSubroutine()

        self.advance()  # '}'
        self.doClosingBracket()
        self.outputFile.close()

    def compileClassVarDec(self):
        """
        compiles a static declaration or a field declaration.
        """
        self.doStartingBracket('classVarDec')
        self.writeClassVarDec()
        self.doClosingBracket()

    def writeClassVarDec(self):
        self.advance()  # get 'static' or 'field'
        self.advance()  # get var type
        self.advance()  # get var name
        while self.checkNextToken(value=","):
            self.advance()  # get ',' symbol
            self.advance()  # get var name
        self.advance()  # get ';' symbol

    def compileSubroutine(self):
        """
        compiles a complete method, function, or constructor.
        """
        self.doStartingBracket('subroutineDec')
        self.advance()  # get subroutine type
        self.advance()  # get subroutine return type / 'constructor'
        self.advance()  # get subroutine name / 'new'
        self.advance()  # get '(' symbol
        self.compileParameterList() # Compiles a parameter list
        self.advance()  # get ')' symbol
        self.compileSubroutineBody()
        self.doClosingBracket()

    def compileParameterList(self):
        """
        Compiles a parameter list, excluding enclosing '()'.
        """
        self.doStartingBracket('parameterList')
        while not self.checkNextToken(token="symbol"):
            self.writeParam()
        self.doClosingBracket()

    def writeParam(self):
        self.advance()  # Parameter type
        self.advance()  # Parameter name
        if self.checkNextToken(value=","):
            self.advance()  # ','


    def compileSubroutineBody(self):
            self.doStartingBracket('subroutineBody')
            self.advance()  # '{'

            while self.checkNextToken(value="var"):
                self.compileVarDec()

            self.compileStatements()
            self.advance()  # '}'
            self.doClosingBracket()

    def compileVarDec(self):
        """
        Compiles a var declaration.
        """
        self.doStartingBracket('varDec')
        self.advance()  # 'var'
        self.advance()  # var type
        self.advance()  # var name
        while self.checkNextToken(value=","):
            self.advance()  # ','
            self.advance()  # var name
        self.advance()  # ';'
        self.doClosingBracket()


    # Compile a sequence of statements
    def compileStatements(self):
        """
        compiles a sequence of statements, not including the enclosing "{}".
        """
        self.doStartingBracket('statements')
        # make sure exist
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
        self.doClosingBracket()

    def compileDo(self):
        """
        compiles a do statement
        """
        self.doStartingBracket('doStatement')
        self.advance()  # get 'do' keyword
        self.compileSubroutineCall()
        self.advance()  # get ';' symbol
        self.doClosingBracket()

    def compileLet(self):
        """
        compiles a let statement
        """
        self.doStartingBracket('letStatement')
        self.advance()  # get 'let' keyword
        self.advance()  # get var name
        if self.checkNextToken(value="["): #case of varName[expression]
            self.writeArrayIndex()
        self.advance()  # get '='
        self.compileExpression()
        self.advance()  # get ';' symbol
        self.doClosingBracket()

    def compileIf(self):
        """
        Compiles an 'if' statement, possibly with an 'else' block.
        """
        self.doStartingBracket('ifStatement')
        self.advance()
        self.advance()
        self.compileExpression()
        self.advance()
        self.advance()
        self.compileStatements()
        self.advance()

        if self.checkNextToken(value="else"):
            self.advance()
            self.advance()
            self.compileStatements()
            self.advance()

        self.doClosingBracket()

    def compileWhile(self):
        """
        compiles a while statement
        """
        self.doStartingBracket('whileStatement')
        self.advance()  # get 'while' keyword
        self.advance()  # get '(' symbol
        self.compileExpression() # calling this from below
        self.advance()  # get ')' symbol
        self.advance()  # get '{' symbol
        self.compileStatements()
        self.advance()  # get '}' symbol
        self.doClosingBracket()

    def compileReturn(self):
        """
        compiles a return statement.
        """
        self.doStartingBracket('returnStatement')
        self.advance()  # get 'return' keyword
        while self.existExpression():
            self.compileExpression() # also calling this from below
        self.advance()  # get ';' symbol
        self.doClosingBracket()


    # Supporting Functions
    def compileSubroutineCall(self):
        # Support CompileDo
        self.advance()  # get class/subroutine/var name
        if self.checkNextToken(value="."):  # case of className.subroutineName
            self.advance()  # get '.' symbol
            self.advance()  # get subroutine name
        self.advance()  # get '(' symbol
        self.compileExpressionList()
        self.advance()  # get ')' symbol

    def compileExpressionList(self):
        """
        Compiles an expression list.
        """
        self.doStartingBracket('expressionList')
        if self.existExpression():
            self.compileExpression()
        while self.checkNextToken(value=","):  # case of multiple expressions
            self.advance()  # get ',' symbol
            self.compileExpression()
        self.doClosingBracket()

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
        self.doStartingBracket('expression')
        self.compileTerm() # calling from below
        while self.checkNextToken(values=self.binaryOp):
            self.advance()
            self.compileTerm()
        self.doClosingBracket()

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
        self.doStartingBracket('term')

        if self.checkNextToken(token="integerConstant") or \
        self.checkNextToken(token="stringConstant") or \
        self.checkNextToken(values=self.keywordConstant):
            self.advance()  # Get constant

        elif self.checkNextToken(token="identifier"):
            self.advance()  # Get class/var name

            if self.checkNextToken(value="["):  # Case of varName[expression]
                self.writeArrayIndex()

            elif self.checkNextToken(value="("):  # Case of function call
                self.advance()  # Get '(' symbol
                self.compileExpressionList()
                self.advance()  # Get ')' symbol

            elif self.checkNextToken(value="."):  # Case of subroutine call
                self.advance()  # Get '.' symbol
                self.advance()  # Get subroutine name
                self.advance()  # Get '(' symbol
                self.compileExpressionList()
                self.advance()  # Get ')' symbol

        elif self.checkNextToken(values=self.unaryOp):
            self.advance()  # Get unary operation symbol
            self.compileTerm()

        elif self.checkNextToken(value="("):
            self.advance()  # Get '(' symbol
            self.compileExpression()
            self.advance()  # Get ')' symbol

        self.doClosingBracket()


def main():
    userInput = sys.argv[1]
    userInput = os.path.abspath(userInput)  # Ensure full absolute path

    if os.path.isdir(userInput):  # If input is a directory
        if not userInput.endswith("/"):
            userInput += "/"
        files = os.listdir(userInput)
        for file in files:
            if file.endswith('.jack'):
                fileName = os.path.splitext(file)[0]  # Get filename without extension
                comp = Parser(os.path.join(userInput, file), os.path.join(userInput, fileName + ".xml"))
                comp.compileClass()
    elif os.path.isfile(userInput):  # If input is a file
        fileName = os.path.splitext(userInput)[0]  # Get filename without extension
        comp = Parser(userInput, fileName + ".xml")
        comp.compileClass()
    else:
        raise Exception("The input is not valid, please try again")

if __name__ == "__main__":
    main()

