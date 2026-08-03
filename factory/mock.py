from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BOM, BatchInventory, Material, ProductProfile


class InitMockDataAPIView(APIView):
    """
    一鍵建立所有預設的產品、原料、包材、BOM、產品專屬規格與初始庫存 (真實數據模擬版)
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
                "spec": "4.5KG/包",
                "sales_price": 1200.00,
                "label_info": {
                    "product_name": "川辣椒麻浸料",
                    "origin": "台灣",
                    "storage": "常溫保存，貯存於乾燥陰涼處，開封後請儘速使用。",
                    "allergens": {
                        "contains": ["大豆", "乳類"],
                        "cross_contamination": [
                            "甲殼類",
                            "芒果",
                            "花生",
                            "奶類",
                            "蛋",
                            "堅果類",
                            "芝麻",
                            "含麩質之穀物",
                            "魚類",
                            "二氧化硫",
                        ],
                    },
                    "nutrition_facts": {
                        "份量資訊": "每一份量 10 公克，本包裝含 450 份",
                        "每份": {
                            "熱量": "27.2 大卡",
                            "蛋白質": "1.5 公克",
                            "脂肪": "0.4 公克",
                            "飽和脂肪": "0.1 公克",
                            "反式脂肪": "0.0 公克",
                            "碳水化合物": "4.5 公克",
                            "糖": "3.1 公克",
                            "鈉": "1040.5 毫克",
                        },
                        "每100公克": {
                            "熱量": "272.3 大卡",
                            "蛋白質": "14.5 公克",
                            "脂肪": "3.9 公克",
                            "飽和脂肪": "0.6 公克",
                            "反式脂肪": "0.0 公克",
                            "碳水化合物": "44.8 公克",
                            "糖": "31.4 公克",
                            "鈉": "10404.9 毫克",
                        },
                    },
                },
                "items": [
                    ("P8501053-1", "川辣椒麻浸料-裸粉", "SEMI", "KG", 4.5, 1),
                    ("R8000001", "4.5KG用厚鋁箔袋", "PACK", "PCS", 1.0, 1),
                    ("R8000002", "川辣椒麻浸料-專屬貼標", "PACK", "PCS", 1.0, 1),
                ],
            },
            "P8501053-1": {
                "name": "川辣椒麻浸料-裸粉",
                "type": "SEMI",
                "unit": "KG",
                "items": [
                    ("R5010022", "糖", "RAW", "KG", 45.0, 1),
                    ("R5010002", "食鹽", "RAW", "KG", 25.0, 1),
                    ("R4010030", "L-麩酸鈉", "RAW", "KG", 15.0, 1),
                    ("R5020031", "辣椒粉", "RAW", "KG", 10.0, 1),
                    ("R50200062", "洋蔥粉(洋蔥粉、二氧化矽)", "RAW", "KG", 5.0, 1),
                ],
            },
            # ---------------------------------------------------------
            # 2. 香草烤雞翅浸料
            # ---------------------------------------------------------
            "P8500013": {
                "name": "香草烤雞翅浸料",
                "type": "PRODUCT",
                "unit": "袋",
                "spec": "散裝 20KG/袋",
                "sales_price": 500.00,
                "label_info": {
                    "product_name": "香草烤雞翅浸料",
                    "origin": "台灣",
                    "storage": "請密封存放於陰涼乾燥處，避免陽光直射。",
                    "allergens": {
                        "contains": ["大豆", "小麥"],
                        "cross_contamination": ["甲殼類", "花生", "芝麻", "魚類"],
                    },
                    "nutrition_facts": {
                        "份量資訊": "每一份量 20 公克，本包裝含 1000 份",
                        "每份": {
                            "熱量": "45.0 大卡",
                            "蛋白質": "1.2 公克",
                            "脂肪": "0.5 公克",
                            "飽和脂肪": "0.1 公克",
                            "反式脂肪": "0.0 公克",
                            "碳水化合物": "8.5 公克",
                            "糖": "5.0 公克",
                            "鈉": "1250.0 毫克",
                        },
                        "每100公克": {
                            "熱量": "225.0 大卡",
                            "蛋白質": "6.0 公克",
                            "脂肪": "2.5 公克",
                            "飽和脂肪": "0.5 公克",
                            "反式脂肪": "0.0 公克",
                            "碳水化合物": "42.5 公克",
                            "糖": "25.0 公克",
                            "鈉": "6250.0 毫克",
                        },
                    },
                },
                "items": [
                    ("R5010002", "精鹽-SALT(建鹽)", "RAW", "KG", 30.0, 100),
                    ("R5010022", "砂糖-(精製細砂)", "RAW", "KG", 25.0, 100),
                    ("R4010030", "味素-MSG*添", "RAW", "KG", 15.0, 100),
                    ("R2000015", "太白粉", "RAW", "KG", 10.0, 100),
                    ("R5010018", "HVP-東樺(水解大豆蛋白調味粉)", "RAW", "KG", 5.0, 100),
                    ("R7010008-1", "基香蒜粉", "RAW", "KG", 3.5, 100),
                    ("R50200062", "洋蔥粉-金禾味", "RAW", "KG", 3.0, 100),
                    ("R5020034", "甜椒粉(原匈牙利紅椒)", "RAW", "KG", 2.0, 100),
                    ("R50200453", "基香咖哩粉", "RAW", "KG", 2.0, 100),
                    ("R50100192", "無味素高鮮N4-無胺基乙酸", "RAW", "KG", 1.0, 100),
                    ("R4010031", "S.T.P.P-多鈉*添", "RAW", "KG", 0.8, 100),
                    ("R4010032", "T.S.P.P-焦鈉*添", "RAW", "KG", 0.8, 100),
                    ("R5020060", "披薩草粉(奧勒岡葉粉)", "RAW", "KG", 0.5, 100),
                    ("R5020036", "※百里香葉", "RAW", "KG", 0.3, 100),
                    ("R5020053", "迷迭香粉", "RAW", "KG", 0.3, 100),
                    ("R5020069", "※披薩葉", "RAW", "KG", 0.2, 100),
                    ("R5020048", "月桂葉粉", "RAW", "KG", 0.2, 100),
                    ("R5020066", "※羅勒葉", "RAW", "KG", 0.2, 100),
                    ("R5020068", "※巴西里(洋芫荽葉)", "RAW", "KG", 0.1, 100),
                    ("R5020136", "胡荽粉-沅哲", "RAW", "KG", 0.1, 100),
                    ("R5020025", "丁香粉", "RAW", "KG", 0.05, 100),
                    ("R50200311", "紅辣椒粉M0080A-小磨坊", "RAW", "KG", 0.1, 100),
                    ("R40410261", "油蔥香精K27-863-30M-廣福林", "RAW", "KG", 0.05, 100),
                ],
            },
            # ---------------------------------------------------------
            # 3. 鹽酥雞醃粉-宇潔 (含包裝)
            # ---------------------------------------------------------
            "P8500099": {
                "name": "鹽酥雞醃粉-宇潔",
                "type": "PRODUCT",
                "unit": "箱",
                "spec": "1KG*25包/箱",
                "sales_price": 2500.00,
                "label_info": {
                    "product_name": "鹽酥雞專用醃粉",
                    "origin": "台灣",
                    "storage": "常溫保存，請避免潮濕環境。",
                    "allergens": {
                        "contains": ["大豆", "小麥"],
                        "cross_contamination": [],
                    },
                    "nutrition_facts": {
                        "份量資訊": "每一份量 10 公克，本包裝含 100 份",
                        "每份": {
                            "熱量": "28.5 大卡",
                            "蛋白質": "0.8 公克",
                            "脂肪": "0.2 公克",
                            "飽和脂肪": "0.0 公克",
                            "反式脂肪": "0.0 公克",
                            "碳水化合物": "5.5 公克",
                            "糖": "3.5 公克",
                            "鈉": "850.0 毫克",
                        },
                        "每100公克": {
                            "熱量": "285.0 大卡",
                            "蛋白質": "8.0 公克",
                            "脂肪": "2.0 公克",
                            "飽和脂肪": "0.0 公克",
                            "反式脂肪": "0.0 公克",
                            "碳水化合物": "55.0 公克",
                            "糖": "35.0 公克",
                            "鈉": "8500.0 毫克",
                        },
                    },
                },
                "items": [
                    ("R5010022", "砂糖-Suger(細砂)", "RAW", "KG", 8.5, 1),
                    ("R5010002", "精鹽-SALT(建鹽)", "RAW", "KG", 6.5, 1),
                    ("R4010030", "味素-MSG*添", "RAW", "KG", 4.5, 1),
                    ("R2000015", "太白粉", "RAW", "KG", 3.0, 1),
                    ("R7010008-1", "基香蒜粉", "RAW", "KG", 1.0, 1),
                    ("R50200183", "黑胡椒粉", "RAW", "KG", 0.5, 1),
                    ("R50200391", "五香粉A2", "RAW", "KG", 0.3, 1),
                    ("R50200402", "基香七里香粉", "RAW", "KG", 0.2, 1),
                    ("R5020038", "八角粉(大茴粉)", "RAW", "KG", 0.1, 1),
                    ("R4010031", "S.T.P.P-多鈉*添", "RAW", "KG", 0.15, 1),
                    ("R4010032", "T.S.P.P-焦鈉*添", "RAW", "KG", 0.15, 1),
                    ("R40100271", "二氧化矽-裕元", "RAW", "KG", 0.08, 1),
                    ("R4010041", "蔗糖素B(稀釋)六和*添", "RAW", "KG", 0.02, 1),
                    ("R8000010", "1KG空白包裝袋", "PACK", "PCS", 25.0, 1),
                    ("R8000011", "5號外箱", "PACK", "PCS", 1.0, 1),
                ],
            },
            # ---------------------------------------------------------
            # 4. 特香麻辣鍋 (液體桶裝)
            # ---------------------------------------------------------
            "P9201015-4": {
                "name": "特香麻辣鍋(降辣10%)--築間",
                "type": "PRODUCT",
                "unit": "桶",
                "spec": "20KG/桶",
                "sales_price": 3800.00,
                "label_info": {
                    "product_name": "築間特製麻辣鍋底醬",
                    "origin": "台灣",
                    "storage": "冷藏保存，開封後請於 7 日內使用完畢。",
                    "allergens": {
                        "contains": ["大豆", "小麥", "芝麻", "蝦", "魚類"],
                        "cross_contamination": ["甲殼類", "蛋", "奶類"],
                    },
                    "nutrition_facts": {
                        "份量資訊": "每一份量 50 公克，本包裝含 400 份",
                        "每份": {
                            "熱量": "245.0 大卡",
                            "蛋白質": "2.5 公克",
                            "脂肪": "25.0 公克",
                            "飽和脂肪": "4.5 公克",
                            "反式脂肪": "0.2 公克",
                            "碳水化合物": "3.5 公克",
                            "糖": "1.0 公克",
                            "鈉": "1280.0 毫克",
                        },
                        "每100公克": {
                            "熱量": "490.0 大卡",
                            "蛋白質": "5.0 公克",
                            "脂肪": "50.0 公克",
                            "飽和脂肪": "9.0 公克",
                            "反式脂肪": "0.4 公克",
                            "碳水化合物": "7.0 公克",
                            "糖": "2.0 公克",
                            "鈉": "2560.0 毫克",
                        },
                    },
                },
                "items": [
                    ("R3000009", "大豆沙拉油A18L", "RAW", "KG", 12.0, 1),
                    (
                        "P9201015-5",
                        "特香麻辣鍋(降辣10%)調味粉-辣A調降.增白芝麻粉",
                        "SEMI",
                        "KG",
                        4.0,
                        1,
                    ),
                    ("R6000007", "萬家香醬油(甲等)", "RAW", "KG", 1.5, 1),
                    ("R6000021", "香菇素蠔油", "RAW", "KG", 1.0, 1),
                    ("R3000001", "香油B18K", "RAW", "KG", 0.8, 1),
                    ("R7050003", "*過*白芝麻粉-台益行", "RAW", "KG", 0.5, 1),
                    ("R5020111", "湯底滷料2mm-金禾味", "RAW", "KG", 0.15, 1),
                    ("R4010049", "脂肪酸甘油酯(乳化劑S)*添-盛源", "RAW", "KG", 0.03, 1),
                    ("R4030013", "焦糖色素-DS*添", "RAW", "KG", 0.01, 1),
                    ("R40100182", "混合濃縮生育醇*添-信意", "RAW", "KG", 0.01, 1),
                ],
            },
            "P9201015-5": {
                "name": "特香麻辣鍋(降辣10%)調味粉-辣A調降.增白芝麻粉",
                "type": "SEMI",
                "unit": "KG",
                "items": [
                    ("R5010022", "砂糖-(精製細砂)", "RAW", "KG", 10.0, 1),
                    (
                        "R5010018",
                        "*過*HVP-東樺(水解大豆蛋白調味粉)",
                        "RAW",
                        "KG",
                        6.0,
                        1,
                    ),
                    ("R5020031", "紅辣椒粉A級", "RAW", "KG", 5.0, 1),
                    ("R5010015", "*過*豬肉抽出物(A)-振芳", "RAW", "KG", 4.0, 1),
                    ("R7010006", "紅蔥酥(細片蔥酥)", "RAW", "KG", 3.0, 1),
                    ("R7010009", "蒜酥", "RAW", "KG", 3.0, 1),
                    ("R5010011", "*過*柴魚粉(須磁吸加工)", "RAW", "KG", 2.0, 1),
                    ("R5020023", "花椒粉-金禾味", "RAW", "KG", 2.0, 1),
                    ("R5020004", "白胡椒細粉", "RAW", "KG", 1.5, 1),
                    ("R50200453", "基香咖哩粉(全素)", "RAW", "KG", 1.0, 1),
                    ("R50100192", "無味素高鮮N4-降胺基乙酸", "RAW", "KG", 0.8, 1),
                    ("R5010013", "*過*香菇精粉FM05-佳津", "RAW", "KG", 0.5, 1),
                    ("R5020038", "八角粉(大茴粉)", "RAW", "KG", 0.5, 1),
                    ("R50200402", "基香七里香粉", "RAW", "KG", 0.3, 1),
                    ("R5020136", "胡荽粉-沅哲", "RAW", "KG", 0.2, 1),
                    ("R5020025", "丁香粉", "RAW", "KG", 0.1, 1),
                    ("R4020003", "I+G *添", "RAW", "KG", 0.1, 1),
                    ("R6000029", "油性辣椒精(100萬單位)", "RAW", "KG", 0.05, 1),
                    ("R40410024", "花椒油樹脂-0401", "RAW", "KG", 0.05, 1),
                    ("R40410023", "青花椒精油-0402", "RAW", "KG", 0.03, 1),
                    ("R6000035", "大蒜精油(大蒜抽出物)/原-蒜精", "RAW", "KG", 0.02, 1),
                    ("R4041056", "蝦香料A-T30954*添(富凰)", "RAW", "KG", 0.02, 1),
                    ("R4030007", "★油性辣椒紅色素-YW-2812", "RAW", "KG", 0.01, 1),
                ],
            },
            # ---------------------------------------------------------
            # 5. 川辣麻婆醬 (含子粉體)
            # ---------------------------------------------------------
            "P9205102": {
                "name": "川辣麻婆醬",
                "type": "PRODUCT",
                "unit": "桶",
                "spec": "散裝 15KG/桶",
                "sales_price": 3600.00,
                "label_info": {
                    "product_name": "川辣麻婆醬",
                    "origin": "台灣",
                    "storage": "常溫保存，開罐後請冷藏。",
                    "allergens": {
                        "contains": ["大豆", "小麥", "芝麻"],
                        "cross_contamination": [],
                    },
                    "nutrition_facts": {
                        "份量資訊": "每一份量 25 公克，本包裝含 600 份",
                        "每份": {
                            "熱量": "65.5 大卡",
                            "蛋白質": "1.8 公克",
                            "脂肪": "4.5 公克",
                            "飽和脂肪": "0.8 公克",
                            "反式脂肪": "0.0 公克",
                            "碳水化合物": "4.2 公克",
                            "糖": "1.5 公克",
                            "鈉": "520.0 毫克",
                        },
                        "每100公克": {
                            "熱量": "262.0 大卡",
                            "蛋白質": "7.2 公克",
                            "脂肪": "18.0 公克",
                            "飽和脂肪": "3.2 公克",
                            "反式脂肪": "0.0 公克",
                            "碳水化合物": "16.8 公克",
                            "糖": "6.0 公克",
                            "鈉": "2080.0 毫克",
                        },
                    },
                },
                "items": [
                    ("R3000009", "大豆沙拉油A18L", "RAW", "KG", 6.5, 1),
                    ("R6000005", "*過*辣豆瓣醬(江記)(原粒)", "RAW", "KG", 4.0, 1),
                    ("R6000007", "*過*萬家香醬油(甲等)", "RAW", "KG", 1.5, 1),
                    ("P9205102-1", "川辣麻婆醬調味粉", "SEMI", "KG", 1.5, 1),
                    ("R6000021", "*過*香菇素蠔油", "RAW", "KG", 0.8, 1),
                    ("R6000020", "蕃茄醬-可果美", "RAW", "KG", 0.4, 1),
                    ("R3000001", "*過*(麻)香油B18K", "RAW", "KG", 0.2, 1),
                    ("R7050003", "*過*白芝麻粉-台益行", "RAW", "KG", 0.1, 1),
                    ("R5020111", "湯底滷料2mm-金禾味", "RAW", "KG", 0.05, 1),
                    ("R40410024", "花椒油樹脂-0401", "RAW", "KG", 0.02, 1),
                    ("R6000029", "油性辣椒精(100萬單位)", "RAW", "KG", 0.01, 1),
                    ("R40410023", "青花椒精油-0402", "RAW", "KG", 0.01, 1),
                    ("R4030007", "★油性辣椒紅色素-YW-2812", "RAW", "KG", 0.005, 1),
                ],
            },
            "P9205102-1": {
                "name": "川辣麻婆醬調味粉",
                "type": "SEMI",
                "unit": "KG",
                "items": [
                    ("R5010002", "【建鹽】精鹽-SALT", "RAW", "KG", 4.0, 1),
                    ("R5010025", "黃糖 (二砂)", "RAW", "KG", 3.0, 1),
                    ("R5020031", "紅辣椒粉A級(另秤)", "RAW", "KG", 2.0, 1),
                    (
                        "R5010018",
                        "*過*HVP-東樺(水解大豆蛋白調味粉)",
                        "RAW",
                        "KG",
                        1.5,
                        1,
                    ),
                    ("R5020023", "花椒粉-金禾味", "RAW", "KG", 1.0, 1),
                    ("R7010008-1", "基香蒜粉-(廣農)", "RAW", "KG", 0.8, 1),
                    ("R7010006", "紅蔥酥(細片蔥酥)", "RAW", "KG", 0.5, 1),
                    ("R7010009", "蒜酥", "RAW", "KG", 0.5, 1),
                    ("R5020104", "老薑粉-久芳", "RAW", "KG", 0.4, 1),
                    ("R5020028", "韓式辣椒/原:韓國辣椒(另秤)", "RAW", "KG", 0.4, 1),
                    ("R5010014", "白肉精", "RAW", "KG", 0.3, 1),
                    ("R50100192", "無味素高鮮N4-降胺基乙酸", "RAW", "KG", 0.2, 1),
                    ("R5010011", "*過*柴魚粉(須磁吸加工)", "RAW", "KG", 0.2, 1),
                    ("R5020004", "白胡椒細粉", "RAW", "KG", 0.1, 1),
                    ("R5010013", "*過*香菇精粉FM05-佳津", "RAW", "KG", 0.1, 1),
                    ("R5020038", "八角粉(大茴粉)", "RAW", "KG", 0.05, 1),
                    ("R40410221", "糖香香料-Y-1403(特品)*添", "RAW", "KG", 0.02, 1),
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
                                "sales_unit": data.get("unit", "箱"),
                                "sales_price": data.get("sales_price", 0),
                                "label_info": data.get("label_info", {}),
                            },
                        )
                        profiles_created += 1

                    # 2. 建立子件與 BOM
                    for (
                        child_code,
                        child_name,
                        child_type,
                        child_unit,
                        exact_qty,
                        exact_base_qty,
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

                        # 直接使用定義好的真實配方用量
                        mock_qty = exact_qty if exact_qty is not None else 1.0
                        base_gty = exact_base_qty if exact_base_qty is not None else 1.0
                        BOM.objects.get_or_create(
                            parent=parent_mat,
                            child=child_mat,
                            defaults={
                                "base_quantity": Decimal(str(base_gty)),
                                "quantity_required": Decimal(str(mock_qty)),
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
                    initial_qty = "10000.0000" if mat.unit == "PCS" else "700.0000"

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
                    "message": "真實 Mock Data 已經成功寫入資料庫！",
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
