from datetime import datetime

class EarningsReport:
    def __init__(self, date, eps_actual, eps_estimate):
        self.date = datetime.strptime(date, "%Y-%m-%d")
        self.eps_actual = eps_actual # actual EPS reported by company
        self.eps_estimate = eps_estimate # expected EPS by analysts

    def surprise(self):
        return self.eps_actual - self.eps_estimate # raw difference

    def surprise_pct(self):
        if self.eps_estimate == 0:
            return 0
        return (self.surprise() / abs(self.eps_estimate)) * 100
