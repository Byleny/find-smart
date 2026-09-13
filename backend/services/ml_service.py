"""
ML Service — FinSmart
=====================
Tres modelos complementarios, seleccionados tras comparación experimental con CV-5:

1. CategoryClassifier  — Regresión Logística + TF-IDF (supervisado)
   Tarea  : predecir la categoría de una transacción a partir de su descripción.
   Por qué: seleccionada tras comparar 5 candidatos (NaiveBayes, LogisticRegression,
             LinearSVC, RF baseline, RF+char TF-IDF) con CV-5. LR alcanzó 90.9 %
             de exactitud, empatando con NB pero con probabilidades mejor calibradas
             y menor varianza (±0.028 vs ±0.055 del RF). Los modelos lineales
             superan a los de árbol en texto de alta dimensión con datasets pequeños.

2. AnomalyDetector    — Isolation Forest (no supervisado)
   Tarea  : detectar gastos inusualmente altos o bajos respecto al historial.
   Por qué: seleccionado al comparar con Local Outlier Factor. IF obtuvo mayor
             F1 (0.37 vs 0.30) al detectar anomalías sobre los datos de demostración.

3. PatternDetector    — TF-IDF + DBSCAN  (en ai_service.py, se mantiene)
   Tarea  : agrupar transacciones con descripciones similares y analizar
             su regularidad temporal para detectar pagos recurrentes.
"""

import pickle
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import LabelEncoder

# ── Persistencia de modelos ───────────────────────────────────────────────────

MODEL_DIR = Path(__file__).parent.parent / "ml_models"
MODEL_DIR.mkdir(exist_ok=True)

MIN_SAMPLES_PER_CLASS = 3   # mínimo por categoría para entrenar RF
MIN_TOTAL_SAMPLES = 10      # mínimo total de gastos


def _cat_path(user_id: int) -> Path:
    return MODEL_DIR / f"user_{user_id}_category.pkl"


def _anom_path(user_id: int) -> Path:
    return MODEL_DIR / f"user_{user_id}_anomaly.pkl"


def _metrics_path(user_id: int) -> Path:
    return MODEL_DIR / f"user_{user_id}_metrics.json"


def delete_user_models(user_id: int) -> None:
    for path in (_cat_path(user_id), _anom_path(user_id), _metrics_path(user_id)):
        path.unlink(missing_ok=True)


def _text(description: str) -> str:
    return description.lower().strip()


# ── 1. Random Forest — clasificación de categorías ────────────────────────────

def train_category_model(user_id: int, transactions) -> Optional[dict]:
    """
    Entrena un pipeline TF-IDF → LogisticRegression con las transacciones
    de tipo 'gasto' del usuario.

    Modelo seleccionado tras comparar 5 candidatos con CV-5 estratificada:
    LogisticRegression alcanzó 90.9 % de exactitud, la mayor entre los modelos
    evaluados, con la menor varianza entre particiones (±0.028).

    Retorna métricas de evaluación o None si no hay suficientes datos.
    """
    from collections import Counter
    from sklearn.linear_model import LogisticRegression

    expenses = [t for t in transactions if t.type == "gasto"]
    if len(expenses) < MIN_TOTAL_SAMPLES:
        return None

    cat_counts = Counter(t.category for t in expenses)
    valid_cats = {c for c, n in cat_counts.items() if n >= MIN_SAMPLES_PER_CLASS}

    filtered = [t for t in expenses if t.category in valid_cats]
    if len(filtered) < MIN_TOTAL_SAMPLES or len(valid_cats) < 2:
        return None

    X = [_text(t.description) for t in filtered]
    y = [t.category for t in filtered]

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            sublinear_tf=True,
            max_features=500,
            min_df=2,
            strip_accents="unicode",
        )),
        ("clf", LogisticRegression(
            C=1.0,
            max_iter=500,
            class_weight="balanced",
            solver="lbfgs",
            random_state=42,
        )),
    ])

    n_splits = min(5, min(cat_counts[c] for c in valid_cats))
    cv_scores, f1_scores = [], []
    if n_splits >= 2:
        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        cv_scores = cross_val_score(pipeline, X, y, cv=skf, scoring="accuracy")
        f1_scores = cross_val_score(pipeline, X, y, cv=skf, scoring="f1_weighted")

    pipeline.fit(X, y)

    # Top features: media del valor absoluto de coeficientes entre categorías
    feature_names = pipeline.named_steps["tfidf"].get_feature_names_out()
    importances = np.mean(np.abs(pipeline.named_steps["clf"].coef_), axis=0)
    top_idx = np.argsort(importances)[::-1][:10]
    top_features = [
        {"word": feature_names[i], "importance": round(float(importances[i]), 4)}
        for i in top_idx
    ]

    with open(_cat_path(user_id), "wb") as f:
        pickle.dump(pipeline, f)

    import json as _json
    result = {
        "accuracy":    round(float(np.mean(cv_scores)), 3) if len(cv_scores) else None,
        "f1_weighted": round(float(np.mean(f1_scores)), 3) if len(f1_scores) else None,
        "n_samples":   len(filtered),
        "n_categories": len(valid_cats),
        "categories":  sorted(valid_cats),
        "top_features": top_features,
        "cv_folds":    n_splits,
        "model":       "LogisticRegression",
    }
    with open(_metrics_path(user_id), "w") as f:
        _json.dump(result, f)
    return result


