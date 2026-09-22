from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import fitdecode
from fit_tool import FitFile, FitFileBuilder
from fit_tool.field_definition import FieldDefinition
from fit_tool.profile.messages.record_message import RecordMessage


@dataclass
class FitFileRecord:
    path: Path
    size_bytes: int
    status: str = "queued"


class FitProcessor:
    """Handles FIT file discovery, validation, and processing workflow."""

    def __init__(self):
        self.supported_extensions = {".fit"}

    @staticmethod
    def _get_cached_altitude(cache, latitude: float, longitude: float):
        interpolated_getter = getattr(cache, "get_interpolated_altitude", None)
        if interpolated_getter is not None:
            return interpolated_getter("COP30", latitude, longitude)
        return cache.get(latitude, longitude)

    @staticmethod
    def _get_missing_grid_nodes(cache, latitude: float, longitude: float, exact_points: bool = False) -> list[tuple[float, float]]:
        if exact_points:
            return [(latitude, longitude)] if cache.get(latitude, longitude) is None else []
        node_getter = getattr(cache, "get_missing_grid_nodes", None)
        if node_getter is None:
            return [(latitude, longitude)]
        return [(node_lat, node_lon) for _, _, node_lat, node_lon in node_getter(latitude, longitude)]

    @staticmethod
    def _set_cached_altitude(cache, latitude: float, longitude: float, altitude: float, exact_points: bool = False) -> None:
        if exact_points:
            cache.set(latitude, longitude, altitude)
            return
        node_setter = getattr(cache, "set_grid_node_at_coordinates", None)
        if node_setter is not None:
            node_setter(latitude, longitude, altitude)
            return
        cache.set(latitude, longitude, altitude)

    def discover_fit_files(self, source: str | Path) -> list[Path]:
        root = Path(source)
        if root.is_file() and root.suffix.lower() in self.supported_extensions:
            return [root]

        if root.is_dir():
            return sorted(
                [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in self.supported_extensions],
                key=lambda p: str(p).lower(),
            )

        return []

    def read_fit_file(self, file_path: str | Path) -> Optional[dict]:
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() not in self.supported_extensions:
            return None

        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "name": path.name,
        }

    @staticmethod
    def _normalize_scalar(raw_value):
        if raw_value is None:
            return None
        if hasattr(raw_value, "__iter__") and not isinstance(raw_value, (str, bytes, bytearray, dict)):
            try:
                return next(iter(raw_value), None)
            except TypeError:
                return raw_value
        return raw_value

    @staticmethod
    def _to_degrees(raw_value: Optional[int | float]) -> Optional[float]:
        raw_value = FitProcessor._normalize_scalar(raw_value)
        if raw_value is None:
            return None
        if raw_value == 0:
            return 0.0
        if not isinstance(raw_value, (int, float)):
            try:
                raw_value = float(raw_value)
            except (TypeError, ValueError):
                return None
        return raw_value * (180.0 / (2**31))

    @staticmethod
    def _read_fields_from_frame(frame) -> dict:
        values: dict[str, object] = {}
        fields = getattr(frame, "fields", None)
        if fields is not None:
            for field in fields:
                if hasattr(field, "name") and hasattr(field, "value"):
                    values[field.name] = field.value
            return values

        if hasattr(frame, "get_values"):
            for field_name in ("position_lat", "position_long", "altitude"):
                try:
                    values[field_name] = frame.get_values(field_name)
                except Exception:
                    values[field_name] = None
        return values

    def read_fit_records(self, file_path: str | Path) -> list[dict]:
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() not in self.supported_extensions:
            return []

        records: list[dict] = []
        with fitdecode.FitReader(path) as fit_file:
            for frame in fit_file:
                if hasattr(frame, "frame_type") and frame.frame_type != fitdecode.FIT_FRAME_DATA:
                    continue

                frame_name = getattr(frame, "name", None)
                if frame_name is not None and frame_name != "record":
                    continue
                if frame_name is None and not hasattr(frame, "fields") and not hasattr(frame, "get_values"):
                    continue

                values = self._read_fields_from_frame(frame)
                latitude = self._to_degrees(values.get("position_lat"))
                longitude = self._to_degrees(values.get("position_long"))
                altitude = self._normalize_scalar(values.get("altitude"))
                if latitude is None and longitude is None and altitude is None:
                    continue

                records.append(
                    {
                        "latitude": latitude,
                        "longitude": longitude,
                        "altitude": float(altitude) if altitude is not None else None,
                        "has_altitude": altitude is not None,
                        "raw": values,
                    }
                )

        return records

    def collect_missing_altitude_points(self, file_path: str | Path, cache, *, exact_points: bool = False, provider=None) -> dict:
        records = self.read_fit_records(file_path)
        to_fetch: list[tuple[float, float]] = []
        in_cache: list[dict] = []
        debug_missing: list[dict] = []
        seen: set[tuple[float, float]] = set()

        for index, record in enumerate(records):
            if record.get("has_altitude"):
                continue

            latitude = record.get("latitude")
            longitude = record.get("longitude")
            if latitude is None or longitude is None:
                debug_missing.append({"record_index": index, "latitude": latitude, "longitude": longitude, "reason": "missing_coordinates"})
                continue

            if provider is not None and hasattr(provider, "get_cached_altitude"):
                cached_altitude = provider.get_cached_altitude(latitude, longitude)
            else:
                cached_altitude = self._get_cached_altitude(cache, latitude, longitude)
            if cached_altitude is not None:
                in_cache.append({"record_index": index, "latitude": latitude, "longitude": longitude, "altitude": cached_altitude})
                continue

            for coord in self._get_missing_grid_nodes(cache, latitude, longitude, exact_points=exact_points):
                if coord in seen:
                    continue
                seen.add(coord)
                to_fetch.append(coord)

        return {
            "records": records,
            "to_fetch": to_fetch,
            "in_cache": in_cache,
            "debug_missing": debug_missing,
        }

    def populate_missing_altitudes(self, file_path: str | Path, cache, provider, *, max_batch: int | None = None) -> dict:
        exact_points = getattr(provider, "uses_exact_points", False)
        phase_one = self.collect_missing_altitude_points(file_path, cache, exact_points=exact_points)
        to_fetch = phase_one["to_fetch"]
        if max_batch is not None:
            to_fetch = to_fetch[:max_batch]

        fetched: list[tuple[float, float, float | None]] = []
        populated_points: list[dict] = []
        if to_fetch:
            fetched = provider.get_altitude_for_points(to_fetch)
            if not getattr(provider, "manages_cache", False):
                for latitude, longitude, altitude in fetched:
                    if altitude is None:
                        continue
                    self._set_cached_altitude(cache, latitude, longitude, altitude, exact_points=exact_points)
                    populated_points.append({
                        "latitude": latitude,
                        "longitude": longitude,
                        "altitude": altitude,
                    })

        phase_two = self.apply_cached_altitudes(file_path, cache)

        return {
            "phase_one": phase_one,
            "fetched": fetched,
            "populated_points": populated_points,
            "phase_two": phase_two,
            "debug_missing_after_phase_one": phase_one["debug_missing"],
            "debug_missing_after_phase_two": phase_two["debug_missing"],
        }

    def apply_cached_altitudes(self, file_path: str | Path, cache, *, exact_points: bool = False, provider=None) -> dict:
        records = self.read_fit_records(file_path)
        debug_missing: list[dict] = []
        updated_count = 0

        for index, record in enumerate(records):
            if record.get("has_altitude"):
                continue

            latitude = record.get("latitude")
            longitude = record.get("longitude")
            if latitude is None or longitude is None:
                debug_missing.append({"record_index": index, "latitude": latitude, "longitude": longitude, "reason": "missing_coordinates"})
                continue

            if provider is not None and hasattr(provider, "get_cached_altitude"):
                altitude = provider.get_cached_altitude(latitude, longitude)
            else:
                altitude = self._get_cached_altitude(cache, latitude, longitude)
            if altitude is None:
                debug_missing.append({"record_index": index, "latitude": latitude, "longitude": longitude, "reason": "missing_after_cache_fill"})
                continue

            record["altitude"] = altitude
            record["has_altitude"] = True
            updated_count += 1

        return {"records": records, "updated_count": updated_count, "debug_missing": debug_missing}

    def write_altitude_file(self, file_path: str | Path, cache, output_path: str | Path | None = None, provider=None) -> dict:
        source_path = Path(file_path)
        destination = Path(output_path) if output_path else source_path.with_name(f"{source_path.stem}_altitude{source_path.suffix}")
        fit_file = FitFile.from_file(str(source_path))
        data_messages = [record.message for record in fit_file.records if not record.is_definition]
        debug_missing: list[dict] = []
        updated_count = 0
        altitude_field_id = 2

        for record_index, message in enumerate(data_messages):
            if getattr(message, "name", None) != "record":
                continue

            latitude_field = message.get_field_by_name("position_lat")
            longitude_field = message.get_field_by_name("position_long")
            latitude = latitude_field.get_value() if latitude_field and latitude_field.is_valid() else None
            longitude = longitude_field.get_value() if longitude_field and longitude_field.is_valid() else None
            altitude_field = message.get_field_by_name("altitude")
            existing_altitude = altitude_field.get_value() if altitude_field and altitude_field.is_valid() else None
            if existing_altitude is not None:
                continue

            if latitude is None and longitude is None:
                continue
            if latitude is None or longitude is None:
                debug_missing.append({"record_index": record_index, "latitude": latitude, "longitude": longitude, "reason": "missing_coordinates"})
                continue

            if provider is not None and hasattr(provider, "get_cached_altitude"):
                altitude = provider.get_cached_altitude(latitude, longitude)
            else:
                altitude = self._get_cached_altitude(cache, latitude, longitude)
            if altitude is None:
                debug_missing.append({"record_index": record_index, "latitude": latitude, "longitude": longitude, "reason": "missing_after_cache_fill"})
                continue

            if message.definition_message.get_field_definition(altitude_field_id) is None:
                altitude_template = RecordMessage().get_field_by_name("altitude")
                altitude_template.set_value(0, altitude)
                message.definition_message.add_field_definition(FieldDefinition.from_field(altitude_template))
                message.set_definition_message(message.definition_message)

            altitude_field.growable = True
            altitude_field.set_value(0, altitude)
            altitude_field.growable = False
            updated_count += 1

        destination.parent.mkdir(parents=True, exist_ok=True)
        builder = FitFileBuilder()
        builder.add_all(data_messages)
        destination.write_bytes(builder.build_bytes())
        return {
            "output_path": str(destination),
            "updated_count": updated_count,
            "debug_missing": debug_missing,
        }

    def process_altitude_resolution(self, file_path: str | Path, cache, provider, *, max_batch: int | None = None) -> dict:
        exact_points = getattr(provider, "uses_exact_points", False)
        phase_one = self.collect_missing_altitude_points(file_path, cache, exact_points=exact_points, provider=provider)
        debug_missing = list(phase_one["debug_missing"])

        to_fetch = phase_one["to_fetch"]
        if max_batch is not None:
            to_fetch = to_fetch[:max_batch]
        if to_fetch:
            for latitude, longitude, altitude in provider.get_altitude_for_points(to_fetch):
                if altitude is not None and not getattr(provider, "manages_cache", False):
                    self._set_cached_altitude(cache, latitude, longitude, altitude, exact_points=exact_points)

        phase_two = self.apply_cached_altitudes(file_path, cache, exact_points=exact_points, provider=provider)
        debug_missing.extend(phase_two["debug_missing"])

        return {
            "phase_one": phase_one,
            "phase_two": phase_two,
            "debug_missing": debug_missing,
            "updated_count": phase_two["updated_count"],
        }

    def process_files_with_provider(self, paths: Iterable[str | Path], cache, provider) -> list[dict]:
        files = [Path(path) for path in paths]
        coordinates: list[tuple[float, float]] = []
        seen: set[tuple[float, float]] = set()
        per_file: dict[Path, list[dict]] = {}
        for path in files:
            records = self.read_fit_records(path)
            per_file[path] = records
            for record in records:
                latitude = record.get("latitude")
                longitude = record.get("longitude")
                if record.get("has_altitude") or latitude is None or longitude is None:
                    continue
                coordinate = (latitude, longitude)
                if coordinate not in seen:
                    seen.add(coordinate)
                    coordinates.append(coordinate)

        fetched = provider.get_altitude_for_points(coordinates)
        exact_points = getattr(provider, "uses_exact_points", False)
        if not getattr(provider, "manages_cache", False):
            for latitude, longitude, altitude in fetched:
                if altitude is not None:
                    self._set_cached_altitude(cache, latitude, longitude, altitude, exact_points=exact_points)

        results = []
        for path in files:
            records = per_file[path]
            has_gps = any(record.get("latitude") is not None and record.get("longitude") is not None for record in records)
            unresolved_points = []
            if has_gps:
                for record_index, record in enumerate(records):
                    if record.get("has_altitude"):
                        continue
                    latitude = record.get("latitude")
                    longitude = record.get("longitude")
                    if latitude is None or longitude is None or provider.get_cached_altitude(latitude, longitude) is None:
                        unresolved_points.append(record_index)

            if unresolved_points:
                output = {
                    "output_path": None,
                    "source_path": str(path),
                    "updated_count": 0,
                    "debug_missing": [
                        {"record_index": record_index, "reason": "missing_after_cache_fill"}
                        for record_index in unresolved_points
                    ],
                    "skipped_incomplete": True,
                }
            else:
                output = self.write_altitude_file(path, cache, provider=provider)
            output["has_gps"] = has_gps
            output["copied_without_gps"] = not has_gps
            results.append(output)
        return results
