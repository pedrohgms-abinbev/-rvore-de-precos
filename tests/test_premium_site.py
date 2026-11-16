import json
import tempfile
import unittest
from pathlib import Path


class PremiumSiteTest(unittest.TestCase):
    def test_premium_site_is_complete_and_shareable(self):
        project_root = Path(__file__).resolve().parents[1]
        site_dir = project_root / "site-premium"

        required_files = [
            "index.html",
            "styles.css",
            "app.js",
            "data.json",
        ]

        for file_name in required_files:
            self.assertTrue((site_dir / file_name).is_file(), file_name)

        html = (site_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn("app-header", html)
        self.assertIn('id="uf-filter"', html)
        self.assertIn('id="package-template"', html)
        self.assertIn("styles.css", html)
        self.assertIn("app.js", html)

        css = (site_dir / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn(".price-chart", css)
        self.assertIn("height: 370px", css)
        self.assertIn(".field select option", css)
        self.assertIn(".mobile-products", css)
        self.assertIn("@media (max-width: 700px)", css)
        self.assertIn(
            ":root.light .row-label .ttc,\n"
            ":root.light .row-label .pp,\n"
            ":root.light .row-label .calendar,\n"
            ":root.light .row-label .ctr { color: #fff; }",
            css,
        )

        js = (site_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("product.Prices?.TTC", js)
        self.assertIn("function ttcPrice(product)", js)
        self.assertIn("function productElevations(products)", js)
        self.assertIn(") * 170", js)
        self.assertNotIn("createPriceChart", js)
        self.assertNotIn("price-chart", js)
        self.assertIn("productCell.rowSpan = state.data.ufs.length", js)
        self.assertIn("state.data.ufs.entries()", js)
        self.assertIn("createMobileProductCard", js)
        self.assertIn("mobile-search-results", js)

        data = json.loads((site_dir / "data.json").read_text(encoding="utf-8"))
        self.assertIn("AM", data["ufs"])
        self.assertGreater(len(data["products"]), 0)
        self.assertGreater(len(data["packages"]), 0)

    def test_search_results_load_prices_from_each_product_uf_record(self):
        project_root = Path(__file__).resolve().parents[1]
        for site_name in ("site", "site-premium"):
            with self.subTest(site=site_name):
                site_dir = project_root / site_name
                js = (site_dir / "app.js").read_text(encoding="utf-8")
                data = json.loads((site_dir / "data.json").read_text(encoding="utf-8"))
                records = [product for product in data["products"] if product["Promax"] == 1898]

                self.assertIn("productsByPromaxAndUf", js)
                self.assertIn("priceSummary(priceRecord, \"TTC\")", js)
                self.assertIn("function commercialPriceText(record, field)", js)
                self.assertIn(".join(\"/\")", js)
                self.assertIn("formatPrice(channelPrices.C) === formatPrice(channelPrices.V)", js)
                self.assertNotIn("product.Prices?.[uf]", js)
                self.assertEqual(set(data["ufs"]), {product["UF"] for product in records})
                self.assertTrue(all(product["Prices"]["TTC"] is not None for product in records))

    def test_missing_wholesale_ttc_uses_available_reference_price(self):
        project_root = Path(__file__).resolve().parents[1]
        for site_name in ("site", "site-premium"):
            with self.subTest(site=site_name):
                site_dir = project_root / site_name
                js = (site_dir / "app.js").read_text(encoding="utf-8")
                data = json.loads((site_dir / "data.json").read_text(encoding="utf-8"))
                missing_ttc = [product for product in data["products"] if product["Prices"]["TTC"] is None]

                self.assertTrue(missing_ttc)
                self.assertTrue(all(product["TTC_Referencia"] is not None for product in missing_ttc))
                self.assertIn("field === \"TTC\" && Number.isFinite(record?.TTC_Referencia)", js)
                if site_name == "site-premium":
                    self.assertIn("Number.isFinite(product.TTC_Referencia) ? product.TTC_Referencia : null", js)

        generator = (project_root / "scripts" / "build_static_site.py").read_text(encoding="utf-8")
        self.assertIn('return price_for_channel(prices, "TTC", "V")', generator)

    def test_premium_prices_retain_and_label_wholesale_and_retail(self):
        project_root = Path(__file__).resolve().parents[1]
        site_dir = project_root / "site-premium"
        data = json.loads((site_dir / "data.json").read_text(encoding="utf-8"))
        products = {(product["UF"], product["Promax"]): product for product in data["products"]}

        missing_wholesale_ttc = products[("MS", 21020)]
        self.assertIsNone(missing_wholesale_ttc["ChannelPrices"]["TTC"]["C"])
        self.assertEqual(missing_wholesale_ttc["ChannelPrices"]["TTC"]["V"], 4.491)

        retail_only_calendar = products[("AM", 9069)]
        self.assertIsNone(retail_only_calendar["ChannelPrices"]["CAL"]["C"])
        self.assertEqual(retail_only_calendar["ChannelPrices"]["CAL"]["V"], 3.4890000000000003)

        different_channel_prices = products[("AM", 12948)]
        self.assertEqual(different_channel_prices["ChannelPrices"]["TTC"]["C"], 3.69)
        self.assertEqual(different_channel_prices["ChannelPrices"]["TTC"]["V"], 3.992)
        self.assertEqual(different_channel_prices["ChannelPrices"]["CAL"]["C"], 3.19)
        self.assertEqual(different_channel_prices["ChannelPrices"]["CAL"]["V"], 3.49)

        js = (site_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("function commercialPriceText(record, field)", js)
        self.assertIn("`R$ ${formatPrice(channelPrices[channel])} ${channel}`", js)
        self.assertIn('.join("/")', js)

        generator = (project_root / "scripts" / "build_static_site.py").read_text(encoding="utf-8")
        self.assertIn('"ChannelPrices": {', generator)
        self.assertIn('for field in ("TTC", "PP", "CAL")', generator)


if __name__ == "__main__":
    unittest.main()
