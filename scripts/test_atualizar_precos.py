import json
import unittest

from atualizar_precos import (
    merge_products,
    normalize_product,
    parse_price,
    parse_vtex_json,
    require_scrape_success,
    validate_catalog,
)


class PriceUpdaterTests(unittest.TestCase):
    def test_parse_price_rejects_invalid_numbers(self):
        self.assertEqual(parse_price(float("nan")), 0.0)
        self.assertEqual(parse_price(float("inf")), 0.0)
        self.assertEqual(parse_price(-10), 0.0)
        self.assertEqual(parse_price(True), 0.0)

    def test_vtex_items_keep_package_variants_separate(self):
        payload = [{
            "productName": "Arroz Branco",
            "brand": "Marca",
            "link": "https://example.test/arroz",
            "items": [
                {"nameComplete": "Arroz Branco 1kg", "sellers": [{"commertialOffer": {"Price": 8.0}}]},
                {"nameComplete": "Arroz Branco 5kg", "sellers": [{"commertialOffer": {"Price": 25.0}}]},
            ],
        }]
        products = parse_vtex_json(json.dumps(payload), "arroz", {"name": "Test", "url": "https://example.test/{query}"}, 8)
        self.assertEqual([product["name"] for product in products], ["Arroz Branco 1kg", "Arroz Branco 5kg"])
        self.assertEqual([product["offers"][0]["price"] for product in products], [8.0, 25.0])

    def test_merge_preserves_existing_offers_during_partial_scrape(self):
        existing = normalize_product({
            "name": "Produto 1kg",
            "price": 10.0,
            "source": "Mercado Carrefour",
            "offers": [{"price": 10.0, "source": "Mercado Carrefour", "region": "Brasil"}],
        })
        merged = merge_products([existing], [])
        self.assertEqual(merged[0]["offers"][0]["price"], 10.0)
        validate_catalog(merged)

    def test_invalid_stats_are_rejected(self):
        product = normalize_product({"name": "Produto 1kg", "price": 10.0})
        product["price_stats"]["median"] = 9.0
        with self.assertRaises(ValueError):
            validate_catalog([product])

    def test_empty_scrape_aborts_publication(self):
        with self.assertRaisesRegex(RuntimeError, "existing catalog preserved"):
            require_scrape_success([], [{"nome": "Test", "produtos": 0, "erros": []}])


if __name__ == "__main__":
    unittest.main()
