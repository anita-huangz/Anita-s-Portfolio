# Customer Churn Prediction

## Overview
This project aims to predict customer churn for a telecom company using machine learning techniques. The goal is to help businesses identify factors contributing to customer churn and take proactive steps to improve retention strategies. This is achieved by analyzing the provided dataset, training multiple machine learning models, and evaluating their performance.

## Problem Statement
Churn prediction is a critical task for businesses in customer-centric industries, where retaining customers is often more cost-effective than acquiring new ones. By accurately predicting churn, companies can take targeted actions to improve customer satisfaction and reduce churn rates.

## Key Steps in the Project
1. **Data Exploration and Preprocessing (EDA)**: Explore the dataset for any missing values, data inconsistencies, and outliers. Clean and prepare the data for model training.
2. **Feature Engineering**: Transform categorical variables into numerical ones, handle missing values, and scale numerical features.
3. **Model Training**: Train multiple machine learning models (Logistic Regression, Random Forest, SVM) to predict customer churn.
4. **Model Evaluation**: Evaluate model performance using metrics such as accuracy, precision, recall, ROC-AUC, and confusion matrix.
5. **Hyperparameter Tuning**: Tune the best-performing model to further improve accuracy.
6. **Results Interpretation**: Analyze the importance of features in predicting churn and provide business insights.

## Dataset
The dataset used in this project is from Kaggle: [Telco Customer Churn](https://www.kaggle.com/blastchar/telco-customer-churn).

### Data Columns:
- **customerID**: Unique identifier for each customer.
- **gender**: Gender of the customer.
- **SeniorCitizen**: Whether the customer is a senior citizen (1 or 0).
- **Partner**: Whether the customer has a partner (Yes or No).
- **Dependents**: Whether the customer has dependents (Yes or No).
- **tenure**: Number of months the customer has been with the company.
- **PhoneService**: Whether the customer has phone service (Yes or No).
- **MultipleLines**: Whether the customer has multiple lines (Yes or No).
- **InternetService**: The customer's internet service provider (DSL, Fiber optic, No).
- **OnlineSecurity**: Whether the customer has online security (Yes or No).
- **OnlineBackup**: Whether the customer has online backup (Yes or No).
- **DeviceProtection**: Whether the customer has device protection (Yes or No).
- **TechSupport**: Whether the customer has tech support (Yes or No).
- **StreamingTV**: Whether the customer has streaming TV (Yes or No).
- **StreamingMovies**: Whether the customer has streaming movies (Yes or No).
- **Contract**: The customer's contract type (Month-to-month, One year, Two year).
- **PaperlessBilling**: Whether the customer has paperless billing (Yes or No).
- **PaymentMethod**: The customer's payment method (Electronic check, Mailed check, Bank transfer, Credit card).
- **MonthlyCharges**: The amount charged to the customer monthly.
- **TotalCharges**: The total amount charged to the customer.
- **Churn**: Whether the customer churned (Yes or No).

## Model Evaluation Metrics
- **Accuracy**: The percentage of correctly predicted churns.
- **Precision**: The percentage of positive predictions that were correct.
- **Recall**: The percentage of actual positives that were correctly predicted.
- **ROC-AUC**: The area under the receiver operating characteristic curve, which evaluates the trade-off between true positives and false positives.
- **Confusion Matrix**: A table used to describe the performance of classification models.

## Technologies Used
- **Python**: Programming language used for data analysis and model building.
- **Pandas**: Data manipulation and analysis library.
- **Scikit-learn**: Machine learning library used for model training and evaluation.
- **Matplotlib**: Visualization library used for creating charts and graphs.
- **Seaborn**: Data visualization library based on Matplotlib.

## Installation
To set up the environment, install the required dependencies by running:

```bash
pip install -r requirements.txt
