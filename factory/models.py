import math
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

TYPE_CHOICES = (
    ("RAW", "原物料"),
    ("SEMI", "半成品"),
    ("PRODUCT", "成品"),
    ("PACK", "包材"),
    ("STICKER", "標籤貼紙"),
    ("OTHER", "其他"),
)


def get_default_expiration_date():
    return timezone.now().date() + timedelta(days=90)


def get_default_onboarding_date():
    return timezone.now().date()


class UserProfile(models.Model):
    DEPARTMENTS = (
        ("ADMIN", "行政"),
        ("MANUFACTURING", "製造"),
        ("RD", "研發"),
        ("PURCHASING", "採購"),
        ("EMPLOYER", "老闆"),
    )
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        User, on_delete=models.DO_NOTHING, related_name="profile"
    )
    department = models.CharField(
        max_length=20, choices=DEPARTMENTS, verbose_name="所屬部門"
    )
    is_active = models.BooleanField(
        default=True, db_index=True, verbose_name="帳號狀態"
    )
    onboarding_date = models.DateTimeField(
        default=get_default_onboarding_date, verbose_name="到職日"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"


class Vendor(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, verbose_name="客戶名稱")
    code = models.CharField(
        max_length=64,
        verbose_name="客戶代號",
        default="PLACEHOLDER",
        null=False,
        blank=False,
    )
    tax_id = models.CharField(
        max_length=8, blank=True, null=True, verbose_name="統一編號"
    )
    address = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="地址"
    )
    phone = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="聯絡電話"
    )
    contact_person = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="負責人名稱"
    )
    is_deleted = models.BooleanField(default=False, verbose_name="是否移除")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING, default=None)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vendors"
        verbose_name = "客戶"

    def __str__(self):
        return self.name


class MaterialProvider(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, verbose_name="供應商名稱")
    code = models.CharField(
        max_length=64,
        verbose_name="供應商代號",
        default="PLACEHOLDER",
        null=False,
        blank=False,
    )
    fax = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="傳真號碼"
    )
    tax_id = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="統一編號"
    )
    address = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="公司地址"
    )
    invoice_address = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="發票地址"
    )
    delivery_address = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="送貨地址"
    )
    phone = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="聯絡電話"
    )
    contact_person = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="負責人名稱"
    )
    contact_email = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="聯絡 Email"
    )
    bank_name = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="銀行名稱"
    )
    bank_account = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="銀行帳號"
    )
    note = models.TextField(blank=True, null=True, verbose_name="備註")
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING, default=None)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "material_providers"
        verbose_name = "原物料供應商"

    def __str__(self):
        return self.name