def predict_category(user_id: int, description: str) -> Optional[dict]:
    """
    Predice la categoría de una descripción usando el modelo entrenado del usuario.
    Retorna categoría sugerida, confianza y dos alternativas.
    """
    path = _cat_path(user_id)
    if not path.exists():
        return None

    try:
        with open(path, "rb") as f:
            pipeline = pickle.load(f)

        text = _text(description)
        proba = pipeline.predict_proba([text])[0]
        classes = pipeline.classes_
        order = np.argsort(proba)[::-1]

        return {
            "category": classes[order[0]],
            "confidence": round(float(proba[order[0]]), 3),
            "alternatives": [
                {"category": classes[order[i]], "confidence": round(float(proba[order[i]]), 3)}
                for i in range(1, min(3, len(classes)))
            ],
        }
    except Exception:
        return None


# ── 2. Isolation Forest — detección de anomalías ─────────────────────────────

def _build_features(transactions) -> tuple[np.ndarray, list]:
    """
    Construye la matriz de features para Isolation Forest.
    Features por transacción:
      - log(amount + 1)                   — magnitud del gasto
      - desviación respecto a la media     — qué tan atípico es en su categoría
      - día del mes                        — detecta patrones temporales
      - mes                                — estacionalidad
    """
    from collections import defaultdict
    cat_amounts: dict[str, list] = defaultdict(list)
    for t in transactions:
        cat_amounts[t.category].append(t.amount)

    cat_means = {c: np.mean(v) for c, v in cat_amounts.items()}
    cat_stds  = {c: max(np.std(v), 1.0) for c, v in cat_amounts.items()}

    rows, ids = [], []
    for t in transactions:
        mean = cat_means[t.category]
        std  = cat_stds[t.category]
        z    = (t.amount - mean) / std      # z-score dentro de la categoría
        rows.append([
            np.log1p(t.amount),             # log(amount)
            z,                               # desviación estándar
            t.date.day,                      # día del mes
            t.date.month,                    # mes
        ])
        ids.append(t.id)

    return np.array(rows, dtype=float), ids


