import re
import json
import os
import gzip
import pandas as pd
from django.contrib.auth.models import User
from django.db import transaction
from django.conf import settings
from .models import BOM, Material
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

class UtilsFuncService:
    @staticmethod
    def to_decimal5(value):
        FIVE_DECIMALS = Decimal("0.00000")
        if value is None or value == "":
            return FIVE_DECIMALS
        try:
            return Decimal(str(value)).quantize(FIVE_DECIMALS, rounding=ROUND_HALF_UP)
        except (ValueError, TypeError, InvalidOperation):
            return FIVE_DECIMALS

class TFDALoopUpService:
    @staticmethod
    def import_tfda_open_data(search_term):
        if not search_term:
            return []
        
        path = os.path.join(str(settings.BASE_DIR), 'tfda.json.gz')
    
        merged_data = {}
        results = []
        data = []
        try:
            with gzip.open(path, 'rt', encoding='utf-8-sig') as f:
                data = json.load(f)
    
            target_nutrients = {
                "修正熱量": "energy_kcal",
                "熱量": "energy_kcal", 
                "粗蛋白": "protein",
                "粗脂肪": "fat",
                "飽和脂肪": "saturated_fat",
                "反式脂肪": "trans_fat", # 注意：TFDA 原始單位為 mg
                "總碳水化合物": "carbs",
                "糖質總量": "sugar",
                "鈉": "sodium"
            }
    
            for item in data:
                food_code = item.get("整合編號")
                if not food_code:
                    continue
    
                if food_code not in merged_data:
                    merged_data[food_code] = {
                        "code": food_code,
                        "category": item.get("食品分類", ""),
                        "name": item.get("樣品名稱", ""),
                        "synonym": item.get("俗名", ""),
                        "energy_kcal": "0", "protein": "0", "fat": "0",
                        "saturated_fat": "0", "trans_fat": "0", "carbs": "0",
                        "sugar": "0", "sodium": "0"
                    }
    
                analysis_item = item.get("分析項", "").strip()
                
                if analysis_item in target_nutrients:
                    raw_value = str(item.get("每100克含量", "")).strip()
                    # 清洗微量與空值
                    if raw_value in ["-", "微量", "未檢出", "Tr", "ND", ""]:
                        val = "0"
                    else:
                        val = raw_value
    
                    key_name = target_nutrients[analysis_item]
                    
                    if key_name == "energy_kcal" and analysis_item == "熱量" and merged_data[food_code]["energy_kcal"] != "0":
                        continue 
                    
                    merged_data[food_code][key_name] = val
                    
            for food in merged_data.values():
                name = food.get("name", "")
                synonym = food.get("synonym", "")
                
                if search_term in name or (synonym and search_term in synonym):
                    
                    try:
                        trans_fat_mg = float(food["trans_fat"])
                        trans_fat_g = trans_fat_mg / 1000.0
                        food["trans_fat"] = f"{trans_fat_g:.4f}".rstrip('0').rstrip('.') if trans_fat_g > 0 else "0"
                    except ValueError:
                        food["trans_fat"] = "0"
                        
                    results.append(food)
    
            return results
    
        except Exception as e:
            print(f"❌ TFDA Service Error: {e}")
            return []


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