class Material(models.Model):
    PHASE_CHOICE = (("IN_DEV", "開發"), ("IN_PROD", "正式"))
    STORAGE_CHOICES = (
        ("ROOM_TEMP", "常溫"),
        ("REFRIGERATED", "冷藏"),
        ("FROZEN", "冷凍"),
    )
    DIETARY_CHOICES = (
        ("MEAT", "葷食"),
        ("VEGAN", "全素"),
        ("LACTO", "奶素"),
        ("OVO", "蛋素"),
        ("LACTO_OVO", "蛋奶素"),
        ("FIVE_PUNGENT", "植物五辛素"),
    )
    code = models.CharField(
        max_length=30, db_index=True, unique=True, verbose_name="物料代號"
    )
    name = models.CharField(
        max_length=100, default="未命名物料", verbose_name="物料名稱"
    )
    english_name = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="物料英文名稱"
    )
    type = models.CharField(
        max_length=10, choices=TYPE_CHOICES, verbose_name="物料類型"
    )
    unit = models.CharField(max_length=10, default="KG", verbose_name="單位")

    pack_capacity = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="包材容量/淨重(KG)",
        help_text="若物料為包材(PACK)，請輸入此包材單一個數可裝載之重量(KG)，如：500g包裝袋請填 0.5",
    )

    allergen_info = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="過敏原資訊"
    )
    storage_life = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="保存期限"
    )
    description = models.TextField(
        blank=True, null=True, verbose_name="描述 (成分來源)"
    )
    nutrition_fact = models.JSONField(
        blank=True, null=True, default=dict, verbose_name="八大營養價值標示"
    )
    product_registration_no = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="產品登錄號"
    )
    origin = models.CharField(max_length=50, blank=True, null=True, verbose_name="產地")

    is_active = models.BooleanField(
        default=True, db_index=True, verbose_name="是否啟用"
    )
    phase = models.CharField(
        max_length=10,
        choices=PHASE_CHOICE,
        default="IN_PROD",
        verbose_name="物料使用階段",
    )

    qc_standards = models.JSONField(
        blank=True,
        null=True,
        default=list,
        verbose_name="預設品管檢驗標準",
        help_text="以 JSON 陣列定義此成品的檢驗項目與合格區間",
    )

    storage_method = models.CharField(
        max_length=20,
        choices=STORAGE_CHOICES,
        default="ROOM_TEMP",
        verbose_name="保存方式",
        help_text="預設為常溫",
    )

    dietary_type = models.CharField(
        max_length=20,
        choices=DIETARY_CHOICES,
        blank=True,
        null=True,
        verbose_name="素食類別",
        help_text="如為複合原料，請依據成分中最嚴格的葷素級別標示",
    )
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def recalculate_from_ingredients(self):
        """
        重新計算營養素並聯集過敏原。
        - 營養素：如果有 BOM (SEMI/PRODUCT)，100% 由 BOM 展算。如果沒有 BOM (RAW)，則由關聯成分帶入。
        - 過敏原：永遠聯集 BOM 與手動宣告成分。
        """
        calc_nutrition = {
            "energy_kcal": 0.0,
            "protein": 0.0,
            "fat": 0.0,
            "saturated_fat": 0.0,
            "trans_fat": 0.0,
            "carbs": 0.0,
            "sugar": 0.0,
            "sodium": 0.0,
        }
        allergens = set()
        has_active_boms = False

        # ---------------------------------------------------------
        # 1. 處理「配方 (BOM)」下層的子物料 (適用於 SEMI, PRODUCT)
        # ---------------------------------------------------------
        if self.type in {"SEMI", "PRODUCT"}:
            active_boms = self.main_product.filter(is_active=True).select_related(
                "child"
            )
            if active_boms.exists():
                has_active_boms = True
                for bom in active_boms:
                    child_mat = bom.child
                    if not child_mat:
                        continue

                    # 確保最底層優先更新 (Bottom-Up)
                    if child_mat.type == "SEMI":
                        child_mat.recalculate_from_ingredients()

                    child_mat.refresh_from_db(
                        fields=["nutrition_fact", "allergen_info"]
                    )

                    base_qty = float(bom.base_quantity) if bom.base_quantity else 1.0
                    req_qty = (
                        float(bom.quantity_required) if bom.quantity_required else 0.0
                    )
                    ratio = req_qty / base_qty if base_qty > 0 else 0

                    child_nut = child_mat.nutrition_fact or {}
                    # 防呆：確保不被 JSON 字串化陷阱卡住
                    if isinstance(child_nut, str):
                        import json

                        try:
                            child_nut = json.loads(child_nut)
                        except:
                            child_nut = {}

                    for key in calc_nutrition:
                        val = float(child_nut.get(key) or 0)
                        calc_nutrition[key] += val * ratio

                    if child_mat.allergen_info:
                        parsed_allergens = [
                            a.strip()
                            for a in child_mat.allergen_info.split(",")
                            if a.strip()
                        ]
                        allergens.update(parsed_allergens)

        # ---------------------------------------------------------
        # 2. 處理「手動綁定」的成分 (適用於 RAW)
        # ---------------------------------------------------------
        m_ingredients = self.material_ingredients.filter(is_active=True).select_related(
            "ingredient"
        )
        for mi in m_ingredients:
            # 🌟 修正：只有在「沒有 BOM」的情況下，才允許由單一成分貢獻營養素！(防雙重計算)
            if not has_active_boms:
                ing_nut = mi.ingredient.nutrition_fact or {}
                if isinstance(ing_nut, str):
                    import json

                    try:
                        ing_nut = json.loads(ing_nut)
                    except:
                        ing_nut = {}

                for key in calc_nutrition:
                    val = float(ing_nut.get(key) or 0)
                    calc_nutrition[key] += val

            # 🌟 過敏原不論有沒有 BOM 都必須宣告聯集
            if mi.ingredient.allergen_info:
                parsed_allergens = [
                    a.strip()
                    for a in mi.ingredient.allergen_info.split(",")
                    if a.strip()
                ]
                allergens.update(parsed_allergens)

        # ---------------------------------------------------------
        # 3. 格式化後存回資料庫
        # ---------------------------------------------------------
        formatted_nutrition = {k: str(round(v, 2)) for k, v in calc_nutrition.items()}

        is_all_zero = all(float(v) == 0.0 for v in formatted_nutrition.values())
        if not is_all_zero or m_ingredients or has_active_boms:
            self.nutrition_fact = formatted_nutrition

        if allergens:
            self.allergen_info = ",".join(sorted(allergens))

        self.save(update_fields=["nutrition_fact", "allergen_info"])

    @property
    def is_raw_material(self):
        return self.type == "RAW" or self.code.startswith("R")

    @property
    def estimated_cost(self):
        """
        計算預估成本 (無條件進位至整數)：
        - 若為 PRODUCT：依據 ProductPackageOrderRelation 找出對應的 SEMI 原料成本與包材成本加總，無條件進位。
        - 若為 SEMI：依據 BOM 展開，計算 (Σ(子物料成本 * 需求量)) / 配方基數，並無條件進位。
        - 若為 RAW/PACK：優先取「三個月加權平均」 -> 「最新採購價」，並無條件進位。
        """
        if self.type == "PRODUCT":
            # 1. 透過中介表找出該成品的半成品與包裝單配置
            relation = self.package_relations.filter(is_active=True).first()
            if not relation:
                return 0

            # 2. 取得底層半成品成本
            semi_cost = (
                float(relation.semi_material.estimated_cost)
                if relation.semi_material
                else 0
            )

            # 3. 加上包裝單內的各項包材成本
            pack_cost = 0
            if relation.package_order:
                po = relation.package_order
                pkg_info = (
                    po.packaging_info if isinstance(po.packaging_info, list) else []
                )
                for p_item in pkg_info:
                    p_mat_id = p_item.get("material_id")
                    p_qty = float(p_item.get("qty") or 0)
                    if p_mat_id:
                        # 迴避 Circular import，直接在此 Query (未來可透過 annotate 優化)
                        p_mat = type(self).objects.filter(id=p_mat_id).first()
                        if p_mat:
                            pack_cost += float(p_mat.estimated_cost) * p_qty

            return math.ceil(semi_cost + pack_cost)

        if self.type == "SEMI":
            boms = [bom for bom in self.main_product.all() if bom.is_active]
            if not boms:
                return 0

            # 🌟 關鍵修正：成本為整數，乘上浮點數數量的需求量
            total_cost = sum(
                (bom.child.estimated_cost if bom.child else 0)
                * float(bom.quantity_required)
                for bom in boms
            )
            base_qty = float(boms[0].base_quantity)

            # 總成本除以基數後，無條件進位
            return math.ceil(total_cost / base_qty) if base_qty > 0 else 0

        # 若透過 ViewSet annotate 預先載入，一樣無條件進位
        annotated_cost = getattr(self, "annotated_estimated_cost", None)
        if annotated_cost is not None:
            return math.ceil(annotated_cost)

        today = timezone.now().date()
        three_months_ago = today - timedelta(days=90)
        recent_purchases = self.purchase_items.filter(
            is_active=True,
            requisition__is_active=True,
            requisition__status="stocked",
            requisition__request_date__gte=three_months_ago,
        )

        aggregates = recent_purchases.aggregate(
            total_quantity=Sum("quantity"),
            total_value=Sum(
                ExpressionWrapper(
                    F("quantity") * F("purchased_price"), output_field=DecimalField()
                )
            ),
        )

        total_qty = aggregates.get("total_quantity")
        total_val = aggregates.get("total_value")

        if total_qty and total_qty > 0 and total_val is not None:
            # 採購平均成本，無條件進位
            return math.ceil(float(total_val / total_qty))

        latest_purchase = (
            self.purchase_items.filter(
                is_active=True,
                requisition__status="stocked",
                requisition__is_active=True,
            )
            .order_by("-requisition__request_date", "-id")
            .first()
        )

        # 最新採購價，無條件進位
        return (
            math.ceil(float(latest_purchase.purchased_price)) if latest_purchase else 0
        )

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        db_table = "materials"


