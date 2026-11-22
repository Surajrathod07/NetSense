import time
import joblib

DOMAINS = ("hospital", "factory", "disaster")


def normalize(text):
    return " ".join(text.lower().split())


def validate(text, domain):
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf8")) > 4096:
        raise ValueError("Enter a message of 1 to 4096 UTF-8 bytes.")
    if domain not in DOMAINS:
        raise ValueError("Choose hospital, disaster or factory.")


class Classifier:
    def __init__(self, path):
        self.bundle = joblib.load(path)

    def predict(self, text):
        validate(text, "factory")
        start = time.perf_counter()
        b = self.bundle
        model = b["pipeline"]
        if b["kind"] == "margin":
            score = -float(
                model.decision_function([text])[0]
            )  # classes: CRITICAL, NORMAL
        else:
            score = float(model.predict_proba([text])[0, 0])
        return dict(
            label="CRITICAL" if score >= b["threshold"] else "NORMAL",
            score=score,
            score_kind=b["kind"],
            model_version=b["version"],
            classification_ms=(time.perf_counter() - start) * 1000,
        )
