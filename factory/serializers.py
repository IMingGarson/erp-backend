# 請購單和進貨單可同一張，更新狀態
# 樣品狀態的貨編可能需要一個區別方式（prefix: TEST，提供研發人員辨識)
# 成本估算單 per 耗損 const；原料成本資料來自前次進貨單回填的成本價
# cond. 估算單要考慮包材、運費、加工費；但包材受平均值（20KG裝30KG箱）、運費分常溫、冷藏、批次、回頭車
# 成品報價、單價需per 客戶，預設前次價格、其次交易日期、該成品成本價（ Maybe checkbox for one-time 更新 per 客戶）
# 添加物總量警示，成品、半成品，總用量不能超過某%
# 新增物料：添加物、展開成分、過敏原、基準單位、輔助單位（袋、箱）
# 營養標籤字體、排序都有規定
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    BOM,
    BatchInventory,
    CustomerOrder,
    CustomerQuotation,
    CustomerQuotationItem,
    DeliveryNote,
    Material,
    MaterialProvider,
    MaterialRequirementPlan,
    ProductionLog,
    ProductionOrder,
    ProductProfile,
    PurchaseRequisition,
    PurchaseRequisitionItem,
    UserProfile,
    Vendor,
)


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = UserProfile
        fields = ["id", "username", "department", "is_active"]
        read_only_fields = ["id"]

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "username": instance.user.username,
            "first_name": instance.user.first_name,
            "last_name": instance.user.last_name,
            "department": instance.department,
            "onboarding_date": instance.onboarding_date.strftime("%Y-%m-%d"),
            "is_active": instance.is_active,
        }


class UserCreateSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    onboarding_date = serializers.DateField(write_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "username",
            "password",
            "department",
            "first_name",
            "last_name",
            "onboarding_date",
        ]

    @transaction.atomic
    def create(self, validated_data):
        username = validated_data.pop("username")
        password = validated_data.pop("password")
        department = validated_data.pop("department")
        first_name = validated_data.pop("first_name")
        last_name = validated_data.pop("last_name")
        onboarding_date = validated_data.pop("onboarding_date")

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        profile = UserProfile.objects.create(
            user=user, department=department, onboarding_date=onboarding_date
        )
        return profile

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "username": instance.user.username,
            "first_name": instance.user.first_name,
            "last_name": instance.user.last_name,
            "department": instance.department,
            "onboarding_date": instance.onboarding_date,
            "is_active": instance.is_active,
        }


class UserUpdateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    password = serializers.CharField(required=False, write_only=True)
    username = serializers.CharField(read_only=True, source="user.username")

    class Meta:
        model = UserProfile
        fields = [
            "username",
            "first_name",
            "last_name",
            "password",
            "department",
            "onboarding_date",
            "is_active",
        ]

    @transaction.atomic
    def update(self, instance, validated_data):
        user = instance.user

        password = validated_data.pop("password", None)
        if password:
            user.set_password(password)

        user_fields = [
            "first_name",
            "last_name",
            "department",
            "onboarding_date",
        ]
        for field in user_fields:
            if field in validated_data:
                setattr(user, field, validated_data.pop(field))
        user.save()

        return super().update(instance, validated_data)

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "username": instance.user.username,
            "first_name": instance.user.first_name,
            "last_name": instance.user.last_name,
            "department": instance.department,
            "onboarding_date": instance.onboarding_date.strftime("%Y-%m-%d"),
            "is_active": instance.is_active,
        }


class ProductProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductProfile
        fields = [
            "spec",
            "sales_unit",
            "sales_pack_unit",
            "sales_unit_quantity",
            "sales_pack_quantity",
            "sales_price",
            "label_info",
        ]


class MaterialProviderSerializer(serializers.ModelSerializer):
    creator_name = serializers.SerializerMethodField()

    class Meta:
        model = MaterialProvider
        fields = [
            "id",
            "name",  # 供應商名稱
            "code",  # 供應商代號
            "fax",  # 傳真號碼
            "tax_id",  # 統一編號
            "address",  # 公司地址
            "invoice_address",  # 發票地址
            "delivery_address",  # 送貨地址
            "phone",  # 聯絡電話
            "contact_person",  # 負責人名稱
            "contact_email",  # 聯絡 Email
            "bank_name",  # 銀行名稱
            "bank_account",  # 銀行帳號
            "note",  # 備註
            "is_active",  # 是否啟用
            "created_by",  # 建立者 (User ID)
            "creator_name",  # 建立者姓名
            "created_at",  # 建立時間
            "updated_at",  # 更新時間
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_creator_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.last_name}{obj.created_by.first_name}"
        return "系統產生"


