from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


class AltitudeCache:
    """SQLite cache for OpenTopography dataset values."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            db_path = app_data / "FITAltitudeTool" / "altitude_cache.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def close(self) -> None:
        if hasattr(self, 'conn') and self.conn:
            try:
                self.conn.close()
            except Exception:
                pass

    def __del__(self):
        self.close()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _init_db(self) -> None:
        with self._connection() as conn:
            self._ensure_schema(conn)

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS altitude_cache (
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                altitude REAL NOT NULL,
                PRIMARY KEY (lat, lon)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cop30_grid_cells (
                dataset TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                altitude REAL NOT NULL,
                PRIMARY KEY (dataset, lat, lon)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cop30_lon ON cop30_grid_cells(dataset, lon)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cop30_lat ON cop30_grid_cells(dataset, lat)")

    @staticmethod
    def _grid_coordinate(value: float) -> float:
        return round(float(value), 12)

    def get(self, lat: float, lon: float) -> Optional[float]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT altitude FROM altitude_cache WHERE lat = ? AND lon = ?",
                (round(lat, 6), round(lon, 6)),
            ).fetchone()
            if row is None:
                return None
            return float(row[0])

    def set(self, lat: float, lon: float, altitude: float) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO altitude_cache (lat, lon, altitude) VALUES (?, ?, ?)",
                (round(lat, 6), round(lon, 6), float(altitude)),
            )
            conn.commit()

    def get_grid_cell(self, dataset: str, lat: float, lon: float) -> Optional[float]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT altitude FROM cop30_grid_cells WHERE dataset = ? AND lat = ? AND lon = ?",
                (dataset, self._grid_coordinate(lat), self._grid_coordinate(lon)),
            ).fetchone()
            return float(row[0]) if row is not None else None

    def set_grid_cell(self, dataset: str, lat: float, lon: float, altitude: float) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cop30_grid_cells (dataset, lat, lon, altitude) VALUES (?, ?, ?, ?)",
                (dataset, self._grid_coordinate(lat), self._grid_coordinate(lon), float(altitude)),
            )

    def set_grid_cells(self, dataset: str, cells: list[tuple[float, float, float]]) -> None:
        if not cells:
            return
        rows = [
            (dataset, self._grid_coordinate(lat), self._grid_coordinate(lon), float(altitude))
            for lat, lon, altitude in cells
        ]
        with self._connection() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO cop30_grid_cells (dataset, lat, lon, altitude) VALUES (?, ?, ?, ?)",
                rows,
            )

    def get_interpolated_altitude(self, dataset: str, latitude: float, longitude: float) -> Optional[float]:
        latitude = self._grid_coordinate(latitude)
        longitude = self._grid_coordinate(longitude)
        with self._connection() as conn:
            west = conn.execute(
                "SELECT MAX(lon) FROM cop30_grid_cells WHERE dataset = ? AND lon <= ?",
                (dataset, longitude),
            ).fetchone()[0]
            east = conn.execute(
                "SELECT MIN(lon) FROM cop30_grid_cells WHERE dataset = ? AND lon >= ?",
                (dataset, longitude),
            ).fetchone()[0]
            south = conn.execute(
                "SELECT MAX(lat) FROM cop30_grid_cells WHERE dataset = ? AND lat <= ?",
                (dataset, latitude),
            ).fetchone()[0]
            north = conn.execute(
                "SELECT MIN(lat) FROM cop30_grid_cells WHERE dataset = ? AND lat >= ?",
                (dataset, latitude),
            ).fetchone()[0]

            if None in (west, east, south, north):
                return None

            rows = conn.execute(
                """
                SELECT lat, lon, altitude
                FROM cop30_grid_cells
                WHERE dataset = ? AND lat IN (?, ?) AND lon IN (?, ?)
                """,
                (dataset, south, north, west, east),
            ).fetchall()

        values = {(float(lat), float(lon)): float(altitude) for lat, lon, altitude in rows}
        southwest = values.get((float(south), float(west)))
        southeast = values.get((float(south), float(east)))
        northwest = values.get((float(north), float(west)))
        northeast = values.get((float(north), float(east)))
        if None in (southwest, southeast, northwest, northeast):
            return None

        if west == east and south == north:
            return southwest
        if west == east:
            north_weight = (latitude - south) / (north - south)
            return southwest * (1 - north_weight) + northwest * north_weight
        if south == north:
            east_weight = (longitude - west) / (east - west)
            return southwest * (1 - east_weight) + southeast * east_weight

        east_weight = (longitude - west) / (east - west)
        north_weight = (latitude - south) / (north - south)
        south_value = southwest * (1 - east_weight) + southeast * east_weight
        north_value = northwest * (1 - east_weight) + northeast * east_weight
        return south_value * (1 - north_weight) + north_value * north_weight