class MaterialProviderQuotation(models.Model):
    id = models.AutoField(primary_key=True)
    provider = models.ForeignKey(
        MaterialProvider,
        on_delete=models.CASCADE,
        related_name="quotations",
        verbose_name="供應商",
    )
    quote_date = models.DateField(null=True, blank=True, verbose_name="報價日期")
    valid_until = models.DateField(null=True, blank=True, verbose_name="報價效期")
    effective_date = models.DateField(verbose_name="系統生效日期")
    is_tax_included = models.BooleanField(default=True, verbose_name="是否含稅")
    remark = models.TextField(blank=True, null=True, verbose_name="整單備註")
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "material_provider_quotations"
        verbose_name = "供應商報價單"


class MaterialProviderPrice(models.Model):
    id = models.AutoField(primary_key=True)
    quotation = models.ForeignKey(
        MaterialProviderQuotation, on_delete=models.CASCADE, related_name="items"
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name="provider_prices",
        verbose_name="物料",
    )

    spec_text = models.CharField(
        max_length=150, blank=True, null=True, verbose_name="報價規格"
    )
    aux_unit = models.CharField(
        max_length=20, blank=True, null=True, verbose_name="輔助單位"
    )
    aux_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="單件基本重",
    )

    quoted_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="廠商原始報價",
    )
    quoted_unit = models.CharField(
        max_length=20, null=True, blank=True, verbose_name="報價單位"
    )
    price = models.DecimalField(
        max_digits=12, decimal_places=4, verbose_name="系統基本單價"
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "material_provider_prices"


class ProductProfile(models.Model):
    id = models.AutoField(primary_key=True)

    material = models.ForeignKey(
        Material,
        on_delete=models.DO_NOTHING,
        related_name="product_profiles",
        verbose_name="關聯成品",
    )

    sales_price = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="銷售單價"
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.DO_NOTHING,
        related_name="clients",
        verbose_name="購買客戶",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True, db_index=True, verbose_name="是否啟用"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_profiles"
        verbose_name = "成品專屬資訊"

    def __str__(self):
        return f"{self.material.name} - 客戶設定"


class BOM(models.Model):
    id = models.AutoField(primary_key=True)
    parent = models.ForeignKey(
        Material,
        related_name="main_product",
        on_delete=models.DO_NOTHING,
        verbose_name="成品",
    )
    child = models.ForeignKey(
        Material,
        related_name="sub_material",
        on_delete=models.DO_NOTHING,
        verbose_name="半成品",
    )
    base_quantity = models.DecimalField(
        max_digits=15, decimal_places=4, default=1, verbose_name="配方基數"
    )
    quantity_required = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name="需求數量"
    )
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(
        default=True, db_index=True, verbose_name="是否啟用"
    )
    remark = models.TextField(null=True, blank=True, verbose_name="物料備註")
    set_cost = models.IntegerField(null=True, blank=True, verbose_name="自訂單位成本")

    selected_price = models.ForeignKey(
        MaterialProviderPrice,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="參考廠商報價",
    )

    sequence_num = models.CharField(
        max_length=50, null=True, blank=True, verbose_name="投入序號"
    )

    class Meta:
        db_table = "boms"
        verbose_name = "配方清單"


class MaterialRequirementPlan(models.Model):
    STATUS_CHOICES = [
        ("pending", "待處理"),
        ("converted", "已轉換"),
    ]
    id = models.AutoField(primary_key=True)
    mrp_id = models.CharField(
        max_length=50, unique=True, default="TEMP-00000000", verbose_name="MRP單號"
    )
    parent_id = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="母單號"
    )
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)

    vendor_info = models.JSONField(verbose_name="客戶資訊")
    batch_inventory_info = models.JSONField(verbose_name="批號資訊")
    product = models.ForeignKey(
        Material, on_delete=models.DO_NOTHING, verbose_name="需求物料"
    )
    required_qty = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name="需求數量"
    )
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="狀態"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mrp_plans"
        verbose_name = "物料需求單"
        indexes = [
            models.Index(fields=["mrp_id", "parent_id"]),
        ]


class PurchaseOrder(models.Model):
    id = models.AutoField(primary_key=True)
    material = models.ForeignKey(
        Material, on_delete=models.DO_NOTHING, verbose_name="採購物料"
    )
    order_qty = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name="採購數量"
    )
    expected_date = models.DateField(null=True, blank=True, verbose_name="預計到貨日期")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")

    class Meta:
        db_table = "purchase_orders"
        verbose_name = "採購訂單"


class BatchInventory(models.Model):
    ADJUSTMENT_CHOICES = (("NONE", "無調整"), ("PROFIT", "盤盈"), ("LOSS", "盤虧"))
    id = models.AutoField(primary_key=True)
    material = models.ForeignKey(
        Material, on_delete=models.DO_NOTHING, verbose_name="物料"
    )
    batch_number = models.CharField(max_length=50, verbose_name="批號")
    original_qty = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name="初始數量"
    )
    remaining_qty = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name="剩餘數量"
    )
    received_date = models.DateField(verbose_name="入庫日期")
    expiration_date = models.DateField(
        default=get_default_expiration_date, verbose_name="有效期限"
    )
    adjustment_type = models.CharField(
        max_length=10,
        choices=ADJUSTMENT_CHOICES,
        default="NONE",
        verbose_name="調整狀態",
    )
    adjustment_qty = models.DecimalField(
        max_digits=15, decimal_places=4, default=0, verbose_name="盈虧數量"
    )
    is_active = models.BooleanField(
        default=True, db_index=True, verbose_name="是否啟用"
    )
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ==========================
    # 進貨當下的現場規格紀錄 (驗收點收依據)
    # ==========================
    in_stock_spec = models.CharField(
        max_length=150, blank=True, null=True, verbose_name="入庫規格"
    )
    package_qty = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="入庫件數"
    )
    aux_unit = models.CharField(
        max_length=20, blank=True, null=True, verbose_name="輔助單位"
    )
    aux_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="單件基本重",
    )
    note = models.TextField(blank=True, null=True, verbose_name="進貨備註")
    source_pr_item = models.OneToOneField(
        "PurchaseRequisitionItem",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="generated_batch",
    )

    def __str__(self):
        return f"{self.material.name} ({self.batch_number})"

    class Meta:
        db_table = "batch_inventories"
        constraints = [
            models.UniqueConstraint(
                fields=["material", "batch_number"], name="unique_material_batch"
            )
        ]
        verbose_name = "批號庫存"


