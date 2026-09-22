from __future__ import annotations

import os
import math
from io import BytesIO
from typing import Optional

import requests
import tifffile

from src.cache import AltitudeCache
class OpenTopographyProvider:
    """Caches raw COP30 GeoTIFF cells and interpolates FIT points locally."""

    def __init__(self, cache: Optional[AltitudeCache] = None, api_key: str | None = None, max_requests: int = 50, timeout: float = 20.0):
        self.cache = cache or AltitudeCache()
        self.api_key = api_key or os.environ.get("OPENTOPO_API_KEY")
        self.max_requests = max_requests
        self.timeout = timeout
        self.request_count = 0
        self.dataset = "COP30"
        self.manages_cache = True
        self.tile_span_degrees = 0.05
        self.errors: list[str] = []

    @property
    def budget_remaining(self) -> int:
        return max(0, self.max_requests - self.request_count)

    def get_cached_altitude(self, latitude: float, longitude: float) -> Optional[float]:
        return self.cache.get_interpolated_altitude(self.dataset, latitude, longitude)

    def _cache_geotiff_cells(self, content: bytes) -> int:
        with tifffile.TiffFile(BytesIO(content)) as raster:
            page = raster.pages[0]
            pixels = page.asarray()
            scale_tag = page.tags.get("ModelPixelScaleTag")
            tiepoint_tag = page.tags.get("ModelTiepointTag")
            if scale_tag is None or tiepoint_tag is None:
                raise ValueError("GeoTIFF COP30 sans géoréférencement exploitable")

            scale_x, scale_y, _ = scale_tag.value
            tie_i, tie_j, _, tie_x, tie_y, _ = tiepoint_tag.value[:6]
            nodata_tag = page.tags.get("GDAL_NODATA")
            nodata = float(nodata_tag.value.strip("\\x00 ")) if nodata_tag is not None else None
            cells: list[tuple[float, float, float]] = []
            for row_index, row in enumerate(pixels):
                latitude = tie_y - ((row_index - tie_j) + 0.5) * scale_y
                for column_index, value in enumerate(row):
                    altitude = float(value)
                    if nodata is not None and altitude == nodata:
                        continue
                    longitude = tie_x + ((column_index - tie_i) + 0.5) * scale_x
                    cells.append((latitude, longitude, altitude))

        self.cache.set_grid_cells(self.dataset, cells)
        return len(cells)

    def _fetch_raster_tile(self, south: float, north: float, west: float, east: float) -> int:
        response = requests.get(
            "https://portal.opentopography.org/API/globaldem",
            params={
                "demtype": self.dataset,
                "south": south,
                "north": north,
                "west": west,
                "east": east,
                "outputFormat": "GTiff",
                "API_Key": self.api_key,
            },
            timeout=self.timeout,
        )
        self.request_count += 1
        if not response.ok:
            detail = response.text.strip().replace("\n", " ")[:300]
            raise ValueError(f"HTTP {response.status_code}{': ' + detail if detail else ''}")
        return self._cache_geotiff_cells(response.content)

    def get_altitude_for_points(self, coordinates: list[tuple[float, float]]) -> list[tuple[float, float, Optional[float]]]:
        values: dict[tuple[float, float], Optional[float]] = {}
        missing_points: list[tuple[float, float]] = []

        for latitude, longitude in coordinates:
            cached = self.get_cached_altitude(latitude, longitude)
            if cached is not None:
                values[(latitude, longitude)] = cached
            else:
                missing_points.append((latitude, longitude))

        if not missing_points:
            return [(lat, lon, values.get((lat, lon))) for lat, lon in coordinates]

        # Regrouper les points manquants par cellules d'environ 100km (1 degré) 
        # pour éviter de demander une boîte englobante massive si les fichiers sont de régions différentes.
        clusters = {}
        for lat, lon in missing_points:
            cluster_key = (math.floor(lat), math.floor(lon))
            if cluster_key not in clusters:
                clusters[cluster_key] = []
            clusters[cluster_key].append((lat, lon))

        for cluster_points in clusters.values():
            if not self.api_key or self.request_count >= self.max_requests:
                break

            lats = [p[0] for p in cluster_points]
            lons = [p[1] for p in cluster_points]
            
            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)
            
            # Ajouter une marge pour permettre l'interpolation bilinéaire sur les bords
            margin = 0.01
            south = min_lat - margin
            north = max_lat + margin
            west = min_lon - margin
            east = max_lon + margin
            
            # Forcer une taille minimale de 0.05° pour éviter l'erreur HTTP 400 d'OpenTopography
            min_span = 0.05
            if north - south < min_span:
                diff = (min_span - (north - south)) / 2.0
                south -= diff
                north += diff
            if east - west < min_span:
                diff = (min_span - (east - west)) / 2.0
                west -= diff
                east += diff

            try:
                self._fetch_raster_tile(south, north, west, east)
            except requests.RequestException as error:
                self.errors.append(f"COP30 : erreur réseau pour l'emprise : {error.__class__.__name__}.")
            except (tifffile.TiffFileError, TypeError, ValueError) as error:
                self.errors.append(f"COP30 : échec de l'emprise [{south:.3f}, {north:.3f}, {west:.3f}, {east:.3f}] : {error}")

        # Récupération finale depuis le cache pour tous les points demandés
        for lat, lon in missing_points:
            alt = self.get_cached_altitude(lat, lon)
            if alt is None and not self.errors and self.request_count < self.max_requests:
                self.errors.append(f"COP30 : Point {lat:.6f}, {lon:.6f} toujours introuvable après téléchargement.")
            values[(lat, lon)] = alt

        return [(lat, lon, values.get((lat, lon))) for lat, lon in coordinates]
