import os
import random
from datetime import date

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from factory.models import BatchInventory, Material


def generate_mock_batches():
    # 1. 取得所有原物料
    raw_materials = Material.objects.filter(type="RAW", is_active=True)

    if not raw_materials.exists():
        print("目前資料庫中沒有原物料，請先執行導入 Excel 的 API。")
        return

    print(f"開始為 {raw_materials.count()} 項原物料建立壓力測試批號...")

    batch_count = 0
    # 2. 設定三個不同的入庫日期（模擬新舊交替）
    dates = [
        date(2026, 1, 15),  # 舊批號 (可能剩餘量少)
        date(2026, 3, 10),  # 中期批號
        date(2026, 4, 25),  # 最新批號
    ]

    for material in raw_materials:
        for i, received_date in enumerate(dates):
            # 格式：YYYYMMDD + 物料編號後四碼 + 流水號
            # 例如：20260115R00201
            suffix = material.code[-4:].replace("-", "0")
            batch_id = f"{received_date.strftime('%Y%m%d')}{suffix}{i + 1}"

            # 模擬進貨量與剩餘量
            original = random.uniform(100.0, 500.0)
            # 越舊的批次，剩餘量隨機越少（模擬已使用）
            remaining_factor = (i + 1) / 3.0
            remaining = original * random.uniform(
                remaining_factor * 0.1, remaining_factor
            )

            BatchInventory.objects.update_or_create(
                batch_number=batch_id,
                defaults={
                    "material": material,
                    "original_qty": round(original, 4),
                    "remaining_qty": round(remaining, 4),
                    "received_date": received_date,
                },
            )
            batch_count += 1

    print(f"成功建立 {batch_count} 筆批號資料！")


if __name__ == "__main__":
    generate_mock_batches()