class NutritionSnapshot(models.Model):
    STATUS_CHOICES = (
        ("PENDING", "待審核"),
        ("APPROVED", "已核准"),
        ("REJECTED", "已退回"),
        ("ARCHIVED", "已封存 (歷史版本)"),
    )

    id = models.AutoField(primary_key=True)
    material = models.ForeignKey(
        "Material",
        on_delete=models.CASCADE,
        related_name="nutrition_snapshots",
        verbose_name="關聯成品/半成品",
    )
    version_num = models.CharField(
        max_length=50, verbose_name="版本編號", help_text="例如: V20261030-01"
    )

    # 標籤快照核心內容 (因為包材上的成分文字與過敏原也會跟著配方變動，一併快照是最安全的)
    nutrition_fact = models.JSONField(default=dict, verbose_name="八大營養素快照")
    allergen_info = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="過敏原快照"
    )
    ingredients_text = models.TextField(
        blank=True, null=True, verbose_name="成分展開文字快照"
    )

    # 審核流控制
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING",
        verbose_name="審核狀態",
    )
    is_active = models.BooleanField(
        default=True, db_index=True, verbose_name="是否啟用"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING,
        related_name="created_snapshots",
        verbose_name="建立者",
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="reviewed_snapshots",
        verbose_name="審核者",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="審核時間")
    review_note = models.TextField(blank=True, null=True, verbose_name="審核備註")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nutrition_snapshots"
        verbose_name = "營養價值標籤快照"
        indexes = [
            models.Index(fields=["material", "status"]),
        ]

    def __str__(self):
        return f"{self.material.code} - {self.version_num}"


class NutritionSnapshotLog(models.Model):
    id = models.AutoField(primary_key=True)
    snapshot = models.ForeignKey(
        NutritionSnapshot, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nutrition_snapshot_logs"


class ProductionOrder(models.Model):
    id = models.AutoField(primary_key=True)
    order_number = models.CharField(
        max_length=50, unique=True, null=True, verbose_name="生產單號"
    )
    parent_id = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="母生產單號", db_index=True
    )
    vendor_info = models.JSONField(verbose_name="客戶與物流資訊", default=None)
    materials_info = models.JSONField(verbose_name="原物料與用量資訊", default=list)
    product = models.ForeignKey(
        Material, on_delete=models.DO_NOTHING, verbose_name="生產產品"
    )
    target_qty = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name="預計生產量"
    )
    actual_qty = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="實際生產量",
    )
    qc_metrics = models.JSONField(
        blank=True,
        null=True,
        default=list,
        verbose_name="品管檢驗與批號紀錄",
        help_text="存放當次生產的各項檢測數值與結果",
    )
    nutrition_snapshot = models.ForeignKey(
        NutritionSnapshot,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        verbose_name="營養標籤內容",
        help_text="用以決定此張生產單與最終出貨標籤要印哪一個版本的營養價值",
    )
    qc_passed = models.BooleanField(null=True, blank=True, verbose_name="品管是否合格")
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    manufacture_date = models.DateField(null=True, blank=True, verbose_name="製造日期")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "production_orders"
        verbose_name = "生產單"
        indexes = [
            models.Index(fields=["order_number", "parent_id"]),
        ]

    @property
    def active_delivered_qty(self):
        """計算當前有效的累計出貨量"""
        return (
            self.delivery_notes.filter(is_active=True).aggregate(total=Sum("quantity"))[
                "total"
            ]
            or 0
        )

    @property
    def is_fully_delivered(self):
        """檢查該生產單的累計出貨量是否已經達到 target_qty"""
        return self.active_delivered_qty >= self.target_qty

    @property
    def remaining_qty(self):
        """計算還剩下多少數量未出貨"""
        return max(self.target_qty - self.active_delivered_qty, 0)


class LogisticsOrder(models.Model):
    id = models.AutoField(primary_key=True)
    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.DO_NOTHING, verbose_name="關聯生產單"
    )
    logistics_provider = models.CharField(max_length=100, verbose_name="物流商")
    vendor_name = models.CharField(max_length=100, verbose_name="客戶名稱")
    details = models.TextField(verbose_name="物流詳情")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "logistics_orders"
        verbose_name = "物流單"


class ProductionLog(models.Model):
    id = models.AutoField(primary_key=True)
    production_order = models.ForeignKey(
        ProductionOrder, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "production_logs"


class MaterialLog(models.Model):
    id = models.AutoField(primary_key=True)
    material = models.ForeignKey(
        Material, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "material_logs"


class VendorLog(models.Model):
    id = models.AutoField(primary_key=True)
    vendor = models.ForeignKey(Vendor, related_name="logs", on_delete=models.DO_NOTHING)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vendor_logs"


class BOMLog(models.Model):
    id = models.AutoField(primary_key=True)
    bom = models.ForeignKey(BOM, related_name="logs", on_delete=models.DO_NOTHING)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bom_logs"


class MaterialRequirementPlanLog(models.Model):
    id = models.AutoField(primary_key=True)
    mrp_plan = models.ForeignKey(
        MaterialRequirementPlan, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mrp_logs"


class BatchInventoryLog(models.Model):
    id = models.AutoField(primary_key=True)
    batch_inventory = models.ForeignKey(
        BatchInventory, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "batch_inventory_logs"


class PurchaseRequisition(models.Model):
    STATUS_CHOICES = (
        ("waiting", "待進貨"),
        ("stocked", "已入庫"),
    )
    paid_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="已付金額",
    )
    request_date = models.DateField(verbose_name="申請日期")
    applicant = models.CharField(max_length=50, verbose_name="申請人")
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="waiting",
        verbose_name="單據狀態",
    )

    class Meta:
        db_table = "purchase_requests"
        verbose_name = "請購單"

    def __str__(self):
        return f"PR #{self.id} - {self.status}"

    @property
    def grand_total(self):
        """動態計算整張進貨單的應付總額"""
        total = self.items.filter(is_active=True).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("quantity") * F("purchased_price"),
                    output_field=DecimalField(max_digits=15, decimal_places=2),
                )
            )
        )["total"]
        return total or Decimal("0.00")

    @property
    def unpaid_amount(self):
        """尚未付款的餘額"""
        return max(
            self.grand_total - (self.paid_amount or Decimal("0.00")), Decimal("0.00")
        )

    @property
    def is_fully_paid(self):
        """是否已結清"""
        total = self.grand_total
        return total > 0 and (self.paid_amount or Decimal("0.00")) >= total


