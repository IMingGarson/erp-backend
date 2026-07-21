import re

import pandas as pd
from django.contrib.auth.models import User
from django.db import transaction

from .models import BOM, Material


class ExcelImportService:
    @staticmethod
    @transaction.atomic
    def import_bom_from_excel(file_obj):
        # 讀取 Excel，並強制將所有內容讀取為字串，避免 float 報錯
        df = pd.read_excel(file_obj, header=None).fillna("")
        rd_user = User.objects.filter(username="rd_user").first()

        # --- 1. 定位產品資訊 (Parent) ---
        prod_code = None
        prod_name = ""

        # 遍歷尋找產品編號位置
        for i, row in df.iterrows():
            # 修正點：確保 row 內所有元素都是 str 之後再 join
            row_values = [str(val).strip() for val in row.values]
            row_str = " ".join(row_values)

            if "產品編號:" in row_str:
                # 匹配 P 開頭的編號（支援帶有連字號的編號如 P9201015-4）
                match = re.search(r"P[A-Z0-9-]+", row_str)
                if match:
                    prod_code = match.group()

            if "產品名稱:" in row_str:
                try:
                    # 擷取產品名稱
                    name_part = row_str.split("產品名稱:")[1]
                    # 移除後方可能出現的欄位標籤
                    prod_name = re.split(r"製令數量|單據編號|開工日期", name_part)[
                        0
                    ].strip()
                except:
                    pass

        # 備案：如果 Excel 內找不到名稱，從 file_obj 名稱抓取
        if not prod_name and hasattr(file_obj, "name"):
            prod_name = file_obj.name.split(".")[0]

        if not prod_code:
            raise ValueError("找不到有效的產品編號 (P開頭)")

        # 建立/更新 產品本體 (對應新 ID 結構)
        parent_item, _ = Material.objects.update_or_create(
            code=prod_code,
            defaults={
                "name": prod_name,
                "type": "PRODUCT",
                "unit": "KG",
                "is_active": True,
            },
            created_by=rd_user,
        )

        # --- 2. 定位原料列表 (Children) ---
        header_idx = None
        for idx, row in df.iterrows():
            if "原料編號" in [str(v).strip() for v in row.values]:
                header_idx = idx
                break

        if header_idx is not None:
            # 取得標題列並清理空格
            columns = [str(c).strip() for c in df.iloc[header_idx]]
            df.columns = columns
            items_df = df.iloc[header_idx + 1 :]

            for _, row in items_df.iterrows():
                # 強制轉換編號為字串，防止數字編號變成 float
                m_code = str(row.get("原料編號", "")).strip()
                m_name = str(row.get("原料名稱", "")).strip()
                m_unit = str(row.get("單位", "KG")).strip()
                m_usage_raw = row.get("正常用量", 0)

                # 過濾掉空值或無效編號
                if m_code and m_code != "nan" and re.match(r"^[RP][0-9A-Z-]+$", m_code):
                    m_type = "RAW" if m_code.startswith("R") else "SEMI"

                    # 建立/更新 原料本體
                    child_item, _ = Material.objects.update_or_create(
                        code=m_code,
                        defaults={
                            "name": m_name,
                            "type": m_type,
                            "unit": m_unit,
                            "is_active": True,
                        },
                        created_by=rd_user,
                    )

                    # 處理用量數值轉換
                    try:
                        quantity = float(m_usage_raw)
                    except (ValueError, TypeError):
                        quantity = 0

                    # 建立 BOM 關聯 (Parent ID 與 Child ID)
                    BOM.objects.update_or_create(
                        parent=parent_item,
                        child=child_item,
                        defaults={"quantity_required": quantity},
                        created_by=rd_user,
                    )

        return parent_item
