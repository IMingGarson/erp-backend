import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BOM, BatchInventory, Material, MaterialProvider, ProductProfile


class InitMockDataAPIView(APIView):
    """
    一鍵建立所有預設的產品、原料、包材、BOM、產品專屬規格與初始庫存 (包材與基數完美對應版)
    """

    def get_permissions(self):
        return [AllowAny()]

    def post(self, request):
        user = User.objects.first()
        if not user:
            return Response(
                {"error": "請先建立至少一個 User"}, status=status.HTTP_400_BAD_REQUEST
            )

        recipes = {
            # ---------------------------------------------------------
            # 1. 川辣椒麻浸料 (粉體)
            # ---------------------------------------------------------
            "P8501053": {
                "name": "川辣椒麻浸料",
                "type": "PRODUCT",
                "unit": "包",
                "spec": "1KG*20包/箱",
                "sales_unit": "箱",
                "sales_unit_quantity": 1.0,
                "sales_pack_unit": "包",
                "sales_pack_quantity": 20.0,
                "sales_price": 4800.00,
                "base_quantity": 20.0,  # 基準量：20KG
                "label_info": {
                    "product_name": "川辣椒麻浸料",
                    "origin": "台灣",
                    "storage": "常溫保存，貯存於乾燥陰涼處，開封後請儘速使用。",
                    "allergens": {
                        "contains": ["大豆", "乳類"],
                        "cross_contamination": ["甲殼類", "芒果", "花生"],
                    },
                },
                "items": [
                    # 內容物總和 = 20.0 KG
                    ("P8501053-1", "川辣椒麻浸料-裸粉", "SEMI", "KG", 20.0),
                    # 包裝耗材：生產 20KG 需要 20個內袋 + 20張貼紙 + 1個外箱
                    ("R8000001", "1KG用厚鋁箔袋", "PACK", "PCS", 20.0),
                    ("R8000002", "川辣椒麻浸料-專屬貼標", "PACK", "PCS", 20.0),
                    ("R8000003", "5號標準外箱(490*360*240)", "PACK", "PCS", 1.0),
                    ("R8000004", "外箱標籤貼紙", "PACK", "PCS", 1.0),
                ],
            },
            "P8501053-1": {
                "name": "川辣椒麻浸料-裸粉",
                "type": "SEMI",
                "unit": "KG",
                "base_quantity": 100.0,  # 基準量：100KG
                "items": [
                    # 內容物加總 = 100.0 KG
                    ("R5010022", "糖", "RAW", "KG", 45.0),
                    ("R5010002", "食鹽", "RAW", "KG", 25.0),
                    ("R4010030", "L-麩酸鈉", "RAW", "KG", 15.0),
                    ("R5020031", "辣椒粉", "RAW", "KG", 10.0),
                    ("R50200062", "洋蔥粉", "RAW", "KG", 5.0),
                ],
            },
            # ---------------------------------------------------------
            # 2. 香草烤雞翅浸料
            # ---------------------------------------------------------
            "P8500013": {
                "name": "香草烤雞翅浸料",
                "type": "PRODUCT",
                "unit": "KG",
                "spec": "散裝 20KG/袋",
                "sales_unit": "袋",
                "sales_unit_quantity": 1.0,
                "sales_pack_unit": "袋",
                "sales_pack_quantity": 1.0,  # 單袋直接販售
                "sales_price": 2500.00,
                "base_quantity": 100.0,  # 基準量：100KG
                "label_info": {
                    "product_name": "香草烤雞翅浸料",
                    "origin": "台灣",
                    "storage": "請密封存放於陰涼乾燥處，避免陽光直射。",
                    "allergens": {
                        "contains": ["大豆", "小麥"],
                        "cross_contamination": [],
                    },
                },
                "items": [
                    # 原料直接混成成品，內容物加總 = 100.0 KG
                    ("R5010002", "精鹽", "RAW", "KG", 30.0),
                    ("R5010022", "砂糖", "RAW", "KG", 25.0),
                    ("R4010030", "味素", "RAW", "KG", 15.0),
                    ("R2000015", "太白粉", "RAW", "KG", 9.8),
                    ("R5010018", "HVP水解蛋白", "RAW", "KG", 5.0),
                    ("R7010008-1", "蒜粉", "RAW", "KG", 3.5),
                    ("R50200062", "洋蔥粉", "RAW", "KG", 3.0),
                    ("R5020034", "甜椒粉", "RAW", "KG", 2.0),
                    ("R50200453", "咖哩粉", "RAW", "KG", 2.0),
                    ("R50100192", "無味素高鮮", "RAW", "KG", 1.0),
                    ("R4010031", "STPP多磷酸鈉", "RAW", "KG", 0.8),
                    ("R4010032", "TSPP焦磷酸鈉", "RAW", "KG", 0.8),
                    ("R5020060", "披薩草粉", "RAW", "KG", 0.5),
                    ("R5020036", "百里香葉", "RAW", "KG", 0.3),
                    ("R5020053", "迷迭香粉", "RAW", "KG", 0.3),
                    ("R5020069", "披薩葉", "RAW", "KG", 0.2),
                    ("R5020048", "月桂葉粉", "RAW", "KG", 0.2),
                    ("R5020066", "羅勒葉", "RAW", "KG", 0.2),
                    ("R5020068", "巴西里", "RAW", "KG", 0.1),
                    ("R5020136", "胡荽粉", "RAW", "KG", 0.1),
                    ("R5020025", "丁香粉", "RAW", "KG", 0.1),
                    ("R50200311", "紅辣椒粉", "RAW", "KG", 0.1),
                    # 包裝耗材：生產 100KG 剛好需要 5個 20KG的大袋子與耗材
                    ("R8000015", "20KG內袋", "PACK", "PCS", 5.0),
                    ("R8000016", "20KG包裝外袋", "PACK", "PCS", 5.0),
                    ("R8000017", "大號防潮束帶", "PACK", "PCS", 5.0),
                    ("R8000018", "香草烤雞通用大貼紙", "PACK", "PCS", 5.0),
                ],
            },
            # ---------------------------------------------------------
            # 3. 鹽酥雞醃粉-宇潔
            # ---------------------------------------------------------
            "P8500099": {
                "name": "鹽酥雞醃粉-宇潔",
                "type": "PRODUCT",
                "unit": "包",
                "spec": "1KG*50包/箱",
                "sales_unit": "箱",
                "sales_unit_quantity": 1.0,
                "sales_pack_unit": "包",
                "sales_pack_quantity": 50.0,
                "sales_price": 8500.00,
                "base_quantity": 50.0,  # 基準量：50KG
                "label_info": {
                    "product_name": "鹽酥雞專用醃粉",
                    "origin": "台灣",
                    "storage": "常溫保存，請避免潮濕環境。",
                    "allergens": {
                        "contains": ["大豆", "小麥"],
                        "cross_contamination": [],
                    },
                },
                "items": [
                    # 內容物加總 = 50.0 KG
                    ("R5010022", "砂糖", "RAW", "KG", 17.0),
                    ("R5010002", "精鹽", "RAW", "KG", 13.0),
                    ("R4010030", "味素", "RAW", "KG", 9.0),
                    ("R2000015", "太白粉", "RAW", "KG", 6.0),
                    ("R7010008-1", "蒜粉", "RAW", "KG", 2.0),
                    ("R50200183", "黑胡椒粉", "RAW", "KG", 1.0),
                    ("R50200391", "五香粉", "RAW", "KG", 0.6),
                    ("R50200402", "七里香粉", "RAW", "KG", 0.4),
                    ("R4010031", "STPP", "RAW", "KG", 0.3),
                    ("R4010032", "TSPP", "RAW", "KG", 0.3),
                    ("R5020038", "八角粉", "RAW", "KG", 0.2),
                    ("R40100271", "二氧化矽", "RAW", "KG", 0.1),
                    ("R4010041", "蔗糖素", "RAW", "KG", 0.1),
                    # 包裝耗材：生產 50KG 需要 50袋 + 50貼紙 + 1個大外箱
                    ("R8000010", "1KG空白包裝袋", "PACK", "PCS", 50.0),
                    ("R8000012", "宇潔客製化產品貼紙", "PACK", "PCS", 50.0),
                    ("R8000011", "3號加厚外箱", "PACK", "PCS", 1.0),
                ],
            },
            # ---------------------------------------------------------
            # 4. 特香麻辣鍋 (液體桶裝)
            # ---------------------------------------------------------
            "P9201015-4": {
                "name": "特香麻辣鍋(降辣10%)",
                "type": "PRODUCT",
                "unit": "桶",
                "spec": "20KG/桶",
                "sales_unit": "桶",
                "sales_unit_quantity": 1.0,
                "sales_pack_unit": "桶",
                "sales_pack_quantity": 1.0,
                "sales_price": 3800.00,
                "base_quantity": 20.0,  # 基準量：20KG
                "label_info": {
                    "product_name": "特製麻辣鍋底醬",
                    "origin": "台灣",
                    "storage": "冷藏保存，開封後請於 7 日內使用完畢。",
                    "allergens": {"contains": ["大豆", "小麥", "芝麻", "蝦", "魚類"]},
                },
                "items": [
                    # 內容物總和 = 20.0 KG
                    ("R3000009", "大豆沙拉油", "RAW", "KG", 12.0),
                    ("P9201015-5", "麻辣鍋調味粉(半成品)", "SEMI", "KG", 4.0),
                    ("R6000007", "醬油", "RAW", "KG", 1.5),
                    ("R6000021", "香菇素蠔油", "RAW", "KG", 1.0),
                    ("R3000001", "香油", "RAW", "KG", 0.8),
                    ("R7050003", "白芝麻粉", "RAW", "KG", 0.5),
                    ("R5020111", "湯底滷料", "RAW", "KG", 0.2),
                    # 包裝耗材：生產 20KG 只需要 1個桶子
                    ("R8000030", "20KG塑膠方桶", "PACK", "PCS", 1.0),
                    ("R8000031", "方桶防漏墊片", "PACK", "PCS", 1.0),
                    ("R8000032", "築間麻辣鍋外桶大貼標", "PACK", "PCS", 1.0),
                ],
            },
            "P9201015-5": {
                "name": "麻辣鍋調味粉(半成品)",
                "type": "SEMI",
                "unit": "KG",
                "base_quantity": 50.0,  # 基準量：50KG
                "items": [
                    # 內容物加總 = 50.0 KG
                    ("R5010022", "砂糖", "RAW", "KG", 13.0),
                    ("R5010018", "HVP水解大豆蛋白", "RAW", "KG", 8.0),
                    ("R5020031", "辣椒粉", "RAW", "KG", 6.0),
                    ("R5010015", "豬肉抽出物", "RAW", "KG", 5.0),
                    ("R7010006", "紅蔥酥", "RAW", "KG", 4.0),
                    ("R7010009", "蒜酥", "RAW", "KG", 4.0),
                    ("R5010011", "柴魚粉", "RAW", "KG", 2.5),
                    ("R5020023", "花椒粉", "RAW", "KG", 2.0),
                    ("R5020004", "白胡椒細粉", "RAW", "KG", 2.0),
                    ("R50200453", "咖哩粉", "RAW", "KG", 1.0),
                    ("R50100192", "無味素高鮮", "RAW", "KG", 1.0),
                    ("R5010013", "香菇精粉", "RAW", "KG", 0.5),
                    ("R5020038", "八角粉", "RAW", "KG", 0.5),
                    ("R50200402", "七里香粉", "RAW", "KG", 0.5),
                ],
            },
            # ---------------------------------------------------------
            # 5. 川辣麻婆醬 (含子粉體)
            # ---------------------------------------------------------
            "P9205102": {
                "name": "川辣麻婆醬",
                "type": "PRODUCT",
                "unit": "桶",
                "spec": "10KG/桶",
                "sales_unit": "桶",
                "sales_unit_quantity": 1.0,
                "sales_pack_unit": "桶",
                "sales_pack_quantity": 1.0,
                "sales_price": 2400.00,
                "base_quantity": 10.0,  # 基準量：10KG
                "label_info": {
                    "product_name": "川辣麻婆醬",
                    "origin": "台灣",
                    "storage": "常溫保存，開罐後請冷藏。",
                    "allergens": {"contains": ["大豆", "小麥", "芝麻"]},
                },
                "items": [
                    # 內容物總和 = 10.0 KG
                    ("R3000009", "大豆沙拉油", "RAW", "KG", 4.0),
                    ("R6000005", "辣豆瓣醬", "RAW", "KG", 3.0),
                    ("P9205102-1", "川辣麻婆醬調味粉", "SEMI", "KG", 1.5),
                    ("R6000007", "萬家香醬油", "RAW", "KG", 1.0),
                    ("R6000021", "香菇素蠔油", "RAW", "KG", 0.5),
                    # 包裝耗材
                    ("R8000035", "10KG專用圓桶", "PACK", "PCS", 1.0),
                    ("R8000036", "10KG食品級耐熱內袋", "PACK", "PCS", 1.0),
                    ("R8000037", "川辣麻婆通用防水貼紙", "PACK", "PCS", 1.0),
                ],
            },
            "P9205102-1": {
                "name": "川辣麻婆醬調味粉",
                "type": "SEMI",
                "unit": "KG",
                "base_quantity": 20.0,  # 基準量：20KG
                "items": [
                    # 內容物加總 = 20.0 KG
                    ("R5010002", "精鹽", "RAW", "KG", 5.0),
                    ("R5010025", "黃糖", "RAW", "KG", 4.0),
                    ("R5020031", "辣椒粉", "RAW", "KG", 3.0),
                    ("R5010018", "HVP水解大豆蛋白", "RAW", "KG", 2.0),
                    ("R5020023", "花椒粉", "RAW", "KG", 1.5),
                    ("R7010008-1", "蒜粉", "RAW", "KG", 1.0),
                    ("R7010006", "紅蔥酥", "RAW", "KG", 1.0),
                    ("R7010009", "蒜酥", "RAW", "KG", 1.0),
                    ("R5020104", "老薑粉", "RAW", "KG", 0.5),
                    ("R5020028", "韓式辣椒粉", "RAW", "KG", 0.5),
                    ("R5010014", "白肉精", "RAW", "KG", 0.5),
                ],
            },
        }

        materials_created = 0
        boms_created = 0
        profiles_created = 0

        try:
            with transaction.atomic():
                for parent_code, data in recipes.items():
                    # 1. 建立母件 (Material)
                    parent_mat, _ = Material.objects.get_or_create(
                        code=parent_code,
                        defaults={
                            "name": data["name"],
                            "type": data["type"],
                            "unit": data.get("unit", "KG"),
                            "created_by": user,
                        },
                    )
                    materials_created += 1

                    # 1.1 若為成品，建立專屬 ProductProfile
                    if data["type"] == "PRODUCT":
                        ProductProfile.objects.get_or_create(
                            material=parent_mat,
                            defaults={
                                "spec": data.get("spec", ""),
                                "sales_unit": data.get("sales_unit", "箱"),
                                "sales_unit_quantity": data.get(
                                    "sales_unit_quantity", 1.0
                                ),
                                "sales_pack_unit": data.get("sales_pack_unit", "包"),
                                "sales_pack_quantity": data.get(
                                    "sales_pack_quantity", 1.0
                                ),
                                "sales_price": data.get("sales_price", 0),
                                "label_info": data.get("label_info", {}),
                            },
                        )
                        profiles_created += 1

                    # 2. 建立子件與 BOM (確保使用字典中定義的 base_quantity)
                    current_base_quantity = data.get("base_quantity", 10.0)

                    for (
                        child_code,
                        child_name,
                        child_type,
                        child_unit,
                        exact_qty,
                    ) in data["items"]:
                        child_mat, _ = Material.objects.get_or_create(
                            code=child_code,
                            defaults={
                                "name": child_name,
                                "type": child_type,
                                "unit": child_unit,
                                "created_by": user,
                            },
                        )
                        materials_created += 1

                        BOM.objects.get_or_create(
                            parent=parent_mat,
                            child=child_mat,
                            defaults={
                                "base_quantity": Decimal(str(current_base_quantity)),
                                "quantity_required": Decimal(str(exact_qty)),
                                "created_by": user,
                            },
                        )
                        boms_created += 1

                # 3. 為所有的 RAW 與 PACK 入庫，確保工單可以扣料
                today = timezone.now().date()
                inventory_materials = Material.objects.filter(type__in=["RAW", "PACK"])

                for mat in inventory_materials:
                    batch_num = f"{today.strftime('%Y%m%d')}-{mat.code}"

                    # 依據單位決定給予的初始庫存數量
                    initial_qty = "10000.00" if mat.unit == "PCS" else "700.00"

                    BatchInventory.objects.get_or_create(
                        material=mat,
                        batch_number=batch_num,
                        defaults={
                            "original_qty": Decimal(initial_qty),
                            "remaining_qty": Decimal(initial_qty),
                            "received_date": today,
                            "expiration_date": today + timedelta(days=90),
                            "created_by": user,
                        },
                    )

            return Response(
                {
                    "message": "真實且精準的 Mock Data 已經成功寫入資料庫！",
                    "stats": {
                        "total_materials_processed": materials_created,
                        "total_product_profiles": profiles_created,
                        "total_boms_created": boms_created,
                        "total_inventory_batches": inventory_materials.count(),
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


from django.db.models import Q
from rest_framework.views import APIView

from .models import (
    PurchaseRequisition,
    PurchaseRequisitionItem,
)


class InitPurchaseMockDataAPIView(APIView):
    """
    動態抓取資料庫內的 原物料 (RAW) 與 包材 (PACK) 資料 (排除標籤)，
    並生成近 90 天內的歷史請購單，用以驗證 estimated_cost 的加權平均成本算法。
    """

    def get_permissions(self):
        return [AllowAny()]

    def post(self, request):
        user = User.objects.first()
        if not user:
            return Response(
                {"error": "請先建立至少一個 User"}, status=status.HTTP_400_BAD_REQUEST
            )

        # 1. 準備通用的供應商 (若不存在則建立)
        provider, _ = MaterialProvider.objects.get_or_create(
            code="MOCK_V01",
            defaults={
                "name": "預設模擬供應商",
                "tax_id": "99999999",
                "note": "系統自動產生的測試用供應商",
                "created_by": user,
            },
        )

        # 2. 單一 Query 提取目標物料：
        #    條件：(類型為 RAW) OR (類型為 PACK 且 名稱不包含 "貼")，並確保是啟用狀態
        target_materials = Material.objects.filter(
            Q(type="RAW") | (Q(type="PACK") & ~Q(name__icontains="貼")), is_active=True
        )

        if not target_materials.exists():
            return Response(
                {"error": "資料庫內找不到符合條件的 RAW 或 PACK 物料，請先建立資料。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requisitions_created = 0

        try:
            with transaction.atomic():
                today = timezone.now().date()

                for mat in target_materials:
                    # 產生過去 90 天內的 3 個隨機日期作為進貨日
                    purchase_dates = [
                        today - timedelta(days=random.randint(1, 29)),
                        today - timedelta(days=random.randint(30, 59)),
                        today - timedelta(days=random.randint(60, 89)),
                    ]

                    # 決定這項物料的基礎單價 (RAW 用 100 當基準，PACK 用 10 當基準)
                    base_price = 100.0 if mat.type == "RAW" else 10.0

                    for p_date in purchase_dates:
                        # 隨機波動價格 (± 15%)
                        price_fluctuation = base_price * random.uniform(0.85, 1.15)
                        # 隨機進貨數量 (RAW: 100~500 KG, PACK: 1000~5000 個)
                        qty = (
                            random.randint(100, 500)
                            if mat.type == "RAW"
                            else random.randint(1000, 5000)
                        )

                        # 建立請購單
                        req = PurchaseRequisition.objects.create(
                            request_date=p_date,
                            applicant="系統產生 (Mock)",
                            status="stocked",  # 狀態必須是 stocked 才會被計入 estimated_cost 成本
                        )
                        requisitions_created += 1

                        # 建立請購明細
                        PurchaseRequisitionItem.objects.create(
                            requisition=req,
                            material=mat,
                            material_provider=provider,
                            quantity=Decimal(str(qty)),
                            unit=mat.unit,
                            purchased_price=Decimal(str(round(price_fluctuation, 2))),
                            expected_delivery_date=p_date + timedelta(days=3),
                        )

            return Response(
                {
                    "message": "歷史採購 Mock Data 建立成功，可用於驗證 estimated_cost！",
                    "stats": {
                        "total_materials_processed": target_materials.count(),
                        "purchase_requisitions_created": requisitions_created,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