class MaterialSerializer(serializers.ModelSerializer):
    is_raw_material = serializers.ReadOnlyField()
    estimated_cost = serializers.ReadOnlyField()
    creator_name = serializers.SerializerMethodField()
    product_profiles = ProductProfileSerializer(many=True, read_only=True)

    class Meta:
        model = Material
        fields = [
            "id",  # 系統 ID
            "code",  # 物料代號
            "name",  # 物料名稱
            "english_name",  # 物料英文名稱
            "phase",  # 物料使用階段 (IN_DEV / IN_PROD)
            "type",  # 物料類型
            "unit",  # 單位
            "estimated_cost",  # 預估成本 (動態計算：三個月加權平均)
            "nutrition_fact", # 八大營養價值標示
            "allergen_info",  # 過敏原資訊
            "storage_life",  # 保存期限
            "description",  # 描述 (成分來源)
            "additive_license_no",  # 添加物許可證號
            "is_additive",  # 是否為添加物
            "legal_limit_percent",  # 添加物比例上限
            "license_valid_date",  # 許可證效期
            "product_registration_no",  # 產品登錄號
            "origin",  # 產地
            "product_profiles",  # 關聯成品專屬資訊
            "is_active",  # 是否啟用
            "is_raw_material",  # 是否為原物料
            "pack_capacity",  # PACK 限定：包材容量（KG）
            "created_by",  # 建立者
            "creator_name",  # 建立者姓名 (自訂方法)
            "created_at",  # 建立時間
            "updated_at",  # 更新時間
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def to_internal_value(self, data):
        mutable_data = data.copy()

        if mutable_data.get("license_valid_date") == "":
            mutable_data["license_valid_date"] = None

        return super().to_internal_value(mutable_data)

    def get_creator_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.last_name}{obj.created_by.first_name}"
        return "系統產生"

    def get_estimated_cost(self, obj):
        if hasattr(obj, "annotated_estimated_cost"):
            return round(obj.annotated_estimated_cost, 2)
        return obj.estimated_cost


class BatchInventorySerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)
    unit = serializers.CharField(source="material.unit", read_only=True)
    material_type = serializers.CharField(source="material.type", read_only=True)

    class Meta:
        model = BatchInventory
        fields = [
            "id",
            "material",
            "material_name",
            "material_type",
            "unit",
            "batch_number",
            "original_qty",
            "remaining_qty",
            "received_date",
            "expiration_date",
            "adjustment_type",
            "adjustment_qty",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class BOMMaterialMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = ["id", "code", "name", "type", "unit", "pack_capacity"]


class BOMSerializer(serializers.ModelSerializer):
    parent = BOMMaterialMinimalSerializer(read_only=True)
    child = BOMMaterialMinimalSerializer(read_only=True)
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Material.objects.all(), source="parent", write_only=True
    )
    child_id = serializers.PrimaryKeyRelatedField(
        queryset=Material.objects.all(), source="child", write_only=True
    )

    class Meta:
        model = BOM
        fields = [
            "id",
            "parent",
            "child",
            "parent_id",
            "child_id",
            "base_quantity",
            "quantity_required",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def _get_additive_contributions(self, material, current_ratio):
        """
        遞迴函數：計算傳入的 material (包含其子件) 會貢獻多少添加物比例
        """
        additives = {}

        # 1. 如果自己本身就是添加物
        if material.is_additive and material.legal_limit_percent:
            additives[material.code] = {
                "name": material.name,
                "limit": Decimal(str(material.legal_limit_percent)),
                "ratio": Decimal(str(current_ratio)),
            }

        # 2. 如果是半成品，遞迴往下挖
        elif material.type == "SEMI":
            semi_boms = material.main_product.filter(is_active=True).select_related(
                "child"
            )

            if semi_boms.exists():
                semi_base_qty = semi_boms.first().base_quantity
                for bom in semi_boms:
                    child_ratio = Decimal(str(current_ratio)) * (
                        bom.quantity_required / semi_base_qty
                    )
                    child_adds = self._get_additive_contributions(
                        bom.child, child_ratio
                    )

                    for code, data in child_adds.items():
                        if code in additives:
                            additives[code]["ratio"] += data["ratio"]
                        else:
                            additives[code] = data

        return additives

    def _check_additive_limits(
        self, parent, child, base_qty, qty_required, exclude_bom_id=None
    ):
        """
        核心驗算邏輯：計算加入此筆明細後，總配方是否會超標
        """
        base_qty = Decimal(str(base_qty))
        qty_required = Decimal(str(qty_required))

        if base_qty <= 0:
            raise ValidationError({"base_quantity": ["基準產量必須大於 0"]})

        # 1. 取得這筆「準備新增/修改」的明細，會帶入多少添加物
        current_item_ratio = qty_required / base_qty
        new_additives = self._get_additive_contributions(child, current_item_ratio)

        if not new_additives:
            return  # 沒有添加物，安全放行

        # 2. 撈取同配方(母件)底下「其他」已存在的 BOM
        existing_boms = parent.main_product.filter(is_active=True).select_related(
            "child"
        )

        if exclude_bom_id:
            existing_boms = existing_boms.exclude(id=exclude_bom_id)

        total_additives = new_additives.copy()

        # 3. 累加資料庫內現有配方的添加物
        for bom in existing_boms:
            bom_ratio = bom.quantity_required / bom.base_quantity
            existing_adds = self._get_additive_contributions(bom.child, bom_ratio)

            for code, data in existing_adds.items():
                if code in total_additives:
                    total_additives[code]["ratio"] += data["ratio"]
                else:
                    total_additives[code] = data

        # 4. 最終驗算：是否超過法規上限
        for code, data in total_additives.items():
            usage_percent = data["ratio"] * Decimal(100)
            if usage_percent > data["limit"]:
                raise ValidationError(
                    {
                        "non_field_errors": [
                            f"後端防護阻擋：添加物【{data['name']}】總佔比 ({usage_percent.quantize(Decimal('0.00'))}%) 已超過法定安全上限 {data['limit']}%！"
                        ]
                    }
                )

    @transaction.atomic
    def create(self, validated_data):
        parent = Material.objects.select_for_update().get(
            id=validated_data["parent"].id
        )

        self._check_additive_limits(
            parent=parent,
            child=validated_data["child"],
            base_qty=validated_data["base_quantity"],
            qty_required=validated_data["quantity_required"],
        )

        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        parent_id = validated_data.get("parent", instance.parent).id
        parent = Material.objects.select_for_update().get(id=parent_id)

        self._check_additive_limits(
            parent=parent,
            child=validated_data.get("child", instance.child),
            base_qty=validated_data.get("base_quantity", instance.base_quantity),
            qty_required=validated_data.get(
                "quantity_required", instance.quantity_required
            ),
            exclude_bom_id=instance.id,  # 排除自己舊的數據，避免重複計算
        )

        return super().update(instance, validated_data)


class CustomerOrderSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Material.objects.all(), source="product", write_only=True
    )

    mrp_id = serializers.PrimaryKeyRelatedField(
        queryset=MaterialRequirementPlan.objects.all(),
        source="mrp",
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = CustomerOrder
        fields = "__all__"
        read_only_fields = ["created_by", "product", "mrp"]


class MaterialRequirementPlanSerializer(serializers.ModelSerializer):
    used_batch_number = serializers.SerializerMethodField()
    product_name = serializers.ReadOnlyField(source="product.name")
    product_code = serializers.ReadOnlyField(source="product.code")
    unit = serializers.ReadOnlyField(source="product.unit")
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    customer_orders = CustomerOrderSerializer(many=True, read_only=True)

    class Meta:
        model = MaterialRequirementPlan
        fields = [
            "id",
            "mrp_id",
            "parent_id",
            "vendor_info",
            "batch_inventory_info",
            "customer_orders",
            "product_id",
            "product_name",
            "product_code",
            "used_batch_number",
            "unit",
            "status",
            "is_active",
            "required_qty",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_required_qty(self, value):
        if value <= 0:
            raise serializers.ValidationError("需求數量必須大於零。")
        return value

    def validate_batch_inventory_info(self, value):
        if not value:
            return value

        if isinstance(value, dict):
            value = list(value.values())
        elif not isinstance(value, list):
            raise serializers.ValidationError("批號分配資訊必須是 JSON 陣列格式。")

        for mat_info in value:
            if not isinstance(mat_info, dict):
                raise serializers.ValidationError("物料的資料結構錯誤。")

            batches = mat_info.get("batches", [])
            if not isinstance(batches, list):
                raise serializers.ValidationError("物料的批號資料必須是陣列格式。")

            for batch in batches:
                used = batch.get("used", 0)
                batch_number = batch.get("batch_number", "未知批號")

                if used == "":
                    used = 0

                try:
                    used_qty = float(used)
                    available_qty = float(batch.get("available", 0))
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        f"批號 {batch_number} 的數量格式錯誤，必須是數字。"
                    )

                if used_qty < 0:
                    raise serializers.ValidationError(
                        f"批號 {batch_number} 的使用量不能為負數。"
                    )

                if used_qty > available_qty + 0.0001:
                    raise serializers.ValidationError(
                        f"批號 {batch_number} 的使用量 ({used_qty}) 不可大於剩餘可用量 ({available_qty})。"
                    )
        return value

    def get_used_batch_number(self, obj):
        batch = (
            BatchInventory.objects.filter(material_id=obj.product, is_active=True)
            .order_by("-created_at")
            .first()
        )
        if batch:
            return batch.batch_number
        return ""


class ProductionLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = ProductionLog
        fields = ["id", "production_order", "username", "action_detail", "created_at"]
        read_only_fields = ["id", "created_at"]


class SimpleProductSerializer(serializers.ModelSerializer):
    spec = serializers.SerializerMethodField()
    sales_price = serializers.SerializerMethodField()
    sales_unit = serializers.SerializerMethodField()
    sales_pack_unit = serializers.SerializerMethodField()
    sales_unit_quantity = serializers.SerializerMethodField()
    sales_pack_quantity = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = [
            "id",
            "code",
            "name",
            "type",
            "unit",
            "spec",
            "sales_price",
            "sales_unit",
            "sales_pack_unit",
            "sales_unit_quantity",
            "sales_pack_quantity",
        ]

    def _get_profile(self, obj):
        # 抓取第一筆設定的 Profile
        return obj.product_profiles.first()

    def get_spec(self, obj):
        profile = self._get_profile(obj)
        return profile.spec if profile else None

    def get_sales_price(self, obj):
        profile = self._get_profile(obj)
        return str(profile.sales_price) if profile and profile.sales_price else None

    def get_sales_unit(self, obj):
        profile = self._get_profile(obj)
        return profile.sales_unit if profile else "箱"

    def get_sales_pack_unit(self, obj):
        profile = self._get_profile(obj)
        return profile.sales_pack_unit if profile else "包"

    def get_sales_unit_quantity(self, obj):
        profile = self._get_profile(obj)
        return str(profile.sales_unit_quantity) if profile else "1"

    def get_sales_pack_quantity(self, obj):
        profile = self._get_profile(obj)
        return str(profile.sales_pack_quantity) if profile else "1"


class ProductionOrderSerializer(serializers.ModelSerializer):
    product_profile = SimpleProductSerializer(source="product", read_only=True)
    used_batch_number = serializers.SerializerMethodField()
    creator_name = serializers.SerializerMethodField()
    is_fully_delivered = serializers.BooleanField(read_only=True)
    remaining_qty = serializers.DecimalField(
        max_digits=15, decimal_places=4, read_only=True
    )

    class Meta:
        model = ProductionOrder
        fields = [
            "id",
            "order_number",
            "parent_id",
            "used_batch_number",
            "product_id",
            "product_profile",
            "target_qty",
            "actual_qty",
            "materials_info",
            "vendor_info",
            "is_fully_delivered",
            "remaining_qty",
            "delivery_notes",
            "created_by",
            "creator_name",
            "created_at",
            "updated_at",
            "is_active",
        ]

    def get_creator_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.last_name}{obj.created_by.first_name}"
        return "系統產生"

    def get_used_batch_number(self, obj):
        batch = (
            BatchInventory.objects.filter(material_id=obj.product_id, is_active=True)
            .order_by("-created_at")
            .first()
        )
        if batch:
            return batch.batch_number
        return ""


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = [
            "id",
            "name",
            "code",
            "tax_id",
            "address",
            "phone",
            "contact_person",
            "is_deleted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_deleted", "created_at", "updated_at"]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(self, user):
        token = super().get_token(user)
        token["username"] = user.username
        if hasattr(user, "profile"):
            token["department"] = user.profile.department
        else:
            token["department"] = None
        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        user = self.user
        user_data = {
            "id": user.id,
            "username": user.username,
            "department": user.profile.department if hasattr(user, "profile") else None,
            "is_active": user.is_active,
        }

        return {
            "refresh": data["refresh"],
            "access": data["access"],
            "user": user_data,
        }


class PurchaseRequisitionItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    material_id = serializers.PrimaryKeyRelatedField(
        queryset=Material.objects.all(), source="material"
    )
    material_provider_id = serializers.PrimaryKeyRelatedField(
        queryset=MaterialProvider.objects.all(),
        source="material_provider",
        required=False,
        allow_null=True,
    )
    purchased_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=True
    )

    material_name = serializers.ReadOnlyField()
    provider_name = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequisitionItem
        fields = [
            "id",
            "material_id",
            "quantity",
            "unit",
            "expected_delivery_date",
            "material_provider_id",
            "provider_name",
            "remark",
            "purchased_price",
            "material_name",
        ]

    def get_provider_name(self, obj):
        if obj.material_provider:
            return obj.material_provider.name
        return ""


class PurchaseRequisitionSerializer(serializers.ModelSerializer):
    items = PurchaseRequisitionItemSerializer(many=True)

    class Meta:
        model = PurchaseRequisition
        fields = "__all__"


class DeliveryNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryNote
        fields = "__all__"
        read_only_fields = [
            "id",
            "note_number",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def to_representation(self, instance):
        response = super().to_representation(instance)

        if instance.production_order:
            response["production_order_detail"] = ProductionOrderSerializer(
                instance.production_order
            ).data

        return response


# 追蹤追溯主要 API
class RecallReportSerializer(serializers.Serializer):
    material_id = serializers.IntegerField()
    material_name = serializers.CharField()
    material_code = serializers.CharField()

    # 1. 回收原料總量 (異常原料進貨總量/已投入量)
    used_raw_total = serializers.DecimalField(max_digits=15, decimal_places=4)
    # 2. 尚未使用原料總量 (異常原料在庫總量)
    unused_raw_total = serializers.DecimalField(max_digits=15, decimal_places=4)
    # 3. 產品生產總量 (牽涉到的成品總重量)
    total_produced_product = serializers.DecimalField(max_digits=15, decimal_places=4)
    # 4. 尚未出貨產品總量 (各品項在庫總量)
    total_in_stock_product = serializers.DecimalField(max_digits=15, decimal_places=4)
    # 5. 下游總出貨總量 (已出貨至下游廠商之總量)
    total_shipped_product = serializers.DecimalField(max_digits=15, decimal_places=4)


class MaterialMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = ["id", "code", "name", "type", "unit", "estimated_cost"]


class CustomerQuotationItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    product_detail = MaterialMinimalSerializer(source="product", read_only=True)
    total_cost_per_kg = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    calculated_price = serializers.IntegerField(read_only=True)

    # 🌟 與 Model 欄位名稱完全統一的外掛欄位 (供 ProductProfile 使用)
    sales_unit = serializers.CharField(max_length=10, required=False, write_only=True)
    sales_unit_quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, write_only=True
    )
    sales_pack_unit = serializers.CharField(
        max_length=10, required=False, write_only=True
    )
    sales_pack_quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, write_only=True
    )

    class Meta:
        model = CustomerQuotationItem
        fields = [
            "id",
            "product",
            "product_detail",
            "costs_breakdown",
            "spec",
            "pricing_multiplier",
            "final_price_per_kg",
            "total_cost_per_kg",
            "calculated_price",
            "is_active",
            "sales_unit",
            "sales_unit_quantity",
            "sales_pack_unit",
            "sales_pack_quantity",
        ]
        extra_kwargs = {"product": {"write_only": True}}


class CustomerQuotationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    items = CustomerQuotationItemSerializer(many=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomerQuotation
        fields = [
            "id",
            "quotation_number",
            "issue_date",
            "customer",
            "customer_name",
            "status",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
            "items",
        ]
        read_only_fields = [
            "quotation_number",
            "issue_date",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.last_name}{obj.created_by.first_name}"
        return ""

    def _sync_product_profile(self, item_data, customer):
        """
        🌟 同步更新或建立 ProductProfile，直接使用統一的變數名稱提取資料
        """
        material = item_data.get("product")
        if not material:
            return

        spec = item_data.get("spec", "")
        sales_unit = item_data.get("sales_unit", "箱")
        sales_unit_quantity = item_data.get("sales_unit_quantity", 1)
        sales_pack_unit = item_data.get("sales_pack_unit", "包")
        sales_pack_quantity = item_data.get("sales_pack_quantity", 1)
        sales_price = item_data.get("final_price_per_kg", None)

        profile = ProductProfile.objects.filter(
            material=material, vendor=customer
        ).first()

        if profile:
            profile.spec = spec
            profile.sales_unit = sales_unit
            profile.sales_unit_quantity = sales_unit_quantity
            profile.sales_pack_unit = sales_pack_unit
            profile.sales_pack_quantity = sales_pack_quantity
            profile.sales_price = sales_price
            profile.save()
        else:
            ProductProfile.objects.create(
                material=material,
                vendor=customer,
                spec=spec,
                sales_unit=sales_unit,
                sales_unit_quantity=sales_unit_quantity,
                sales_pack_unit=sales_pack_unit,
                sales_pack_quantity=sales_pack_quantity,
                sales_price=sales_price,
            )

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        customer = validated_data.get("customer")

        quotation = super().create(validated_data)

        for item_data in items_data:
            self._sync_product_profile(item_data, customer)

            item_data.pop("id", None)
            item_data.pop("sales_unit", None)
            item_data.pop("sales_unit_quantity", None)
            item_data.pop("sales_pack_unit", None)
            item_data.pop("sales_pack_quantity", None)

            CustomerQuotationItem.objects.create(quotation=quotation, **item_data)

        return quotation

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        customer = validated_data.get("customer", instance.customer)

        instance = super().update(instance, validated_data)

        if items_data is not None:
            existing_items = {
                item.id: item for item in instance.items.filter(is_active=True)
            }
            incoming_ids = set()
            items_to_update = []
            items_to_delete = []

            for item_data in items_data:
                item_id = item_data.get("id")

                self._sync_product_profile(item_data, customer)

                # 清除外掛欄位 (變數名稱已統一)
                item_data.pop("sales_unit", None)
                item_data.pop("sales_unit_quantity", None)
                item_data.pop("sales_pack_unit", None)
                item_data.pop("sales_pack_quantity", None)

                if item_id and item_id in existing_items:
                    incoming_ids.add(item_id)
                    existing_item = existing_items[item_id]

                    for attr, value in item_data.items():
                        setattr(existing_item, attr, value)

                    items_to_update.append(existing_item)
                else:
                    item_data.pop("id", None)
                    CustomerQuotationItem.objects.create(
                        quotation=instance, **item_data
                    )

            for existing_id, existing_item in existing_items.items():
                if existing_id not in incoming_ids:
                    existing_item.is_active = False
                    items_to_delete.append(existing_item)

            if items_to_delete:
                CustomerQuotationItem.objects.bulk_update(
                    items_to_delete, ["is_active"]
                )

            if items_to_update:
                update_fields = [
                    "spec",
                    "costs_breakdown",
                    "pricing_multiplier",
                    "final_price_per_kg",
                ]
                CustomerQuotationItem.objects.bulk_update(
                    items_to_update, update_fields
                )

        return instance
