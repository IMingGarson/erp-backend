import random
import string
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import BOM, BatchInventory, Material, UserProfile


@api_view(["POST"])
@permission_classes([AllowAny])
@transaction.atomic
def generate_mock_data(request):
    # BOM.objects.all().delete()
    # BatchInventory.objects.all().delete()
    # Material.objects.all().delete()
    # UserProfile.objects.all().delete()
    # User.objects.filter(username__in=["admin_user", "rd_user"]).delete()

    admin_user = User.objects.create_user(username="admin_user", password="password123")
    UserProfile.objects.create(user=admin_user, department="ADMIN")

    rd_user = User.objects.create_user(username="rd_user", password="password123")
    UserProfile.objects.create(user=rd_user, department="RD")

    def generate_material_code(m_type, length=6):
        """
        依照物料類型產生帶有前綴的隨機代碼
        範例輸出: RAW-X7B9A2, PRD-1029F3
        """
        # 定義各類別的代碼前綴
        prefix_map = {"PRODUCT": "PRD", "SEMI": "SEM", "RAW": "RAW", "PACK": "PCK"}
        prefix = prefix_map.get(m_type, "MAT")

        # 產生指定長度的隨機大寫英文字母與數字組合
        random_chars = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=length)
        )

        return f"{prefix}-{random_chars}"

    materials_data = {
        "PRODUCT": [
            ("台式炸雞粉", "kg"),
            ("濃縮雞湯底", "kg"),
            ("冷凍手工水餃", "kg"),
            ("滷肉汁罐頭", "kg"),
            ("珍珠奶茶粉", "kg"),
        ],
        "SEMI": [
            ("雞骨高湯", "kg"),
            ("水餃皮", "kg"),
            ("豬肉高麗菜餡", "kg"),
            ("基礎滷汁", "kg"),
            ("奶茶基底粉", "kg"),
        ],
        "RAW": [
            ("低筋麵粉", "kg"),
            ("地瓜粉", "kg"),
            ("蒜粉", "kg"),
            ("白胡椒粉", "kg"),
            ("鹽", "kg"),
            ("味精", "kg"),
            ("水", "kg"),
            ("雞骨架", "kg"),
            ("青蔥", "kg"),
            ("生薑", "kg"),
            ("雞油", "kg"),
            ("中筋麵粉", "kg"),
            ("豬絞肉", "kg"),
            ("高麗菜", "kg"),
            ("醬油", "kg"),
            ("香油", "kg"),
            ("冰糖", "kg"),
            ("綜合滷包", "kg"),
            ("帶皮五花肉丁", "kg"),
            ("油蔥酥", "kg"),
            ("奶精粉", "kg"),
            ("紅茶粉", "kg"),
            ("糖粉", "kg"),
            ("乾燥黑糖蜜", "kg"),
        ],
        "PACK": [
            ("炸雞粉包裝袋", "pcs"),
            ("湯底鋁箔包", "pcs"),
            ("水餃包裝盒", "pcs"),
            ("馬口鐵罐", "pcs"),
            ("奶茶粉夾鏈袋", "pcs"),
        ],
    }

    m_objs = {}
    for m_type, items in materials_data.items():
        for name, unit in items:
            m_objs[name] = Material.objects.create(
                name=name,
                type=m_type,
                unit=unit,
                code=generate_material_code(m_type),
                created_by=rd_user,
            )

    bom_data = [
        (m_objs["台式炸雞粉"], m_objs["低筋麵粉"], 0.4000),
        (m_objs["台式炸雞粉"], m_objs["地瓜粉"], 0.4500),
        (m_objs["台式炸雞粉"], m_objs["蒜粉"], 0.0500),
        (m_objs["台式炸雞粉"], m_objs["白胡椒粉"], 0.0500),
        (m_objs["台式炸雞粉"], m_objs["鹽"], 0.0300),
        (m_objs["台式炸雞粉"], m_objs["味精"], 0.0200),
        (m_objs["台式炸雞粉"], m_objs["炸雞粉包裝袋"], 1.0000),
        (m_objs["雞骨高湯"], m_objs["水"], 0.7000),
        (m_objs["雞骨高湯"], m_objs["雞骨架"], 0.2500),
        (m_objs["雞骨高湯"], m_objs["青蔥"], 0.0300),
        (m_objs["雞骨高湯"], m_objs["生薑"], 0.0200),
        (m_objs["濃縮雞湯底"], m_objs["雞骨高湯"], 0.9000),
        (m_objs["濃縮雞湯底"], m_objs["鹽"], 0.0500),
        (m_objs["濃縮雞湯底"], m_objs["雞油"], 0.0500),
        (m_objs["濃縮雞湯底"], m_objs["湯底鋁箔包"], 1.0000),
        (m_objs["水餃皮"], m_objs["中筋麵粉"], 0.6500),
        (m_objs["水餃皮"], m_objs["水"], 0.3300),
        (m_objs["水餃皮"], m_objs["鹽"], 0.0200),
        (m_objs["豬肉高麗菜餡"], m_objs["豬絞肉"], 0.5000),
        (m_objs["豬肉高麗菜餡"], m_objs["高麗菜"], 0.4000),
        (m_objs["豬肉高麗菜餡"], m_objs["醬油"], 0.0500),
        (m_objs["豬肉高麗菜餡"], m_objs["香油"], 0.0500),
        (m_objs["冷凍手工水餃"], m_objs["水餃皮"], 0.4000),
        (m_objs["冷凍手工水餃"], m_objs["豬肉高麗菜餡"], 0.6000),
        (m_objs["冷凍手工水餃"], m_objs["水餃包裝盒"], 1.0000),
        (m_objs["基礎滷汁"], m_objs["水"], 0.6000),
        (m_objs["基礎滷汁"], m_objs["醬油"], 0.3000),
        (m_objs["基礎滷汁"], m_objs["冰糖"], 0.0800),
        (m_objs["基礎滷汁"], m_objs["綜合滷包"], 0.0200),
        (m_objs["滷肉汁罐頭"], m_objs["基礎滷汁"], 0.4000),
        (m_objs["滷肉汁罐頭"], m_objs["帶皮五花肉丁"], 0.5500),
        (m_objs["滷肉汁罐頭"], m_objs["油蔥酥"], 0.0500),
        (m_objs["滷肉汁罐頭"], m_objs["馬口鐵罐"], 1.0000),
        (m_objs["奶茶基底粉"], m_objs["奶精粉"], 0.5000),
        (m_objs["奶茶基底粉"], m_objs["糖粉"], 0.3000),
        (m_objs["奶茶基底粉"], m_objs["紅茶粉"], 0.2000),
        (m_objs["珍珠奶茶粉"], m_objs["奶茶基底粉"], 0.8500),
        (m_objs["珍珠奶茶粉"], m_objs["乾燥黑糖蜜"], 0.1500),
        (m_objs["珍珠奶茶粉"], m_objs["奶茶粉夾鏈袋"], 1.0000),
    ]

    for parent, child, qty in bom_data:
        BOM.objects.create(
            parent=parent, child=child, quantity_required=qty, created_by=rd_user
        )

    today = date.today()
    batch_counter = 1

    raw_and_pack_materials = [
        m for name, m in m_objs.items() if m.type in ["RAW", "PACK"]
    ]

    for material in raw_and_pack_materials:
        qty = 100 if material.unit == "pcs" else 250.0000

        BatchInventory.objects.create(
            material=material,
            batch_number=f"B{today.strftime('%Y%m')}-{batch_counter:04d}",
            original_qty=qty,
            remaining_qty=qty,
            received_date=today - timedelta(days=10),
            created_by=rd_user,
        )
        batch_counter += 1

        BatchInventory.objects.create(
            material=material,
            batch_number=f"B{today.strftime('%Y%m')}-{batch_counter:04d}",
            original_qty=qty,
            remaining_qty=qty,
            received_date=today - timedelta(days=2),
            created_by=rd_user,
        )
        batch_counter += 1

    return Response(
        {"status": "success", "message": "Mock data generated successfully."}
    )
