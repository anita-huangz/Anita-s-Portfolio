# Anita-s-Portfolio

Welcome to my portfolio. Below are links to AI platform, software engineering,
data science, and computer systems projects I've worked on.

Every project marked ✅ runs its full test suite offline in
[CI](.github/workflows/ci.yml) — no network, no API keys — across Python 3.11,
3.12, and 3.13.

## AI Platform Engineering

### ✅ [SEC Filing Intelligence](ai-platform-projects/sec-filing-intelligence)
A multi-agent research platform over SEC EDGAR filings, served as **both** an
HTTP API and an **MCP server**, with per-call token, cost, and latency telemetry.
Ask it a question about a public company; it plans the research, pulls the
filings and XBRL financials it needs, drafts a cited answer, then runs a separate
verification pass that checks every citation against the evidence gathered before
returning it.

- **Multi-provider model access** — Anthropic, AWS Bedrock, and a deterministic
  replay provider behind one interface, switched by config
- **LangGraph workflow** — plan → research ⇄ tools → analyze → verify, with a
  hard tool-call ceiling and least-privilege capability grants
- **Typed tool boundaries** — Pydantic contracts on every argument, strict JSON
  schemas at the model boundary
- **Telemetry** — tokens, estimated USD, latency percentiles, and failure kinds,
  sliced by model and tool
- **Redis** sessions and tool-result caching, degrading to in-process on outage
- **Evaluation harness** measuring accuracy, consistency, reliability, latency,
  and cost per run
- **Technical Tools Used**: Python, FastAPI, MCP, Pydantic, LangGraph, Claude via
  the Anthropic SDK and AWS Bedrock, Redis, httpx, pytest, Ruff, Docker,
  GitHub Actions — **154 tests**

## Software Engineer Projects

### ✅ [Earnings Drift Tracker](software-engineer-projects/earnings-drift-tracker)
- Measures post-earnings-announcement drift against the size of the analyst
  surprise, correlating the two
- Handles announcements on non-trading days, omits unmeasurable horizons rather
  than zero-filling them, and treats a zero consensus estimate as undefined
- **Technical Tools Used**: Python, pandas, NumPy, REST APIs (Financial Modeling
  Prep, Yahoo Finance), pytest, Ruff — **29 tests**

### ✅ [Factor Portfolio Simulator](software-engineer-projects/factor-based-portfolio-simulator)
- Point-in-time backtest of cross-sectional equity factor strategies with
  Fama-French 3-factor attribution
- Fixes a look-ahead bias in the original that overstated total return by 92
  percentage points; `examples/lookahead_demo.py` reproduces the comparison
- **Technical Tools Used**: Python, pandas, NumPy, statsmodels, yfinance,
  pytest, Ruff — **52 tests**

### [Course and Catalog Scheduling System](https://github.com/anita-huangz/Anita-s-Portfolio/tree/4c80e4de7d9151d7ddebcac4926bb1dbdb2a8141/software-engineer-projects/Course%20Catalog%20and%20Scheduling%20System)
- Helps manage and schedule university courses, preventing conflicts and ensuring efficient organization.  
- **Technical Tools Used**: Python’s OOP features, and efficient data filtering algorithms.

### [Single-player Card Game](https://github.com/anita-huangz/Anita-s-Portfolio/tree/8887e5d7fc0621222e80a78feef4c0a75e93b320/software-engineer-projects/card-game-system) 
- Simulates a poker-style card game where players make strategic decisions to maximize their scores.
- **Technical Tools Used**: Python’s OOP principles, random.shuffle for card shuffling, and a structured game loop for user interaction.

### [Web Crawler and Search Engine](https://github.com/anita-huangz/Anita-s-Portfolio/tree/6fa5abf9d5fdc6909b31c394229b0ec9bb392371/software-engineer-projects/web-crawler-and-search-engine) 
- Builds a custom search engine by crawling web pages, indexing their content, and allowing users to query information.
- **Technical Tools Used**: Python’s abc.MutableMapping for trie implementation, Flask for a web-based search UI, rich for a terminal UI, and web scraping utilities.

### [Performance Optimization and Caching](https://github.com/anita-huangz/Anita-s-Portfolio/tree/8c958119b3bb3764271e5238b49f862fdc024a9d/software-engineer-projects/performance-optimization)
- Improves computational efficiency by implementing caching mechanisms and optimizing memory usage.
- **Technical Tools Used**: Python’s functools.lru_cache, dictionary-based caching, generator functions, and pytest for validation.

## Data Science Projects
### 1. [Bitcoin Price Prediction](https://github.com/anita-huangz/Anita-s-Portfolio/tree/e24e895c5d50569398ddfd6ed4c0e42b03d300e2/data-science-projects/bitcoin-and-asset-trading)
- Forecasting Bitcoin prices using LSTM with 60-day lookback sequences, MinMax scaling, and dropout regularization, implemented through a full deep learning pipeline.
- Technical Tools Used: Python, TensorFlow/Keras, NumPy, Pandas, Matplotlib, Scikit-learn.

### 2. [Fake News Prediction](https://github.com/anita-huangz/Anita-s-Portfolio/tree/af6e5bd68562af6f32dc0e8928e66618a157128f/data-science-projects/fake-news-detection) 
- Classifying fake news articles using metadata, sentiment analysis, TF-IDF, and feature engineering through a full machine learning pipeline.
- **Technical Tools Used:** Python, Scikit-learn, Pandas, Seaborn, XGBoost, Matplotlib, TextBlob.

