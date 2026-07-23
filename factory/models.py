from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum
from django.utils import timezone


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
    department = models.CharField(max_length=20, choices=DEPARTMENTS)
    is_active = models.BooleanField(default=True, db_index=True)
    onboarding_date = models.DateTimeField(default=get_default_onboarding_date)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"


class Material(models.Model):
    TYPE_CHOICES = (
        ("RAW", "原物料"),
        ("SEMI", "半成品"),
        ("PRODUCT", "最終產品"),
        ("PACK", "包材"),
    )
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=30, db_index=True, unique=True)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    unit = models.CharField(max_length=20)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_raw_material(self):
        return self.type == "RAW" or self.code.startswith("R")

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        db_table = "materials"


class BOM(models.Model):
    id = models.AutoField(primary_key=True)
    parent = models.ForeignKey(
        Material, related_name="main_product", on_delete=models.DO_NOTHING
    )
    child = models.ForeignKey(
        Material, related_name="sub_material", on_delete=models.DO_NOTHING
    )
    quantity_required = models.DecimalField(max_digits=15, decimal_places=4)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "boms"
        unique_together = ("parent", "child")


class MaterialRequirementPlan(models.Model):
    id = models.AutoField(primary_key=True)
    mrp_id = models.CharField(
        max_length=50, unique=True, default="TEMP-00000000", verbose_name="MRP單號"
    )
    parent_id = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="母單號"
    )
    vendor_info = models.JSONField()
    batch_inventory_info = models.JSONField()
    product = models.ForeignKey(Material, on_delete=models.DO_NOTHING)
    required_qty = models.DecimalField(max_digits=15, decimal_places=4)
    status = models.CharField(max_length=20, default="PENDING", db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
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
    material = models.ForeignKey(Material, on_delete=models.DO_NOTHING)
    order_qty = models.DecimalField(max_digits=15, decimal_places=4)
    expected_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default="DRAFT", db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "purchase_orders"
        verbose_name = "採購訂單"


class BatchInventory(models.Model):
    ADJUSTMENT_CHOICES = (("NONE", "無調整"), ("PROFIT", "盤盈"), ("LOSS", "盤虧"))
    id = models.AutoField(primary_key=True)
    material = models.ForeignKey(Material, on_delete=models.DO_NOTHING)
    batch_number = models.CharField(max_length=50, unique=True)
    original_qty = models.DecimalField(max_digits=15, decimal_places=4)
    remaining_qty = models.DecimalField(max_digits=15, decimal_places=4)
    received_date = models.DateField()
    expiration_date = models.DateField(default=get_default_expiration_date)
    adjustment_type = models.CharField(
        max_length=10,
        choices=ADJUSTMENT_CHOICES,
        default="NONE",
        verbose_name="調整狀態",
    )
    adjustment_qty = models.DecimalField(
        max_digits=15, decimal_places=4, default=0, verbose_name="盈虧數量"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.material.name} ({self.batch_number})"

    class Meta:
        db_table = "batch_inventories"
        verbose_name = "批號庫存"


class ProductionOrder(models.Model):
    STATUS_CHOICES = (("DRAFT", "草稿"), ("IN_PROGRESS", "生產中"), ("DONE", "已完成"))
    id = models.AutoField(primary_key=True)
    order_number = models.CharField(
        max_length=50, unique=True, null=True, verbose_name="生產單號"
    )
    parent_id = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="母生產單號", db_index=True
    )
    vendor_info = models.JSONField(verbose_name="客戶與物流資訊", default=None)
    product = models.ForeignKey(Material, on_delete=models.DO_NOTHING)
    target_qty = models.DecimalField(max_digits=15, decimal_places=4)
    actual_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True
    )
    materials_info = models.JSONField(verbose_name="原物料與用量資訊", default=list)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="DRAFT", db_index=True
    )
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "production_orders"
        verbose_name = "生產單"
        indexes = [
            models.Index(fields=["order_number", "parent_id"]),
        ]

    @property
    def is_fully_delivered(self):
        """檢查該生產單的累計出貨量是否已經達到 target_qty"""
        delivered_qty = (
            self.delivery_notes.aggregate(total=Sum("quantity"))["total"] or 0
        )

        return delivered_qty >= self.target_qty

    @property
    def remaining_qty(self):
        """計算還剩下多少數量未出貨"""
        delivered_qty = (
            self.delivery_notes.aggregate(total=Sum("quantity"))["total"] or 0
        )

        return max(self.target_qty - delivered_qty, 0)


class LogisticsOrder(models.Model):
    id = models.AutoField(primary_key=True)
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.DO_NOTHING)
    logistics_provider = models.CharField(max_length=100)
    vendor_name = models.CharField(max_length=100)
    details = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "logistics_orders"
        verbose_name = "物流單"
        verbose_name_plural = "物流單"


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
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING, default=None)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vendors"
        verbose_name = "客戶"

    def __str__(self):
        return self.name


class ProductionLog(models.Model):
    id = models.AutoField(primary_key=True)
    production_order = models.ForeignKey(
        ProductionOrder, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "production_logs"


class MaterialLog(models.Model):
    id = models.AutoField(primary_key=True)
    material = models.ForeignKey(
        Material, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "material_logs"


class VendorLog(models.Model):
    id = models.AutoField(primary_key=True)
    vendor = models.ForeignKey(Vendor, related_name="logs", on_delete=models.DO_NOTHING)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vendor_logs"


class BOMLog(models.Model):
    id = models.AutoField(primary_key=True)
    bom = models.ForeignKey(BOM, related_name="logs", on_delete=models.DO_NOTHING)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bom_logs"


class MaterialRequirementPlanLog(models.Model):
    id = models.AutoField(primary_key=True)
    mrp_plan = models.ForeignKey(
        MaterialRequirementPlan, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mrp_logs"


class BatchInventoryLog(models.Model):
    id = models.AutoField(primary_key=True)
    batch_inventory = models.ForeignKey(
        BatchInventory, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "batch_inventory_logs"


class RequisitionStatus(models.TextChoices):
    WAITING = "WAITING", "等待進貨"
    STOCKED = "STOCKED", "已經入庫"


class PurchaseRequisition(models.Model):
    request_date = models.DateField()
    applicant = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20,
        choices=RequisitionStatus.choices,
        default=RequisitionStatus.WAITING,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "purchase_requests"

    def __str__(self):
        return f"PR #{self.id} - {self.status}"


class PurchaseRequisitionItem(models.Model):
    requisition = models.ForeignKey(
        PurchaseRequisition, related_name="items", on_delete=models.DO_NOTHING
    )

    material = models.ForeignKey(
        Material, on_delete=models.DO_NOTHING, related_name="purchase_items"
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=10, default="Kg")
    purchased_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=False, blank=False
    )
    expected_delivery_date = models.DateField(null=True, blank=True)
    supplier = models.CharField(max_length=100, null=True, blank=True)
    remark = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

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
    action_detail = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


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
    unit_price = models.DecimalField(
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

    document_note = models.TextField(blank=True, null=True, verbose_name="單據備註")
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "delivery_notes"
        verbose_name = "銷貨單"


class DeliveryNoteLog(models.Model):
    id = models.AutoField(primary_key=True)
    delivery_notes = models.ForeignKey(
        DeliveryNote, related_name="logs", on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    action_detail = models.CharField(max_length=255)
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
    action_detail = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "customer_order_logs"