class PurchaseRequisitionItem(models.Model):
    requisition = models.ForeignKey(
        PurchaseRequisition,
        related_name="items",
        on_delete=models.DO_NOTHING,
        verbose_name="請購單",
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.DO_NOTHING,
        related_name="purchase_items",
        verbose_name="請購物料",
    )
    material_provider = models.ForeignKey(
        MaterialProvider,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        verbose_name="供應商",
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="數量")
    unit = models.CharField(max_length=10, default="Kg", verbose_name="單位")
    purchased_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=False,
        blank=False,
        verbose_name="採購單價",
    )
    expected_delivery_date = models.DateField(
        null=True, blank=True, verbose_name="預計到貨日期"
    )
    remark = models.TextField(null=True, blank=True, verbose_name="備註")
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")

    # ==========================
    # 請購包裝規格 (代表：採購預期)
    # ==========================
    in_stock_spec = models.CharField(
        max_length=150, blank=True, null=True, verbose_name="參考規格"
    )
    package_qty = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="採購件數"
    )
    aux_unit = models.CharField(
        max_length=20, blank=True, null=True, verbose_name="輔助單位"
    )
    aux_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="單件基本重",
    )

    @property
    def material_name(self):
        return self.material.name if self.material else ""

    def __str__(self):
        return f"{self.requisition.id} - {self.material_name}"


class PurchaseRequisitionLog(models.Model):
    purchase_requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.DO_NOTHING, related_name="logs"
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, null=True)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PurchaseInvoice(models.Model):
    id = models.AutoField(primary_key=True)
    invoice_number = models.CharField(
        max_length=50, db_index=True, verbose_name="發票號碼"
    )
    invoice_date = models.DateField(verbose_name="發票日期")
    buyer_title = models.CharField(
        max_length=100, default="基香食品", verbose_name="買受人抬頭"
    )
    buyer_tax_id = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="統編",
    )

    provider = models.ForeignKey(
        MaterialProvider,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name="開立廠商",
    )

    # 🌟 多對多關聯：1張進貨單可綁多張發票，1張發票也可綁整月多張進貨單
    requisitions = models.ManyToManyField(
        PurchaseRequisition,
        related_name="invoices",
        blank=True,
        verbose_name="關聯進貨單",
    )

    untaxed_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="未稅金額",
    )
    tax_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00"), verbose_name="稅額"
    )
    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="含稅總額",
    )

    note = models.TextField(blank=True, null=True, verbose_name="發票備註")
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "purchase_invoices"
        verbose_name = "進貨發票"
        indexes = [
            models.Index(fields=["invoice_number", "invoice_date"]),
        ]

    def __str__(self):
        return f"{self.invoice_number} ({self.buyer_title})"


class PurchaseInvoiceItem(models.Model):
    id = models.AutoField(primary_key=True)
    invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.DO_NOTHING,
        related_name="items",
        verbose_name="所屬發票",
    )
    item_name = models.CharField(max_length=150, verbose_name="品名/摘要")
    quantity = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("1.0000"), verbose_name="數量"
    )
    unit = models.CharField(max_length=20, blank=True, null=True, verbose_name="單位")
    unit_price = models.DecimalField(
        max_digits=15, decimal_places=4, default=Decimal("0.0000"), verbose_name="單價"
    )
    subtotal = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="小計金額",
    )
    remark = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="備註"
    )
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")

    class Meta:
        db_table = "purchase_invoice_items"
        verbose_name = "進貨發票明細"


class PurchaseInvoiceLog(models.Model):
    id = models.AutoField(primary_key=True)
    invoice = models.ForeignKey(
        PurchaseInvoice, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "purchase_invoice_logs"


class DeliveryNote(models.Model):
    id = models.AutoField(primary_key=True)

    note_number = models.CharField(max_length=50, unique=True, verbose_name="單據編號")
    note_date = models.DateField(verbose_name="單據日期")

    production_order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.DO_NOTHING,
        related_name="delivery_notes",
        verbose_name="關聯生產單",
    )

    quantity = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name="本次出貨數量"
    )
    unit = models.CharField(max_length=20, blank=True, null=True, verbose_name="單位")
    spec = models.CharField(max_length=100, blank=True, null=True, verbose_name="規格")
    sales_price = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="單價"
    )
    batch_number = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="批號編號"
    )

    customer_info = models.JSONField(verbose_name="客戶與收件資訊", default=dict)

    total_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="合計金額"
    )
    tax_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="營業稅"
    )
    grand_total = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="銷貨總額"
    )
    paid_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="已銷帳金額",
    )
    document_note = models.TextField(blank=True, null=True, verbose_name="單據備註")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")

    class Meta:
        db_table = "delivery_notes"
        verbose_name = "銷貨單"

    @property
    def unpaid_amount(self):
        """計算該銷貨單尚未沖銷的欠款餘額"""
        total = self.grand_total or Decimal("0.00")
        paid = self.paid_amount or Decimal("0.00")
        return max(total - paid, Decimal("0.00"))

    @property
    def is_fully_paid(self):
        """是否已完全沖銷"""
        total = self.grand_total or Decimal("0.00")
        paid = self.paid_amount or Decimal("0.00")
        return total > 0 and paid >= total

    @property
    def payment_status(self):
        """回傳沖銷狀態：UNPAID(未沖銷) / PARTIAL(部分沖銷) / PAID(已結清)"""
        paid = self.paid_amount or Decimal("0.00")
        total = self.grand_total or Decimal("0.00")
        if paid <= 0:
            return "UNPAID"
        if paid >= total:
            return "PAID"
        return "PARTIAL"