### 3. [Customer Churn Prediction](https://github.com/anita-huangz/Anita-s-Portfolio/tree/c8056a6a37c216867126b8e32ac26f9a80cab6f4/customer-churn-prediction) 
- Predicting customer churn using machine learning techniques. This project includes data exploration, model training, and evaluation.
- **Technical Tools Used**: Python, Scikit-learn, Pandas, Seaborn, Matplotlib.

### 4. [Stock-Bond Portfolio](https://github.com/anita-huangz/Anita-s-Portfolio/tree/c8056a6a37c216867126b8e32ac26f9a80cab6f4/Stock-Bond%20Portfolio)
- Optimizing a stock-bond portfolio across different timeframes by maximizing returns for a given level of risk, considering various market scenarios and investor preferences.
- **Technical Tools Used**: Python, Pandas, NumPy, Matplotlib.

### 5. [Cybersecurity Threat Analysis](https://github.com/anita-huangz/Anita-s-Portfolio/tree/978498cd0767a9ec24306e8bfb547f150cd35910/global-security-threats)
- Analyzing global cybersecurity threats from 2015-2024 using clustering, anomaly detection, and dimensionality reduction techniques to identify attack patterns, high-risk incidents, and emerging threats.
- **Technical Tools Used**: Python, Scikit-learn, Pandas, Seaborn, Matplotlib, t-SNE, PCA, K-Means, DBSCAN, Isolation Forest, Local Outlier Factor.

### 6. [Weather Historical Trends and Forecast](https://github.com/anita-huangz/Anita-s-Portfolio/tree/300fa6455724dc7cebc348c8126d99d02e0ed320/data-science-projects/weather-trends-and-forecast)
- Processes large datasets to uncover trends in weather patterns over time and do forecasts for future.
- **Technical Tools Used**: Python, pandas for data manipulation, matplotlib for data visualization, and requests for retrieving datasets.

## Computer Systems Projects
### 1. [Project 0: File Cleaner](computer-systems-notes/HuangAnitaProject0)
- This project involves cleaning up text files by removing unwanted elements like blank lines, whitespace, and comments.

### 2. [Project 1: Logic Gates](computer-systems-notes/HuangAnitaProject1)
- Summary: Built a set of elementary logic gates (e.g., AND, OR, XOR, MUX) that serve as fundamental building blocks for a computer's architecture.
- **Technical Tools Used**: Implemented using HDL (Hardware Description Language)

### 3. [Project 2: Boolean Arithmetic](computer-systems-notes/HuangAnitaProject2)
- Developed arithmetic logic components, including adders and an ALU, to perform arithmetic and logical operations.
- **Technical Tools Used**: Implemented in HDL, tested using the hardware simulator, and validated using predefined test scripts​

### 4. [Project 3: Memory](computer-systems-notes/HuangAnitaProject3)
- Built a RAM unit by constructing memory chips of increasing size and a program counter for controlling execution flow.
- **Technical Tools Used**: Implemented in HDL, tested using the hardware simulator, and validated using test scripts​

### 5. [Project 4: Machine Language](computer-systems-notes/HuangAnitaProject4)
- Developed and tested programs in Hack assembly language and translated them into binary machine code.
- **Technical Tools Used**: Used the Hack assembler to convert assembly into binary and tested execution using the CPU emulator​

### 6. [Project 5: Computer](computer-systems-notes/HuangAnitaProject5)
- Built a simple computer by integrating an ALU, registers, RAM, and a CPU capable of executing machine language instructions.
- **Technical Tools Used**: Implemented using HDL (Hardware Description Language), tested using the hardware simulator, and verified by executing machine language programs

### 7. [Project 6: Assembler](computer-systems-notes/HuangAnitaProject6)
- Developed an assembler to translate Hack assembly language into binary Hack machine code.
- **Technical Tools Used**: Implemented in a programming language of choice, compared output with a supplied assembler, and validated correctness using a CPU emulator

### 8. [Project 7: VM Translator I](computer-systems-notes/HuangAnitaProject7)
- Built a basic VM translator to convert VM commands into Hack assembly language, supporting arithmetic-logical and stack operations.
- **Technical Tools Used**: Implemented in a programming language of choice, tested using a CPU emulator, and optionally validated translations with a VM emulator​

### 9. [Project 8: VM Translator II](computer-systems-notes/HuangAnitaProject8)
- Extended the VM translator from Project 7 to handle branching and function commands, allowing for the translation of multi-file VM programs.
- **Technical Tools Used**: Implemented in a programming language of choice, tested using a CPU emulator, and used the VM emulator to verify translations​

### 10. [Project 9: Jack Programming](computer-systems-notes/HuangAnitaProject9)
- Created an interactive program or simple game using the Jack language 
- **Technical Tools Used**: Developed with Jack, compiled using the Jack compiler, and tested using the VM emulator​

### 11. [Project 10: Syntax Analyzer for Jack Programs](computer-systems-notes/HuangAnitaProject10)
- Developed a syntax analyzer that parses Jack programs and outputs XML reflecting the syntactic structure of the input source code.
- **Technical Tools Used**: Implemented in a programming language of choice, used a TextComparer tool for validation, and tested with an XML viewer

### 12. [Project 11: Syntax Analyzer for Jack Programs](computer-systems-notes/HuangAnitaProject11)
- Extended the syntax analyzer from Project 10 into a full-scale Jack compiler by implementing a Symbol Table and Code Generation module to produce executable VM code.
- **Technical Tools Used**: Implemented in a programming language of choice, tested using a VM emulator, and used the existing syntax analyzer from Project 10 as a base​

## How to Use
1. Clone this repository:
   ```bash
   git clone https://github.com/anita-huangz/Anita-s-Portfolio.git
   ```
