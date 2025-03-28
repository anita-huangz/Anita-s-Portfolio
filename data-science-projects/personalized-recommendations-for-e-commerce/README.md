# 🛍️ Personalized Product Recommendation System - Model Evaluation Walkthrough

This project demonstrates a complete end-to-end machine learning evaluation pipeline using the Personalized Recommendations for E-Commerce dataset from Kaggle. The analysis includes cross-validation, hyperparameter tuning, scoring, thresholding, and validation curves.

# 🎯 Objective
To predict whether a customer will likely recommend a product using:
- **Classification:** Binary target (Recommend / Not Recommend)
- **Regression:** Continuous target (Probability of Recommendation)

# 🧠 Methods
1. Label encoding and multi-label binarization for history fields
2. Merged 200x100 customer-product pairs
3. Feature scaling with StandardScaler
4. Used RandomForestRegressor and RandomForestClassifier

# 📈 Key Outcomes
1. Built interpretable models for both regression and classification
2. Visualized threshold tuning and learning curve dynamics
3. Compared model performance to a dummy baseline
4. Achieved high performance using proper cross-validation methods

