from __future__ import annotations

from pathlib import Path
from statistics import mean

from src.fit_processor import FitProcessor


def compare_fit_altitudes(reference_path: str | Path, candidate_path: str | Path) -> dict:
    processor = FitProcessor()
    reference = processor.read_fit_records(reference_path)
    candidate = processor.read_fit_records(candidate_path)
    differences = []
    for reference_record, candidate_record in zip(reference, candidate):
        reference_altitude = reference_record.get("altitude")
        candidate_altitude = candidate_record.get("altitude")
        if reference_altitude is None or candidate_altitude is None:
            continue
        differences.append(candidate_altitude - reference_altitude)

    absolute = [abs(value) for value in differences]
    return {
        "reference": str(reference_path),
        "candidate": str(candidate_path),
        "compared_points": len(differences),
        "mean_difference_m": mean(differences) if differences else None,
        "mean_absolute_difference_m": mean(absolute) if absolute else None,
        "max_absolute_difference_m": max(absolute) if absolute else None,
    }