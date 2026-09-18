# Fixture attribution

The receipt images and ground-truth JSON files in this directory come from **CORD v2**
(Park et al., "CORD: A Consolidated Receipt Dataset for Post-OCR Parsing", 2019), published by
NAVER Clova on Hugging Face as `naver-clova-ix/cord-v2` under the **CC BY 4.0** license.

They are downscaled copies of three validation-split receipts, used only to exercise OCR, prompt
building and the eval matchers in the test suite. Regenerate with
`uv run python scripts/make_fixtures.py`.
