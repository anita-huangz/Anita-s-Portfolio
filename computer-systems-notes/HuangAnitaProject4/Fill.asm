@R0
M=0

(LOOP)          // Main loop: check for keyboard input
    @KBD
    D=M         // Load the keyboard input value into D
    @BLACK
    D;JNE       // If a key is pressed (D != 0), jump to BLACK
    @WHITE
    0;JMP       // Otherwise (no key pressed), jump to WHITE

(BLACK)         // Fill the screen with black pixels
    @R0
    D=M         // Load the current pixel index
    @8192
    D=D-A       // Check if the index reached the end of the screen
    @LOOP
    D;JGE       // If at the end, restart the loop

    @R0         // Reload R0
    D=M
    
    @SCREEN
    A=D+A       // Access the current pixel memory address
    M=-1        // Write black (-1) to the pixel
    @R0
    M=M+1       // Move to the next pixel

    @LOOP
    0;JMP       // Repeat the loop

(WHITE)         // Clear the screen (fill with white pixels)
    @R0
    D=M
    @LOOP
    D;JLT       // If less than 0, restart the loop
    
    @R0         // Reload R0
    D=M
    
    @SCREEN
    A=D+A
    M=0         // Write white (0) to the pixel
    @R0
    M=M-1       // Move to the previous pixel
    
    @LOOP
    0;JMP       // Repeat the loop

(END)           // Infinite loop to stop execution
    @END
    0;JMP
