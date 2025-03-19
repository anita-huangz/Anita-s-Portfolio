@R2
M=0     // Set R2 = 0

(LOOP)  // start of the loop
@R1
D=M     // Load R1 (RAM[1]) into D
@END
D;JEQ   // If R1 value == 0, go to END

@R0
D=M     // Load R0 (RAM[0]) into D
@R2
M=D+M   // Add R0 (D) to R2 (M = M + D)

@R1
M=M-1   // Decrement R1 (RAM[1]) by 1 [loop counter]
@LOOP
0;JMP   // Jump back to LOOP without any conditions

(END)   // End of the program
@END
0;JMP   // Inifite loop at end
