import json
from io import BytesIO
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image

from fieldwise.documents.cord_import import iter_rows, map_gt_parse

SAMPLE_GT = {
    "menu": [
        {"nm": "NASI GORENG", "cnt": "2 x", "unitprice": "25.000", "price": "50.000"},
        {"nm": ["ES", "TEH"], "price": "8.000", "num": "2"},
    ],
    "sub_total": {"subtotal_price": "58.000", "tax_price": "5.800", "discount_price": "-5.000"},
    "total": {
        "total_price": "58.800",
        "cashprice": "100.000",
        "changeprice": "41.200",
        "menuqty_cnt": "3",
    },
}


def test_map_gt_parse_normalises_values_and_defaults_quantity() -> None:
    golden = map_gt_parse(SAMPLE_GT)
    assert golden["line_items"] == [
        {"name": "NASI GORENG", "quantity": 2, "unit_price": 25000.0, "line_total": 50000.0},
        {"name": "ES TEH", "quantity": 1, "unit_price": None, "line_total": 8000.0},
    ]
    assert golden["subtotal"] == 58000.0
    assert golden["discount"] == -5000.0
    assert golden["tax"] == 5800.0
    assert golden["service_charge"] is None
    assert golden["total"] == 58800.0
    assert golden["cash_paid"] == 100000.0
    assert golden["change"] == 41200.0
    assert golden["card_paid"] is None
    assert golden["item_count"] == 3


def test_map_gt_parse_accepts_single_menu_dict_and_list_sections() -> None:
    golden = map_gt_parse(
        {
            "menu": {"nm": "-TICKET CP", "cnt": "2", "price": "60.000"},
            "sub_total": [{"subtotal_price": "60.000"}, {"tax_price": "5.455"}],
            "total": {"total_price": "60.000", "creditcardprice": "60.000", "menuqty_cnt": "2.00"},
        }
    )
    assert golden["line_items"] == [
        {"name": "-TICKET CP", "quantity": 2, "unit_price": None, "line_total": 60000.0}
    ]
    assert golden["subtotal"] == 60000.0
    assert golden["tax"] == 5455.0
    assert golden["card_paid"] == 60000.0
    assert golden["item_count"] == 2


def test_map_gt_parse_falls_back_to_the_item_subtotal() -> None:
    golden = map_gt_parse(
        {
            "menu": {
                "nm": "BLUS WANITA",
                "unitprice": "@120,000",
                "cnt": "1",
                "itemsubtotal": "120,000",
            }
        }
    )
    assert golden["line_items"] == [
        {"name": "BLUS WANITA", "quantity": 1, "unit_price": 120000.0, "line_total": 120000.0}
    ]


def test_map_gt_parse_of_empty_ground_truth() -> None:
    golden = map_gt_parse({})
    assert golden["line_items"] == []
    assert all(golden[key] is None for key in golden if key != "line_items")


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 60), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_iter_rows_reads_parquet_in_order(tmp_path: Path) -> None:
    table = pa.table(
        {
            "image": [{"bytes": _jpeg(), "path": "a.jpg"}, {"bytes": _jpeg(), "path": "b.jpg"}],
            "ground_truth": [
                json.dumps({"gt_parse": SAMPLE_GT}),
                json.dumps({"gt_parse": {"menu": {"nm": "X", "price": "1.000"}}}),
            ],
        }
    )
    path = tmp_path / "validation-00000.parquet"
    pq.write_table(table, path)

    rows = list(iter_rows("validation", [path]))

    assert [r.external_id for r in rows] == ["cord-v2/validation/0000", "cord-v2/validation/0001"]
    assert rows[0].gt_parse == SAMPLE_GT
    assert rows[1].image.startswith(b"\xff\xd8")
