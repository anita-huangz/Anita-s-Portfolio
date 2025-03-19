// c_push constant 3030
@3030
D=A
@SP
A=M
M=D
@SP
M=M+1
// c_pop pointer 0
@R3
D=A
@R13
M=D
@SP
M=M-1
A=M
D=M
@R13
A=M
M=D
// c_push constant 3040
@3040
D=A
@SP
A=M
M=D
@SP
M=M+1
// c_pop pointer 1
@R4
D=A
@R13
M=D
@SP
M=M-1
A=M
D=M
@R13
A=M
M=D
// c_push constant 32
@32
D=A
@SP
A=M
M=D
@SP
M=M+1
// c_pop this 2
@THIS
D=M
@2
D=D+A
@R13
M=D
@SP
M=M-1
A=M
D=M
@R13
A=M
M=D
// c_push constant 46
@46
D=A
@SP
A=M
M=D
@SP
M=M+1
// c_pop that 6
@THAT
D=M
@6
D=D+A
@R13
M=D
@SP
M=M-1
A=M
D=M
@R13
A=M
M=D
// c_push pointer 0
@R3
D=M
@SP
A=M
M=D
@SP
M=M+1
// c_push pointer 1
@R4
D=M
@SP
A=M
M=D
@SP
M=M+1
// add
@SP
M=M-1
A=M
D=M
@SP
M=M-1
A=M
M=D+M
@SP
M=M+1
// c_push this 2
@THIS
D=M
@2
A=D+A
D=M
@SP
A=M
M=D
@SP
M=M+1
// sub
@SP
M=M-1
A=M
D=M
@SP
M=M-1
A=M
M=M-D
@SP
M=M+1
// c_push that 6
@THAT
D=M
@6
A=D+A
D=M
@SP
A=M
M=D
@SP
M=M+1
// add
@SP
M=M-1
A=M
D=M
@SP
M=M-1
A=M
M=D+M
@SP
M=M+1
