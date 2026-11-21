from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/quickshell"))
from street_search import matches


def feature(lon, lat, **address):
    return {"geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"type": "street", "name": "Avenida Paulista", "city": "São Paulo", **address}}


class StreetSearchTests(unittest.TestCase):
    def test_nearby_segments_share_a_result_but_distinct_addresses_remain(self):
        results = matches([feature(-46.66, -23.55), feature(-46.661, -23.551, postcode="01311"),
                           feature(-46.66, -23.55, district="Bela Vista"), feature(-47, -24),
                           feature(-46.66, -23.55, type="house", street="Avenida Paulista", housenumber="10")])
        self.assertEqual(len(results), 4)
        self.assertEqual((results[0]["latitude"], results[0]["longitude"]), (-23.55, -46.66))
        self.assertTrue(results[0]["approximate"])
        self.assertIn("Bela Vista", results[1]["area"])
        self.assertEqual(results[-1]["title"], "Avenida Paulista 10")
        self.assertFalse(results[-1]["approximate"])

    def test_limit_and_unusable_results(self):
        self.assertEqual(matches([{}, feature(181, 12), feature(1, 2, type="country")]), [])
        self.assertEqual(len(matches([feature(n, n) for n in range(10)])), 5)