class DeliveryNoteLog(models.Model):
    id = models.AutoField(primary_key=True)
    delivery_notes = models.ForeignKey(
        DeliveryNote, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "delivery_note_logs"


class CustomerOrder(models.Model):
    id = models.AutoField(primary_key=True)
    order_number = models.CharField(max_length=50, verbose_name="單據編號")
    order_date = models.DateField(verbose_name="單據日期")
    delivery_date = models.DateField(null=True, blank=True, verbose_name="交貨日期")

    mrp = models.ForeignKey(
        MaterialRequirementPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_orders",
        verbose_name="物料需求單(MRP)",
    )

    customer_info = models.JSONField(verbose_name="客戶資訊", default=dict)

    product = models.ForeignKey(
        Material, on_delete=models.DO_NOTHING, verbose_name="訂購產品"
    )
    spec = models.CharField(max_length=100, blank=True, null=True, verbose_name="規格")
    quantity = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name="訂單總數量"
    )
    unit = models.CharField(max_length=10, default="KG", verbose_name="單位")
    unit_price = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, verbose_name="單價"
    )

    total_amount = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, verbose_name="合計金額"
    )
    tax_amount = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, verbose_name="營業稅"
    )
    grand_total = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, verbose_name="總計金額"
    )
    document_note = models.TextField(blank=True, null=True, verbose_name="單據備註")
    logistics_info = models.JSONField(verbose_name="物流設定", default=dict)

    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="刪除時間")

    class Meta:
        db_table = "customer_orders"
        verbose_name = "客戶訂貨單"
        indexes = [
            models.Index(fields=["order_number"]),
            models.Index(fields=["order_date"]),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.product.name}"


class CustomerOrderLog(models.Model):
    id = models.AutoField(primary_key=True)
    customer_order = models.ForeignKey(
        CustomerOrder, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "customer_order_logs"


class CustomerQuotation(models.Model):
    quotation_number = models.CharField(
        max_length=50, unique=True, verbose_name="單據編號"
    )
    issue_date = models.DateField(auto_now_add=True, verbose_name="單據日期")

    customer = models.ForeignKey(
        "Vendor",
        on_delete=models.CASCADE,
        related_name="quotations",
        verbose_name="客戶",
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("DRAFT", "草稿"),
            ("CONFIRMED", "已確認/成立"),
        ],
        default="DRAFT",
        verbose_name="狀態",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING,
        null=True,
        verbose_name="經辦人",
    )
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer_quotations"

    def __str__(self):
        return f"{self.quotation_number} - {self.customer.name}"


class CustomerQuotationItem(models.Model):
    quotation = models.ForeignKey(
        CustomerQuotation, on_delete=models.DO_NOTHING, related_name="items"
    )
    product = models.ForeignKey(
        Material, on_delete=models.DO_NOTHING, verbose_name="報價產品"
    )

    sales_unit = models.CharField(max_length=10, default="箱", verbose_name="銷售單位")
    sales_unit_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=1, verbose_name="銷售單位數量"
    )
    sales_pack_unit = models.CharField(
        max_length=10, null=True, blank=True, verbose_name="包裝單位"
    )
    sales_pack_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="每銷售單位含包裝數"
    )

    outer_pack = models.ForeignKey(
        "Material",
        on_delete=models.SET_NULL,
        related_name="quotation_outer_packs",
        null=True,
        blank=True,
        verbose_name="外層實體包材",
    )
    inner_pack = models.ForeignKey(
        "Material",
        on_delete=models.SET_NULL,
        related_name="quotation_inner_packs",
        null=True,
        blank=True,
        verbose_name="內層實體包材",
    )

    # 採用 JSONField 儲存動態成本結構
    # 格式範例：
    # {
    #   "material_cost": {"name": "純料成本", "value": 120.50},
    #   "packaging_cost": {"name": "包材成本", "value": 15.00},
    #   "manual_cost": {"name": "其他製造費", "value": 5.00}
    # }
    costs_breakdown = models.JSONField(
        default=dict,
        verbose_name="成本明細結構",
    )

    spec = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="包裝規格",
        help_text="如：0.10KG*110包/箱",
    )

    pricing_multiplier = models.DecimalField(
        max_digits=6, decimal_places=3, default=1.000, verbose_name="客戶報價常數"
    )

    final_price_per_kg = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="最終報價單價/KG"
    )

    is_active = models.BooleanField(default=True, verbose_name="是否啟用")

    class Meta:
        db_table = "customer_quotation_items"

    def __str__(self):
        return f"{self.quotation.quotation_number} - {self.product.name}"

    @property
    def total_cost_per_kg(self):
        """加總所有成本項目的 value"""
        total = Decimal(0)
        if isinstance(self.costs_breakdown, dict):
            for cost_item in self.costs_breakdown.values():
                if isinstance(cost_item, dict) and "value" in cost_item:
                    try:
                        total += Decimal(str(cost_item["value"]))
                    except (ValueError, TypeError):
                        pass
        return total

    @property
    def calculated_price(self):
        """依據常數算出的理論報價 (四捨五入)"""
        exact = self.total_cost_per_kg * (self.pricing_multiplier or Decimal("1.000"))
        return int(Decimal(str(exact)).quantize(Decimal(1), rounding="ROUND_HALF_UP"))


class CustomerQuotationLog(models.Model):
    quotation = models.ForeignKey(
        CustomerQuotation,
        on_delete=models.CASCADE,
        related_name="logs",
        verbose_name="報價單",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="操作人員",
    )
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "customer_quotation_logs"

    def __str__(self):
        return f"{self.quotation.quotation_number} - {self.action_detail} at {self.created_at}"


class BatchQCRecord(models.Model):
    id = models.AutoField(primary_key=True)

    # 關聯：針對哪一個實體批號進行檢驗
    batch = models.ForeignKey(
        BatchInventory,
        on_delete=models.DO_NOTHING,
        related_name="qc_records",
        verbose_name="檢驗批號",
    )

    material = models.ForeignKey(
        Material,
        on_delete=models.DO_NOTHING,
        related_name="qc_records",
        verbose_name="物料",
    )

    # ==========================
    # 檢驗基礎資訊
    # ==========================
    sample_date = models.DateField(verbose_name="取樣日期")
    test_date = models.DateField(verbose_name="檢測日期")

    # 物理化學指標 (實際檢測出的數值)
    actual_moisture = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="實際水分(%)",
    )
    actual_brix = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="實際糖度(Brix)",
    )
    actual_salt = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="實際鹽度(%)",
    )

    # 若有額外的微生物或特殊檢驗，可利用 JSONField 動態記錄
    actual_microbiology = models.JSONField(
        blank=True, null=True, default=dict, verbose_name="實際微生物檢驗結果"
    )

    # ==========================
    # 綜合判定與備註
    # ==========================
    is_passed = models.BooleanField(default=True, verbose_name="最終判定(合格/不合格)")
    remark = models.TextField(
        blank=True,
        null=True,
        verbose_name="備註",
        help_text="如: 綜合此檢測落點，修正鹽度規格",
    )

    # ==========================
    # 系統欄位
    # ==========================
    inspector = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING,
        related_name="inspected_qcs",
        verbose_name="檢驗人員",
    )
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "batch_qc_records"
        verbose_name = "批號品管檢驗紀錄"
        ordering = ["-test_date", "-id"]

    def __str__(self):
        return (
            f"QC - {self.batch.batch_number} ({'合格' if self.is_passed else '不合格'})"
        )


