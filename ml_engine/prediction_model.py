"""
Random Forest model for trade outcome prediction.
Designed for future use when enough labelled data accumulates.
"""
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from utils.logger import get_logger

log = get_logger("prediction_model")


class OutcomePredictor:
    """Binary classifier: will this trade be profitable?"""

    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            min_samples_leaf=5,
            random_state=42,
        )
        self.is_trained = False

    def train(self, X: np.ndarray, y: np.ndarray) -> dict:
        """
        Train on feature vectors X and binary labels y (1=profitable, 0=loss).
        Returns training metrics.
        """
        if len(X) < 20:
            log.warning(f"Only {len(X)} samples — need ≥20 for reliable training")
            return {"status": "insufficient_data", "samples": len(X)}

        self.model.fit(X, y)
        self.is_trained = True

        cv_scores = cross_val_score(self.model, X, y, cv=min(5, len(X) // 4), scoring="accuracy")

        importances = dict(zip(
            range(X.shape[1]),
            [round(float(v), 4) for v in self.model.feature_importances_],
        ))

        log.info(f"Model trained: accuracy={cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

        return {
            "status": "trained",
            "accuracy_mean": round(float(cv_scores.mean()), 4),
            "accuracy_std": round(float(cv_scores.std()), 4),
            "feature_importances": importances,
            "samples": len(X),
        }

    def predict_proba(self, features: list[float]) -> float:
        """Return probability of profitable trade (0-1)."""
        if not self.is_trained:
            return 0.5  # no opinion yet
        X = np.array([features])
        proba = self.model.predict_proba(X)[0]
        return float(proba[1]) if len(proba) > 1 else float(proba[0])
