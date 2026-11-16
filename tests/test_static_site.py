import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_static_site import build_single_file_premium_site, build_site


class StaticSiteBuildTest(unittest.TestCase):
    def test_build_generates_a_complete_shareable_site(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "site"
            result = build_site(project_root, output_dir)

            self.assertTrue((output_dir / "index.html").is_file())
            self.assertTrue((output_dir / "styles.css").is_file())
            self.assertTrue((output_dir / "app.js").is_file())
            self.assertGreater(len(result["products"]), 0)
            self.assertGreater(len(result["ufs"]), 0)

            html = (output_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="app"', html)
            self.assertIn('src="images/logo.png"', html)
            self.assertIn("app.js", html)
            self.assertIn("styles.css", html)

            css = (output_dir / "styles.css").read_text(encoding="utf-8")
            js = (output_dir / "app.js").read_text(encoding="utf-8")
            self.assertIn(".mobile-products", css)
            self.assertIn("@media (max-width: 700px)", css)
            self.assertIn("createMobileProductCard", js)
            self.assertIn("mobile-search-results", js)

            data = json.loads((output_dir / "data.json").read_text(encoding="utf-8"))
            first_product = data["products"][0]
            self.assertEqual(data["ufs"], result["ufs"])
            self.assertEqual(data["packages"], result["packages"])
            self.assertIn("NomeImg", first_product)
            self.assertIn("Prices", first_product)
            self.assertTrue((output_dir / "images" / first_product["NomeImg"]).is_file())

    def test_build_generates_a_self_contained_premium_html(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            premium_dir = project_root / "site-premium"
            image_dir = project_root / "images" / "img"
            premium_dir.mkdir(parents=True)
            image_dir.mkdir(parents=True)
            (premium_dir / "index.html").write_text(
                '<link rel="stylesheet" href="styles.css">'
                '<main id="app"></main><script src="app.js"></script>',
                encoding="utf-8",
            )
            (premium_dir / "styles.css").write_text(
                "body { color: red; }\n.mobile-products { display: grid; }",
                encoding="utf-8",
            )
            (premium_dir / "app.js").write_text(
                "window.loaded = true;\nfunction createMobileProductCard() {}",
                encoding="utf-8",
            )
            (image_dir / "product.png").write_bytes(b"image-bytes")
            manifest = {
                "ufs": ["AM"],
                "packages": ["Outros"],
                "products": [{"NomeImg": "product.png"}],
            }

            output_path = build_single_file_premium_site(project_root, manifest)
            html = output_path.read_text(encoding="utf-8")

            self.assertEqual(output_path.name, "arvore_precos_premium.html")
            self.assertIn(
                "<style>\nbody { color: red; }\n.mobile-products { display: grid; }\n</style>",
                html,
            )
            self.assertIn("window.loaded = true;\nfunction createMobileProductCard() {}", html)
            self.assertIn("window.PREMIUM_SITE_DATA=", html)
            self.assertIn("data:image/png;base64,aW1hZ2UtYnl0ZXM=", html)
            self.assertIn(".mobile-products", html)
            self.assertIn("createMobileProductCard", html)
            self.assertNotIn('href="styles.css"', html)
            self.assertNotIn('src="app.js"', html)


if __name__ == "__main__":
    unittest.main()