class Ingredient(models.Model):
    """
    成分表：對應法規標示上的成分文字與其營養價值/過敏原
    """

    SOURCE_CHOICES = (
        ("TFDA", "食藥署資料庫"),
        ("MANUAL", "手動建檔"),
    )

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=150, verbose_name="成分名稱")
    source_type = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, default="MANUAL", verbose_name="資料來源"
    )
    tfda_code = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="TFDA代碼"
    )
    is_additive = models.BooleanField(default=False, verbose_name="是否為法規添加物")
    legal_limit_percent = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="法規上限(%)",
    )
    additive_license_no = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="許可證號"
    )
    license_valid_date = models.DateField(
        blank=True, null=True, verbose_name="許可證效期"
    )
    nutrition_fact = models.JSONField(
        blank=True, null=True, default=dict, verbose_name="八大營養素"
    )
    allergen_info = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="法定過敏原"
    )
    source_material = models.ForeignKey(
        "Material",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_ingredients",
        verbose_name="來源物料",
    )
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_by = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, verbose_name="建檔人"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_source_type_display()})"

    class Meta:
        db_table = "ingredients"
        verbose_name = "成分"


class MaterialIngredient(models.Model):
    """
    原物料與成分關聯表 (純粹紀錄該原物料用到了哪些成分)
    """

    id = models.AutoField(primary_key=True)
    material = models.ForeignKey(
        Material,
        on_delete=models.DO_NOTHING,
        related_name="material_ingredients",
        verbose_name="原物料",
    )
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.DO_NOTHING, verbose_name="成分"
    )
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")

    class Meta:
        db_table = "material_ingredients"
        verbose_name = "原物料成分明細"


# ==========================================
# 會計模組：雜支與零用金紀錄
# ==========================================
class MiscTransactionRecord(models.Model):
    TRANSACTION_TYPES = (
        ("EXPENSE", "應付費用 (支出)"),
        ("INCOME", "應收費用 / 入零用金 (收入)"),
    )

    id = models.AutoField(primary_key=True)
    transaction_date = models.DateField(verbose_name="交易日期", db_index=True)
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES,
        default="EXPENSE",
        verbose_name="大項 (收支類型)",
    )
    # 🌟 補上：次項分類 (不綁死 choices，交由前端傳入如 FIX/修繕、FACILITY/水電、LABOR/人事、COMMISSION/佣金 等)
    sub_category = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default="OTHER",
        verbose_name="次項分類",
    )
    category = models.CharField(
        max_length=100,
        verbose_name="名稱/類別摘要",
        help_text="如：生鮮、電話費、維修費、提領零用金",
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="金額")
    note = models.TextField(blank=True, null=True, verbose_name="備註")

    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "misc_transaction_records"
        verbose_name = "雜支與零用金紀錄"


class MiscTransactionRecordLog(models.Model):
    id = models.AutoField(primary_key=True)
    transaction_record = models.ForeignKey(
        MiscTransactionRecord, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "misc_transaction_record_logs"


# ==========================================
# 會計模組：金流與票據收付款紀錄
# ==========================================
class PaymentRecord(models.Model):
    PARTNER_TYPES = (
        ("CUSTOMER", "客戶 (收款)"),
        ("VENDOR", "廠商 (付款)"),
    )
    PAYMENT_METHODS = (
        ("CASH", "現金"),
        ("TRANSFER", "匯款"),
        ("CHECK", "支票/票據"),
        ("MIXED", "複合付款"),
    )

    id = models.AutoField(primary_key=True)
    payment_date = models.DateField(verbose_name="收付款日期", db_index=True)
    partner_type = models.CharField(
        max_length=20, choices=PARTNER_TYPES, verbose_name="對象類型"
    )

    # 對象 (擇一填寫)
    customer = models.ForeignKey(
        "Vendor",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        verbose_name="客戶",
        help_text="若為客戶收款請填此欄",
        related_name="payments",
    )
    provider = models.ForeignKey(
        "MaterialProvider",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        verbose_name="廠商",
        help_text="若為廠商付款請填此欄",
        related_name="payments",
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default="TRANSFER",
        verbose_name="付款方式",
    )

    # 🌟 補上：完整金額結構 (實收付金額 + 匯費/手續費 + 其他折讓差額 = 本次總沖銷額度)
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="實際收付總金額",
    )
    total_fee = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="匯費/手續費總計",
    )
    other_deduction = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="其他扣除/折讓金額",
        help_text="如：扣除標籤貼紙錢後的差額",
    )
    other_deduction_note = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="其他扣除說明",
    )
    total_write_off_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="本次可沖銷總額度",
    )

    # 支票專用 JSON 欄位 (保留相容性)
    check_info = models.JSONField(
        blank=True, null=True, default=dict, verbose_name="支票與票據資訊"
    )

    reference_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="沖銷與備註",
        help_text="會計可輸入沖銷的銷貨單號或發票號碼",
    )

    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_records"
        verbose_name = "金流收付款紀錄"


