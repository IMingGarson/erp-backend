from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    BOM,
    BatchInventory,
    CustomerOrder,
    DeliveryNote,
    Material,
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
        fields = ["spec", "sales_unit", "sales_price", "label_info"]


class MaterialSerializer(serializers.ModelSerializer):
    is_raw_material = serializers.ReadOnlyField()
    creator_name = serializers.SerializerMethodField()
    product_profile = ProductProfileSerializer(read_only=True)

    class Meta:
        model = Material
        fields = [
            "id",
            "code",
            "name",
            "type",
            "unit",
            "unit_price",
            "product_profile",
            "is_active",
            "is_raw_material",
            "created_by",
            "creator_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_creator_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.last_name}{obj.created_by.first_name}"
        return "系統產生"


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


class BOMSerializer(serializers.ModelSerializer):
    parent = MaterialSerializer(read_only=True)
    child = MaterialSerializer(read_only=True)

    class Meta:
        model = BOM
        fields = [
            "id",
            "parent",
            "child",
            "quantity_required",
            "base_quantity",
            "is_active",
        ]


# class BOMSerializer(serializers.ModelSerializer):
#     parent_name = serializers.CharField(source="parent.name", read_only=True)
#     child_name = serializers.CharField(source="child.name", read_only=True)
#     child_code = serializers.CharField(source="child.code", read_only=True)
#     child_type = serializers.CharField(source="child.type", read_only=True)

#     class Meta:
#         model = BOM
#         fields = [
#             "id",
#             "parent",
#             "parent_name",
#             "child",
#             "child_code",
#             "child_name",
#             "child_type",
#             "is_active",
#             "quantity_required",
#         ]
#         read_only_fields = ["id"]


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


class ProductionOrderSerializer(serializers.ModelSerializer):
    used_batch_number = serializers.SerializerMethodField()
    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_type = serializers.CharField(source="product.type", read_only=True)
    product_unit = serializers.CharField(source="product.unit", read_only=True)
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
            "product_code",
            "product_name",
            "product_type",
            "product_unit",
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
    purchased_price = serializers.IntegerField(required=True, allow_null=False)

    class Meta:
        model = PurchaseRequisitionItem
        fields = [
            "id",
            "material_id",
            "quantity",
            "unit",
            "expected_delivery_date",
            "supplier",
            "remark",
            "purchased_price",
            "material_name",
        ]


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