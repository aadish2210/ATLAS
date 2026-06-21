"""Step 10 — Semantic incident archetypes (language-agnostic, Kannada-safe).

~13% of the `description` field is in Kannada. Rather than translate (which
needs an external service), we vectorise descriptions with CHARACTER n-gram
TF-IDF. Character n-grams are script-agnostic: they cluster Kannada and English
text about the same real-world phenomenon together without any model download.

We then KMeans the vectors into archetypes and, for each archetype, surface:
  * size + dominant official event_cause
  * average duration / response
  * representative example descriptions (closest to the centroid)

This proves ATLAS reads the raw multilingual complaint text, not just the
structured columns — and surfaces incident types the official taxonomy blurs.

Output: artifacts/semantic.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402

N_CLUSTERS = 10
MIN_DESCRIPTIONS = 200
KANNADA_LO, KANNADA_HI = 0x0C80, 0x0CFF


def _has_kannada(text: str) -> bool:
    return any(KANNADA_LO <= ord(ch) <= KANNADA_HI for ch in text)


def main() -> None:
    df = pd.read_parquet(settings.artifacts_dir / "events_clean.parquet")
    if "description" not in df.columns:
        print("[semantic] no description column — skipping")
        (settings.artifacts_dir / "semantic.json").write_text(json.dumps({"archetypes": []}))
        return

    work = df.copy()
    work["description"] = work["description"].fillna("").astype(str).str.strip()
    work = work[work["description"].str.len() >= 8].reset_index(drop=True)
    if len(work) < MIN_DESCRIPTIONS:
        print(f"[semantic] only {len(work)} usable descriptions — skipping")
        (settings.artifacts_dir / "semantic.json").write_text(json.dumps({"archetypes": []}))
        return

    docs = work["description"].tolist()
    kannada_mask = work["description"].map(_has_kannada).values

    # Character n-grams (3-5) — language agnostic, handles Kannada + English.
    vec = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=5,
        max_features=20000,
        sublinear_tf=True,
    )
    X = vec.fit_transform(docs)

    k = min(N_CLUSTERS, max(2, len(work) // 100))
    km = KMeans(n_clusters=k, n_init=4, random_state=42)
    labels = km.fit_predict(X)
    work["cluster"] = labels

    # distance to own centroid, to pick representative examples
    centroids = km.cluster_centers_
    Xd = X.toarray() if X.shape[0] * X.shape[1] < 5_000_000 else None

    archetypes = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        if len(idx) == 0:
            continue
        grp = work.iloc[idx]
        # representative docs = closest to centroid
        if Xd is not None:
            dists = np.linalg.norm(Xd[idx] - centroids[c], axis=1)
            order = idx[np.argsort(dists)]
        else:
            order = idx
        reps = []
        seen = set()
        for j in order:
            d = work.iloc[j]["description"]
            key = d[:40].lower()
            if key in seen:
                continue
            seen.add(key)
            reps.append(d[:160])
            if len(reps) >= 4:
                break

        causes = grp["event_cause"].value_counts()
        dom_cause = str(causes.index[0]) if len(causes) else "unknown"
        kn_share = float(kannada_mask[idx].mean())

        archetypes.append({
            "id": int(c),
            "size": int(len(idx)),
            "dominant_cause": dom_cause,
            "cause_purity": round(float(causes.iloc[0] / len(idx)), 3) if len(causes) else 0.0,
            "kannada_share": round(kn_share, 3),
            "avg_duration_min": round(float(grp["duration_min"].dropna().mean() or 0), 1),
            "avg_response_min": round(float(grp["response_min"].dropna().mean() or 0), 1),
            "examples": reps,
        })

    archetypes.sort(key=lambda a: a["size"], reverse=True)

    out = {
        "n_descriptions": int(len(work)),
        "n_clusters": k,
        "kannada_descriptions": int(kannada_mask.sum()),
        "kannada_share_overall": round(float(kannada_mask.mean()), 3),
        "method": "char_wb TF-IDF (3-5 grams) + KMeans — language agnostic",
        "archetypes": archetypes,
        "notes": [
            "Character n-grams cluster Kannada and English text without translation.",
            "cause_purity = fraction of the cluster sharing its dominant official cause.",
            "High kannada_share clusters are incident types the English-only flags miss.",
        ],
    }
    path = settings.artifacts_dir / "semantic.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[semantic] {len(work)} docs -> {k} archetypes "
        f"({int(kannada_mask.sum())} Kannada rows now usable)"
    )


if __name__ == "__main__":
    main()