def train_anomaly_model(user_id: int, transactions) -> bool:
    """
    Entrena Isolation Forest con los gastos históricos.
    contamination=0.02 → tasa de contaminación ajustada a la proporción real
    de anomalías observada en el historial de demostración (4 de 208, 1.92%),
    en lugar del valor por defecto de 8% usado inicialmente, que no se apoyaba
    en ninguna medición y penalizaba la precisión marcando gastos grandes pero
    legítimos (ver Sección 3.1.2.4 de la tesis).
    Retorna True si se entrenó correctamente.
    """
    expenses = [t for t in transactions if t.type == "gasto"]
    if len(expenses) < 10:
        return False

    X, _ = _build_features(expenses)

    iso = IsolationForest(
        n_estimators=200,
        contamination=0.02,
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    iso.fit(X)

    with open(_anom_path(user_id), "wb") as f:
        pickle.dump((iso, {t.id: i for i, t in enumerate(expenses)}, expenses), f)

    return True


def score_anomalies(user_id: int, transactions) -> list[dict]:
    """
    Calcula el score de anomalía para cada gasto.
    score < 0  → más anómalo  (Isolation Forest convention)
    Retorna lista con id, score y flag is_anomaly.
    """
    path = _anom_path(user_id)
    if not path.exists():
        return []

    expenses = [t for t in transactions if t.type == "gasto"]
    if not expenses:
        return []

    try:
        with open(path, "rb") as f:
            iso, _, _ = pickle.load(f)

        X, ids = _build_features(expenses)
        scores  = iso.decision_function(X)   # score: menor = más anómalo
        labels  = iso.predict(X)             # -1 = anómalo, 1 = normal

        return [
            {
                "transaction_id": ids[i],
                "anomaly_score": round(float(scores[i]), 4),
                "is_anomaly": bool(labels[i] == -1),
            }
            for i in range(len(ids))
        ]
    except Exception:
        return []


# ── 3. Comparación de modelos — para la tabla de resultados de la tesis ──────

def compare_category_models(user_id: int, transactions) -> Optional[list]:
    """
    Evalúa cinco clasificadores sobre las transacciones del usuario con CV-5
    y retorna una lista ordenada por exactitud (de mayor a menor).

    Modelos evaluados:
      - Naive Bayes (MultinomialNB)        — baseline bayesiano para texto
      - Regresión Logística                — baseline lineal regularizado
      - SVM Lineal (LinearSVC calibrado)   — fuerte en texto de alta dimensión
      - Random Forest baseline             — configuración original del sistema
      - Random Forest mejorado             — word+char TF-IDF, más árboles
    """
    from collections import Counter
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.svm import LinearSVC

    expenses = [t for t in transactions if t.type == "gasto"]
    if len(expenses) < MIN_TOTAL_SAMPLES:
        return None

    cat_counts = Counter(t.category for t in expenses)
    valid_cats = {c for c, n in cat_counts.items() if n >= MIN_SAMPLES_PER_CLASS}
    filtered = [t for t in expenses if t.category in valid_cats]
    if len(filtered) < MIN_TOTAL_SAMPLES or len(valid_cats) < 2:
        return None

    X = [_text(t.description) for t in filtered]
    y = [t.category for t in filtered]
    n_splits = min(5, min(cat_counts[c] for c in valid_cats))
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    def _word_vec(**kw):
        return TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), sublinear_tf=True,
            max_features=500, min_df=2, strip_accents="unicode", **kw,
        )

    candidates = [
        (
            "Naive Bayes",
            Pipeline([
                ("tfidf", TfidfVectorizer(
                    analyzer="word", ngram_range=(1, 2),
                    max_features=500, min_df=2, strip_accents="unicode",
                )),
                ("clf", MultinomialNB(alpha=0.1)),
            ]),
        ),
        (
            "Regresión Logística",
            Pipeline([
                ("tfidf", _word_vec()),
                ("clf", LogisticRegression(
                    C=1.0, max_iter=500, class_weight="balanced", random_state=42,
                )),
            ]),
        ),
        (
            "SVM Lineal",
            Pipeline([
                ("tfidf", _word_vec()),
                ("clf", CalibratedClassifierCV(
                    LinearSVC(C=1.0, max_iter=2000, random_state=42), cv=3,
                )),
            ]),
        ),
        (
            "Random Forest (baseline)",
            Pipeline([
                ("tfidf", _word_vec()),
                ("clf", RandomForestClassifier(
                    n_estimators=200, max_depth=8, min_samples_split=4,
                    min_samples_leaf=2, max_features="sqrt",
                    class_weight="balanced", random_state=42, n_jobs=-1,
                )),
            ]),
        ),
        (
            "Random Forest (mejorado)",
            Pipeline([
                ("features", FeatureUnion([
                    ("word", _word_vec()),
                    ("char", TfidfVectorizer(
                        analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
                        max_features=300, min_df=3, strip_accents="unicode",
                    )),
                ])),
                ("clf", RandomForestClassifier(
                    n_estimators=300, max_depth=10, min_samples_split=4,
                    min_samples_leaf=2, max_features="sqrt",
                    class_weight="balanced", random_state=42, n_jobs=-1,
                )),
            ]),
        ),
    ]

    results = []
    for name, pipe in candidates:
        try:
            acc = cross_val_score(pipe, X, y, cv=skf, scoring="accuracy")
            f1  = cross_val_score(pipe, X, y, cv=skf, scoring="f1_weighted")
            results.append({
                "model": name,
                "accuracy": round(float(np.mean(acc)), 3),
                "f1_weighted": round(float(np.mean(f1)), 3),
                "acc_std": round(float(np.std(acc)), 3),
            })
        except Exception as e:
            results.append({"model": name, "accuracy": None, "f1_weighted": None, "error": str(e)})

    results.sort(key=lambda r: (r.get("accuracy") or 0), reverse=True)
    return results


def compare_anomaly_models(user_id: int, transactions) -> Optional[list]:
    """
    Compara Isolation Forest vs Local Outlier Factor para detección de anomalías.
    Usa como referencia los gastos que superan mean + 4·std del total como
    proxy de las anomalías plantadas (no requiere etiquetas).
    """
    from sklearn.neighbors import LocalOutlierFactor

    expenses = [t for t in transactions if t.type == "gasto"]
    if len(expenses) < 10:
        return None

    X, ids = _build_features(expenses)
    amounts = np.array([t.amount for t in expenses])
    threshold = np.mean(amounts) + 4.0 * np.std(amounts)
    true_anom = {t.id for t in expenses if t.amount > threshold}

    candidates = [
        ("Isolation Forest", IsolationForest(
            n_estimators=200, contamination=0.02, random_state=42, n_jobs=-1,
        )),
        ("Local Outlier Factor", LocalOutlierFactor(
            n_neighbors=20, contamination=0.02,
        )),
    ]

    results = []
    for name, model in candidates:
        try:
            if isinstance(model, LocalOutlierFactor):
                labels = model.fit_predict(X)
            else:
                labels = model.fit(X).predict(X)

            flagged   = {ids[i] for i, l in enumerate(labels) if l == -1}
            n_found   = len(true_anom & flagged)
            precision = round(n_found / len(flagged), 3) if flagged else 0.0
            recall    = round(n_found / len(true_anom), 3) if true_anom else 0.0
            f1        = round(2 * precision * recall / (precision + recall), 3) if (precision + recall) > 0 else 0.0

            results.append({
                "model": name,
                "total_flagged": len(flagged),
                "known_found": n_found,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            })
        except Exception as e:
            results.append({"model": name, "error": str(e)})

    results.sort(key=lambda r: r.get("f1", 0), reverse=True)
    return results