class PaymentRecordLog(models.Model):
    id = models.AutoField(primary_key=True)
    payment_record = models.ForeignKey(
        PaymentRecord, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_record_logs"


class PackageOrder(models.Model):
    id = models.AutoField(primary_key=True)
    order_number = models.CharField(max_length=50, unique=True, verbose_name="包裝單號")

    spec = models.TextField(
        blank=True,
        null=True,
        verbose_name="產品規格",
        help_text="如: 1KG*25包/箱",
    )
    sales_unit = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="銷售單位"
    )
    sales_unit_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        verbose_name="銷售單位數量",
        help_text="如: 1KG*25包/箱，則填1(箱)",
    )
    sales_pack_unit = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="銷售輔助單位"
    )
    sales_pack_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        verbose_name="銷售輔助單位數量",
        help_text="如: 1KG*25包/箱，則填25(包)",
    )

    tag_id = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="標籤關聯代號"
    )

    packaging_info = models.JSONField(default=list, verbose_name="包材設定資訊")

    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "package_orders"
        verbose_name = "包裝單"
        indexes = [
            models.Index(fields=["order_number"]),
        ]

    def __str__(self):
        return f"{self.order_number} ({self.product.name})"


class PackageOrderLog(models.Model):
    id = models.AutoField(primary_key=True)
    package_order = models.ForeignKey(
        PackageOrder, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "package_order_logs"


class ProductPackageOrderRelation(models.Model):
    id = models.AutoField(primary_key=True)

    package_order = models.ForeignKey(
        PackageOrder,
        on_delete=models.DO_NOTHING,
        related_name="product_relations",
        verbose_name="包裝單",
    )

    product = models.ForeignKey(
        "Material",
        on_delete=models.DO_NOTHING,
        related_name="package_relations",
        verbose_name="關聯成品",
    )

    semi_material = models.ForeignKey(
        "Material",
        on_delete=models.DO_NOTHING,
        related_name="semi_package_relations",
        verbose_name="關聯半成品",
    )

    is_active = models.BooleanField(default=True, verbose_name="是否啟用")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_package_relations"
        verbose_name = "成品與包裝單關聯"
        indexes = [
            models.Index(fields=["product", "is_active"]),
        ]

    def __str__(self):
        return f"{self.product.name} = {self.semi_material.name} + {self.package_order.order_number}"


class ProductPackageOrderRelationLog(models.Model):
    id = models.AutoField(primary_key=True)
    relation = models.ForeignKey(
        ProductPackageOrderRelation, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_package_relation_logs"


class PaymentMethodDetail(models.Model):
    """
    三大付款區塊明細 (現金、銀行轉帳、支票)
    紀錄各區塊填寫的「已付金額」、「匯費/手續費」以及「進入的基香銀行帳戶」
    """

    METHOD_CHOICES = (
        ("CASH", "現金"),
        ("TRANSFER", "銀行轉帳"),
        ("CHECK", "支票"),
    )

    id = models.AutoField(primary_key=True)
    payment_record = models.ForeignKey(
        PaymentRecord,
        on_delete=models.CASCADE,
        related_name="method_details",
        verbose_name="所屬金流主單",
    )
    payment_method = models.CharField(
        max_length=20, choices=METHOD_CHOICES, verbose_name="付款方式區塊"
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="實收/實付金額",
    )
    fee = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="匯費/手續費",
        help_text="轉帳匯費或支票扣除之手續費，可一併計入沖銷額度",
    )
    company_bank_account = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="入帳/扣款之基香帳戶",
    )
    note = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="區塊備註"
    )

    class Meta:
        db_table = "payment_method_details"
        verbose_name = "付款方式區塊明細"


class PaymentCheck(models.Model):
    """
    支票詳細資訊表 (支援單次銷帳包含多張支票，例如 700、800 兩張，並追蹤各自兌現狀態)
    """

    id = models.AutoField(primary_key=True)
    payment_record = models.ForeignKey(
        PaymentRecord,
        on_delete=models.CASCADE,
        related_name="checks",
        verbose_name="所屬金流主單",
    )
    check_number = models.CharField(max_length=50, db_index=True, verbose_name="票號")
    received_date = models.DateField(verbose_name="收票日")
    due_date = models.DateField(
        verbose_name="到期日 (預計可兌現日)", help_text="對應 YYYY-MM-DD"
    )
    cleared_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="實際兌現日",
        help_text="收到時未兌現，事後回填",
    )
    is_cleared = models.BooleanField(
        default=False, db_index=True, verbose_name="是否已兌現"
    )
    note = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="支票備註"
    )
    amount = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name="支票面額"
    )
    fee = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="手續費",
        help_text="若開票時已扣除手續費可記錄於此",
    )
    issuer_bank = models.CharField(max_length=100, verbose_name="開票人的銀行")
    deposit_bank_account = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="存入的銀行帳號 (基香雙帳戶)",
    )
    title = models.CharField(
        max_length=100,
        default="基香食品",
        blank=True,
        null=True,
        verbose_name="支票抬頭",
    )
    is_active = models.BooleanField(default=True, verbose_name="是否啟用")

    class Meta:
        db_table = "payment_checks"
        verbose_name = "支票明細紀錄"


class PaymentWriteOff(models.Model):
    """
    銷帳沖銷橋接表：
    紀錄「某種付款方式 (CASH / TRANSFER / CHECK / OTHER)」沖銷了「哪張銷貨單 (或進貨單)」多少金額。
    例如：1000元現金區塊 -> 勾選沖銷了 DeliveryNote A (300元) 與 DeliveryNote B (700元)
    """

    ALLOCATION_METHOD_CHOICES = (
        ("CASH", "現金區塊"),
        ("TRANSFER", "銀行轉帳區塊"),
        ("CHECK", "支票區塊"),
        ("OTHER", "其他折讓/差額扣除"),
    )

    id = models.AutoField(primary_key=True)
    payment_record = models.ForeignKey(
        PaymentRecord,
        on_delete=models.CASCADE,
        related_name="write_offs",
        verbose_name="所屬金流主單",
    )
    payment_method = models.CharField(
        max_length=20,
        choices=ALLOCATION_METHOD_CHOICES,
        verbose_name="對應沖銷區塊",
    )

    # 客戶應收沖銷：綁定銷貨單
    delivery_note = models.ForeignKey(
        DeliveryNote,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="write_offs",
        verbose_name="沖銷之銷貨單",
    )
    # 廠商應付沖銷：綁定進貨單
    purchase_requisition = models.ForeignKey(
        PurchaseRequisition,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="write_offs",
        verbose_name="沖銷之進貨單",
    )

    allocated_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="本次沖銷金額",
        help_text="此區塊分配給該單據的沖銷金額 (支援部分沖銷)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_write_offs"
        verbose_name = "單據沖銷明細"
