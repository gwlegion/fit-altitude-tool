import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.altitude_provider import OpenTopographyProvider
from src.cache import AltitudeCache
from src.fit_processor import FitProcessor
from src.settings import SettingsStore


class FakeFieldData:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class FakeFitDataMessage:
    def __init__(self, name, values):
        self.name = name
        self._values = values
        self.fields = [FakeFieldData(key, value) for key, value in values.items()]

    def get_values(self, field_name=None):
        if field_name is None:
            return self._values
        return self._values.get(field_name)


class RealLikeFitDataMessage:
    def __init__(self, name, field_values):
        self.name = name
        self.fields = [FakeFieldData(key, value) for key, value in field_values.items()]


class FitProcessorTests(unittest.TestCase):
    def _make_fit_path(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        fit_path = Path(tmp_dir.name) / "dummy.fit"
        fit_path.write_bytes(b"not a real fit")
        return fit_path

    def test_read_fit_records_extracts_record_points(self):
        frames = [
            FakeFitDataMessage("record", {"position_lat": 1000, "position_long": 2000, "altitude": 42.5}),
            FakeFitDataMessage("record", {"position_lat": 1500, "position_long": 2500}),
        ]

        fit_path = self._make_fit_path()
        with patch("src.fit_processor.fitdecode.FitReader") as reader_cls:
            reader_cls.return_value.__enter__.return_value.__iter__.return_value = iter(frames)
            records = FitProcessor().read_fit_records(fit_path)

        self.assertEqual(len(records), 2)
        self.assertAlmostEqual(records[0]["latitude"], 8.381903171539307e-05, places=12)
        self.assertAlmostEqual(records[0]["longitude"], 1.6763806343078614e-04, places=12)
        self.assertAlmostEqual(records[0]["altitude"], 42.5, places=7)
        self.assertTrue(records[0]["has_altitude"])
        self.assertFalse(records[1]["has_altitude"])

    def test_read_fit_records_ignores_non_record_messages(self):
        frames = [
            FakeFitDataMessage("device_info", {"manufacturer": 1}),
            FakeFitDataMessage("record", {"position_lat": 3000, "position_long": 4000, "altitude": 10}),
        ]

        fit_path = self._make_fit_path()
        with patch("src.fit_processor.fitdecode.FitReader") as reader_cls:
            reader_cls.return_value.__enter__.return_value.__iter__.return_value = iter(frames)
            records = FitProcessor().read_fit_records(fit_path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["altitude"], 10.0)

    def test_read_fit_records_reads_real_like_field_objects(self):
        frames = [
            RealLikeFitDataMessage("record", {"position_lat": 1000, "position_long": 2000, "altitude": 42.5}),
            RealLikeFitDataMessage("record", {"position_lat": 1500, "position_long": 2500}),
        ]

        fit_path = self._make_fit_path()
        with patch("src.fit_processor.fitdecode.FitReader") as reader_cls:
            reader_cls.return_value.__enter__.return_value.__iter__.return_value = iter(frames)
            records = FitProcessor().read_fit_records(fit_path)

        self.assertEqual(len(records), 2)
        self.assertAlmostEqual(records[0]["altitude"], 42.5, places=7)
        self.assertFalse(records[1]["has_altitude"])

    def test_process_altitude_resolution_populates_cache_before_write_back(self):
        class FakeCache:
            def __init__(self):
                self.values = {}

            def get(self, lat, lon):
                return self.values.get((round(lat, 6), round(lon, 6)))

            def set(self, lat, lon, altitude):
                self.values[(round(lat, 6), round(lon, 6))] = altitude

        class FakeProvider:
            def __init__(self):
                self.calls = []

            def get_altitude_for_points(self, coordinates):
                self.calls.append(list(coordinates))
                return [(lat, lon, 123.5) for lat, lon in coordinates]

        frames = [
            FakeFitDataMessage("record", {"position_lat": 1000, "position_long": 2000}),
            FakeFitDataMessage("record", {"position_lat": 1500, "position_long": 2500, "altitude": 10.0}),
        ]

        fit_path = self._make_fit_path()
        cache = FakeCache()
        provider = FakeProvider()
        with patch("src.fit_processor.fitdecode.FitReader") as reader_cls:
            reader_cls.return_value.__enter__.return_value.__iter__.side_effect = [iter(frames), iter(frames)]
            result = FitProcessor().process_altitude_resolution(fit_path, cache, provider)

        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result["phase_one"]["to_fetch"], [(8.381903171539307e-05, 1.6763806343078614e-04)])
        self.assertEqual(cache.get(8.381903171539307e-05, 1.6763806343078614e-04), 123.5)
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["debug_missing"], [])

    def test_opentopography_uses_cop30_cache_and_stops_at_budget(self):
        class FakeCache:
            def __init__(self):
                self.values = {}

            def get_interpolated_altitude(self, dataset, lat, lon):
                return self.values.get((dataset, round(lat, 6), round(lon, 6)))

            def set_interpolated_altitude(self, dataset, lat, lon, altitude):
                self.values[(dataset, round(lat, 6), round(lon, 6))] = altitude

        cache = FakeCache()
        provider = OpenTopographyProvider(cache=cache, api_key="test", max_requests=1)
        def fetch_raster(south, north, west, east):
            provider.request_count += 1
            cache.set_interpolated_altitude(provider.dataset, 48.1, 2.2, 123.0)

        with patch.object(provider, "_fetch_raster_tile", side_effect=fetch_raster) as request:
            first = provider.get_altitude_for_points([(48.1, 2.2)])
            second = provider.get_altitude_for_points([(48.1, 2.2)])
            blocked = provider.get_altitude_for_points([(48.2, 2.3)])

        request.assert_called_once()
        self.assertEqual(first, [(48.1, 2.2, 123.0)])
        self.assertEqual(second, [(48.1, 2.2, 123.0)])
        self.assertEqual(blocked, [(48.2, 2.3, None)])
        self.assertEqual(provider.request_count, 1)

    def test_opentopography_groups_points_in_the_same_raster_tile(self):
        class FakeCache:
            def __init__(self):
                self.values = {}

            def get_interpolated_altitude(self, dataset, lat, lon):
                return self.values.get((round(lat, 6), round(lon, 6)))

            def set_interpolated_altitude(self, lat, lon, altitude):
                self.values[(round(lat, 6), round(lon, 6))] = altitude

        cache = FakeCache()
        provider = OpenTopographyProvider(cache=cache, api_key="test")

        def fetch_raster(south, north, west, east):
            provider.request_count += 1
            cache.set_interpolated_altitude(48.101, 2.201, 100.0)
            cache.set_interpolated_altitude(48.102, 2.202, 101.0)
            return 4

        with patch.object(provider, "_fetch_raster_tile", side_effect=fetch_raster) as request:
            results = provider.get_altitude_for_points([(48.101, 2.201), (48.102, 2.202)])

        request.assert_called_once()
        self.assertEqual(results, [(48.101, 2.201, 100.0), (48.102, 2.202, 101.0)])

    def test_cop30_grid_cache_interpolates_from_four_raw_cells(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = AltitudeCache(Path(tmp_dir) / "cache.db")
            try:
                cache.set_grid_cells(
                    "COP30",
                    [
                        (0.0, 0.0, 10.0),
                        (0.0, 1.0, 20.0),
                        (1.0, 0.0, 30.0),
                        (1.0, 1.0, 40.0),
                    ],
                )

                altitude = cache.get_interpolated_altitude("COP30", 0.5, 0.5)
            finally:
                cache.close()

        self.assertEqual(altitude, 25.0)

    def test_cache_recreates_schema_after_database_file_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "cache.db"
            cache = AltitudeCache(database_path)
            cache.close()
            database_path.unlink()

            cache = AltitudeCache(database_path)
            try:
                self.assertIsNone(cache.get_interpolated_altitude("COP30", 48.1, 2.2))
                cache.set_grid_cell("COP30", 48.0, 2.0, 100.0)
                self.assertEqual(cache.get_grid_cell("COP30", 48.0, 2.0), 100.0)
            finally:
                cache.close()

    def test_settings_store_saves_the_api_key_outside_the_project(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "FITAltitudeTool" / "settings.json"
            settings = SettingsStore(settings_path)

            settings.save_api_key("  test-api-key  ")

            self.assertEqual(settings.load_api_key(), "test-api-key")
            self.assertTrue(settings_path.exists())

if __name__ == "__main__":
    unittest.main()
