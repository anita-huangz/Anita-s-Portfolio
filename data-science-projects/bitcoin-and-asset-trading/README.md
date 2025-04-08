# Bitcoin Price Prediction 

## 📦 Dataset Overview 
- **Source**: Kaggle dataset 
- **Size**: Over 50,000+ time steps (varies by granularity)
- **Features**:
  - Price columns: `Open`, `High`, `Low`, `Close`
  - Volume columns: `Volume_(BTC)`, `Volume_(Currency)`
  - Timestamps used to construct a sequential index
- **Target**: `Close` price (regression)


## 🧹 Preprocessing Steps
Goal: Prepare time series data for LSTM modeling.

- **Normalization**: `MinMaxScaler()` applied to the `Close` column
- **Sequence Construction**: 90-day lookback window used to create supervised learning sequences
- **Train/Test Split**: 80/20 split with optional shuffle disabled to preserve time order
- **Reshaping**: Input reshaped to 3D `(samples, timesteps, features)` for LSTM compatibility


## 🔧 Model Architecture

- **Loss**: Mean Squared Error (MSE)
- **Optimizer**: Adam (`lr=0.001`)
- **Regularization**: Dropout + EarlyStopping (`patience=10`)
- **Callbacks**: Restore best weights to avoid overfitting


## 📊 EDA Highlights

- **Rolling Statistics**: Moving averages, volatility, and Bollinger Bands visualized
- **Volume Surges**: Aligned with key market events (e.g., halving cycles, crashes)
- **MACD / RSI Trends**: Tracked to confirm momentum and overbought/oversold zones
- **Return Distributions**: Fat-tailed and non-normal, highlighting volatility risks


## 🧪 Model Evaluation

### Metrics Used
| Metric | Score | Notes |
|--------|-------|-------|
| RMSE   | ~500–1200 | Varies with granularity and data period |
| MAE    | Lower than RMSE | Indicates stable prediction accuracy |
| Visuals | ✅ | Actual vs. predicted curve plotted |

### Evaluation Strategy
- Predictions were inverse-transformed to original scale
- Performance tracked on validation set using EarlyStopping
- Rolling predictions visualized for interpretability


## 🔮 Future Improvements

- 📈 Add multivariate features (e.g., volume, technical indicators, macro inputs)
- 🧠 Try GRU, CNN, or Transformer-based models for long-sequence prediction
- 📊 Integrate real-time API feeds and backtesting engine
- ⏱ Evaluate impact of time interval changes (1min vs. 1hr vs. daily)