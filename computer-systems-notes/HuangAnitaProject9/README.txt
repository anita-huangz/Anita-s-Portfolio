Project 9: FishGame: A Simple Fish Movement Simulator
=======================

Description:
This program is a simple fish movement simulator written in Jack. The game features a fish that moves based on keyboard input, consumes food, and grows after successfully consumed food. 

- The program reads keyboard inputs to change the fish's direction and moves the fish accordingly.
- It generates food at random positions, which the fish can eat to grow in size.

How to Run:
1. Unzip the package. 
2. Open the Jack Compiler, select src folder, and compile all .jack files in the directory.
3. Load the compiled .vm files into the VM Emulator.
4. se arrow keys to move the fish and avoid collisions.

Files Included:
1. Fish.jack - Handles fish movement, growth in size, and position changes.
2. FishGame.jack - Manages key game logics
3. Main.jack - Entry point of the game. Initializes the game loop, including a welcome screen
4. Random.jack - Reference file from Mark Armbrust, aims for generating random numbers for food placement.
5. RandSeed.jack - Provides seed-based random number generation 


Requirements:
- Nand2Tetris software (Jack Compiler & VM Emulator).
- Keyboard support for controlling fish movement.

What Works:
- Displays a "Welcome to game" message, and prompt the user to press any key to start the game
- Fish moves on the screen. 
- Reads keyboard input to move the moving fish.
- Generates and places food at random locations for fish to catch it.
- Displays a "Game Over" message.

What Doesn't Work:
- No error handling for invalid game states. 
- The game assumes the VM environment is correctly set up.
