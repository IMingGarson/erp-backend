from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import models, transaction
from django.db.models import (
    CharField,
    ExpressionWrapper,
    F,
    FloatField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    BOM,
    BatchInventory,
    BatchInventoryLog,
    BOMLog,
    CustomerOrder,
    CustomerOrderLog,
    CustomerQuotation,
    CustomerQuotationItem,
    CustomerQuotationLog,
    DeliveryNote,
    DeliveryNoteLog,
    Material,
    MaterialLog,
    MaterialProvider,
    MaterialRequirementPlan,
    MaterialRequirementPlanLog,
    ProductionLog,
    ProductionOrder,
    PurchaseRequisition,
    PurchaseRequisitionItem,
    PurchaseRequisitionLog,
    Vendor,
    VendorLog,
)
from .permissions import IsAdminOrEmployerOrReadOnly, IsRDOrReadOnly
from .serializers import (
    BatchInventorySerializer,
    BOMSerializer,
    CustomerOrderSerializer,
    CustomerQuotationSerializer,
    DeliveryNoteSerializer,
    MaterialProviderSerializer,
    MaterialRequirementPlanSerializer,
    MaterialSerializer,
    ProductionOrderSerializer,
    PurchaseRequisitionSerializer,
    VendorSerializer,
)


def to_decimal5(value):
    """轉換為精準的五位小數 Decimal"""
    FIVE_DECIMALS = Decimal("0.00000")
    if value is None or value == "":
        return FIVE_DECIMALS
    try:
        return Decimal(str(value)).quantize(FIVE_DECIMALS, rounding=ROUND_HALF_UP)
    except (ValueError, TypeError, InvalidOperation):
        return FIVE_DECIMALS


class CRUDAuditMixin:
    LOG_MODEL_MAP = {
        Material: (MaterialLog, "material"),
        Vendor: (VendorLog, "vendor"),
        BOM: (BOMLog, "bom"),
        MaterialRequirementPlan: (MaterialRequirementPlanLog, "mrp_plan"),
        BatchInventory: (BatchInventoryLog, "batch_inventory"),
        ProductionOrder: (ProductionLog, "production_order"),
        PurchaseRequisition: (PurchaseRequisitionLog, "purchase_requisition"),
        DeliveryNote: (DeliveryNoteLog, "delivery_notes"),
        CustomerOrder: (CustomerOrderLog, "customer_order"),
        CustomerQuotation: (CustomerQuotationLog, "quotation"),
    }

    def get_valid_user(self):
        """獲取並驗證當前使用者"""
        user = self.request.user
        if user and user.is_authenticated:
            return user

        raise NotAuthenticated("無法識別使用者身分，拒絕操作。")

    def _get_field_display_value(self, instance, field, value):
        if value is None or value == "":
            return "空值"

        if isinstance(value, bool):
            return "是" if value else "否"

        if isinstance(field, models.ForeignKey) or hasattr(value, "pk"):
            return str(value)

        if getattr(field, "choices", None):
            choice_dict = dict(field.choices)
            return str(choice_dict.get(value, value))

        return str(value)

    def _record_db_log(self, instance, user, action_detail):
        model_class = type(instance)

        if model_class in self.LOG_MODEL_MAP:
            LogModel, fk_field_name = self.LOG_MODEL_MAP[model_class]

            log_data = {
                fk_field_name: instance,
                "user": user,
                "action_detail": action_detail,
            }
            LogModel.objects.create(**log_data)

    def perform_create(self, serializer):
        user = self.get_valid_user()
        full_username = f"{user.last_name}{user.first_name}"

        save_kwargs = {}
        if hasattr(serializer.Meta.model, "created_by"):
            save_kwargs["created_by"] = user

        instance = serializer.save(**save_kwargs)
        model_name = instance.__class__.__name__
        action_detail = ""

        if model_name == "MaterialRequirementPlan":
            action_detail = f"{full_username} 建立了物料需求單 #{instance.mrp_id}"

        elif model_name == "Vendor":
            action_detail = f"{full_username} 建立了客戶資料 {instance.name}"

        elif model_name == "ProductionOrder":
            action_detail = f"{full_username} 建立了生產單 #{instance.order_number}"

        elif model_name == "DeliveryNote":
            action_detail = f"{full_username} 建立了銷貨單 #{instance.note_number}"

        elif model_name == "CustomerOrder":
            action_detail = f"{full_username} 建立了客戶訂單 #{instance.order_number}"

        elif model_name == "PurchaseRequisition":
            action_detail = f"{full_username} 建立了請購單 #{instance.id}"

        elif model_name == "Material":
            action_detail = (
                f"{full_username} 建立了物料 {instance.name} #{instance.code}"
            )

        elif model_name == "BatchInventory":
            action_detail = f"{full_username} 建立了批號庫存 {instance.material.name} #{instance.batch_number}"

        elif model_name == "BOM":
            action_detail = f"{full_username} 建立了配方 ({instance.parent.name} #{instance.parent.code} -> {instance.child.name} #{instance.child.code})"

        elif model_name == "CustomerQuotation":
            action_detail = f"{full_username} 建立了報價單 #{instance.quotation_number} (客戶: {instance.customer.name})"

        else:
            action_detail = f"{full_username} 建立了此筆資料 (ID: {instance.pk})"

        self._record_db_log(instance, user, action_detail)

    def perform_update(self, serializer):
        user = self.get_valid_user()
        old_instance = serializer.instance

        changes = []
        for field_name, new_val in serializer.validated_data.items():
            if field_name in ["updated_at", "updated_by", "created_at", "created_by"]:
                continue

            try:
                field = old_instance._meta.get_field(field_name)
                old_val = getattr(old_instance, field_name)
                if isinstance(field, models.JSONField) or isinstance(
                    old_val, (dict, list)
                ):
                    verbose_name = getattr(field, "verbose_name", field_name)
                    json_diffs = self.get_json_diff(old_val or {}, new_val or {})

                    if json_diffs:
                        diff_str = "，".join(json_diffs)
                        changes.append(f"「{verbose_name}」細節異動: {diff_str}")

                    continue

                if old_val != new_val:
                    verbose_name = getattr(field, "verbose_name", field_name)
                    old_display = self._get_field_display_value(
                        old_instance, field, old_val
                    )
                    new_display = self._get_field_display_value(
                        old_instance, field, new_val
                    )

                    changes.append(
                        f"「{verbose_name}」由 '{old_display}' 改為 '{new_display}'"
                    )
            except Exception:
                pass

        save_kwargs = {}
        if hasattr(serializer.Meta.model, "updated_by"):
            save_kwargs["updated_by"] = user

        instance = serializer.save(**save_kwargs)
        full_username = f"{user.last_name}{user.first_name}"

        if changes:
            action_detail = f"{full_username} 更新了: " + "，".join(changes)
            self._record_db_log(instance, user, action_detail)

    def perform_destroy(self, instance):
        user = self.get_valid_user()
        full_username = f"{user.last_name}{user.first_name}"
        model_name = instance.__class__.__name__
        action_detail = ""

        if model_name == "Vendor":
            instance.is_deleted = True
            instance.save(update_fields=["is_deleted"])
            action_detail = f"{full_username} 刪除了客戶資料 {instance.name}"

        elif model_name == "MaterialRequirementPlan":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            instance.__class__.objects.filter(parent_id=instance.mrp_id).update(
                is_active=False
            )
            action_detail = f"{full_username} 刪除了物料需求單 #{instance.mrp_id}"

        elif model_name == "ProductionOrder":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            action_detail = f"{full_username} 刪除了生產單 #{instance.order_number}"

        elif model_name == "DeliveryNote":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            action_detail = f"{full_username} 刪除了銷貨單 #{instance.note_number}"

        elif model_name == "CustomerOrder":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            action_detail = f"{full_username} 刪除了客戶訂單 #{instance.order_number}"

        elif model_name == "PurchaseRequisition":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            instance.items.update(is_active=False)
            action_detail = f"{full_username} 刪除了請購單 #{instance.id}"

        elif model_name == "Material":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            action_detail = (
                f"{full_username} 停用了物料 {instance.name} #{instance.code}"
            )

        elif model_name == "BatchInventory":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            action_detail = f"{full_username} 停用了批號庫存 {instance.material.name} #{instance.batch_number}"

        elif model_name == "BOM":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            action_detail = f"{full_username} 停用了配方 ({instance.parent.name} #{instance.parent.code} -> {instance.child.name} #{instance.child.code})"
        else:
            action_detail = f"{full_username} 停用此筆資料 (ID: {instance.pk})"

        if user and action_detail:
            self._record_db_log(instance, user, action_detail)

    def get_json_diff(self, old_obj, new_obj, path=""):
        local_changes = []

        if isinstance(old_obj, dict) and isinstance(new_obj, dict):
            all_keys = set(old_obj.keys()).union(set(new_obj.keys()))
            for k in all_keys:
                current_path = f"{path}.{k}" if path else str(k)
                if k not in old_obj:
                    local_changes.append(f"新增了 '{current_path}': '{new_obj[k]}'")
                elif k not in new_obj:
                    local_changes.append(f"移除了 '{current_path}'")
                else:
                    local_changes.extend(
                        self.get_json_diff(old_obj[k], new_obj[k], current_path)
                    )

        elif isinstance(old_obj, list) and isinstance(new_obj, list):
            max_len = max(len(old_obj), len(new_obj))
            for i in range(max_len):
                current_path = f"{path}[{i}]"
                if i >= len(old_obj):
                    local_changes.append(f"新增了 '{current_path}': '{new_obj[i]}'")
                elif i >= len(new_obj):
                    local_changes.append(f"移除了 '{current_path}'")
                else:
                    local_changes.extend(
                        self.get_json_diff(old_obj[i], new_obj[i], current_path)
                    )

        else:
            if str(old_obj or "") != str(new_obj or ""):
                local_changes.append(f"'{path}' 由 '{old_obj}' 改為 '{new_obj}'")

        return local_changes


class ProductionOrderViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = ProductionOrder.objects.filter(is_active=True).order_by("-created_at")
    serializer_class = ProductionOrderSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsAdminOrEmployerOrReadOnly()]

    def list(self, request, *args, **kwargs):
        """
        取得生產單列表 (支援多種條件篩選)
        """
        queryset = self.get_queryset()

        search_keyword = request.query_params.get("search")
        if search_keyword:
            queryset = queryset.filter(
                models.Q(order_number__icontains=search_keyword)
                | models.Q(product__name__icontains=search_keyword)
            )

        parent_id = request.query_params.get("parent_id")
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)

        is_root = request.query_params.get("is_root")
        if is_root == "true":
            queryset = queryset.filter(models.Q(parent_id__isnull=True))

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """
        取得單一生產單詳細資訊
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        data = serializer.data

        if not instance.parent_id:
            children = self.get_queryset().filter(parent_id=instance.order_number)
            data["children_orders"] = ProductionOrderSerializer(
                children, many=True
            ).data

        return Response(data)


class MaterialRequirementPlanViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = (
        MaterialRequirementPlan.objects.filter(
            is_active=True,
        )
        .prefetch_related("customer_orders")
        .order_by("-created_at")
    )
    serializer_class = MaterialRequirementPlanSerializer

    def get_permissions(self):
        return [IsAuthenticated()]

        # return [IsAuthenticated(), IsAdminOrEmployerOrReadOnly()]

    @action(detail=False, methods=["get"])
    def daily_sequence(self, request):
        """取得今日 MRP 流水號的下一個可用號碼"""
        today_str = timezone.localtime(timezone.now()).strftime("%Y%m%d")
        prefix = f"P{today_str}"

        mrp_ids = MaterialRequirementPlan.objects.filter(
            mrp_id__startswith=prefix
        ).values_list("mrp_id", flat=True)

        max_seq = 0
        for mrp_id in mrp_ids:
            suffix = mrp_id[len(prefix) :]
            seq_str = suffix.split("-")[0]

            if seq_str.isdigit():
                max_seq = max(max_seq, int(seq_str))

        return Response({"sequence": max_seq + 1, "prefix": prefix})

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def bulk_create_drafts(self, request):
        user = self.get_valid_user()
        vendor_data = request.data.get("vendor_data")
        root_mrp = request.data.get("parent_mrp_payload")

        if not root_mrp:
            return Response(
                {"error": "缺少單據資料"}, status=status.HTTP_400_BAD_REQUEST
            )

        v_info_json = {
            "name": vendor_data.get("name"),
            "logistics": vendor_data.get("logisticsProvider"),
            "shipping_date": vendor_data.get("shippingDate"),
            "address": vendor_data.get("address"),
            "phone": vendor_data.get("phone"),
            "notes": vendor_data.get("notes"),
            "code": vendor_data.get("code"),
        }

        created_mrps = []

        def save_mrp_recursive(mrp_data, parent_id=None):
            batch_info = mrp_data.get("batch_inventory_info", {}).values()
            if not batch_info:
                return False

            if not all(
                [
                    mrp_data.get("id", False),
                    mrp_data.get("productId", False),
                    mrp_data.get("qty", 0),
                ]
            ):
                return False

            new_mrp = MaterialRequirementPlan.objects.create(
                mrp_id=mrp_data.get("id"),
                parent_id=parent_id,
                vendor_info=v_info_json,
                batch_inventory_info=list(batch_info),
                product_id=mrp_data.get("productId"),
                required_qty=mrp_data.get("qty"),
                created_by=user,
            )

            created_mrps.append(
                {
                    "id": new_mrp.id,
                    "parent_id": parent_id,
                    "product_id": mrp_data.get("productId"),
                }
            )
            self._record_db_log(
                new_mrp, user, f"{user.last_name}{user.first_name} 建立此需求單草稿"
            )

            children = mrp_data.get("children_mrp", [])
            for child in children:
                save_mrp_recursive(child, parent_id=mrp_data.get("id"))

            return True

        for r in root_mrp:
            save_mrp_recursive(r)

        return Response(created_mrps, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def convert_to_production(self, request):
        """將 MRP 草稿轉為生產單"""
        user = self.get_valid_user()
        mrp_id = request.data.get("mrp_id")

        if not mrp_id:
            return Response({"error": "Invalid ID"})

        # 1. 撈出母單 (當前 PK 指定的 MRP)
        try:
            parent_mrp = self.get_queryset().get(
                id=mrp_id, status=MaterialRequirementPlan.STATUS_CHOICES[0][0]
            )
        except MaterialRequirementPlan.DoesNotExist:
            return Response(
                {"error": "找不到此 MRP 母單"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 2. 撈出對應的所有子單
        children_mrps = MaterialRequirementPlan.objects.filter(
            parent_id=parent_mrp.mrp_id,
            status=MaterialRequirementPlan.STATUS_CHOICES[0][0],
        )

        all_mrps = [parent_mrp] + list(children_mrps)

        # 3. 檢查並真實扣除庫存 (防超賣)
        for mrp in all_mrps:
            for material_item in mrp.batch_inventory_info:
                for batch in material_item.get("batches", []):
                    used_str = batch.get("used", "")

                    if not used_str:
                        continue

                    try:
                        used_qty = Decimal(str(used_str))
                    except (InvalidOperation, ValueError):
                        continue

                    if used_qty <= 0:
                        continue

                    batch_id = batch.get("id")

                    try:
                        inventory = BatchInventory.objects.select_for_update().get(
                            id=batch_id
                        )
                    except BatchInventory.DoesNotExist:
                        raise ValidationError(f"找不到批次庫存 ID: {batch_id}")

                    if inventory.remaining_qty < used_qty:
                        self._record_db_log(
                            inventory,
                            user,
                            f"{user.last_name}{user.first_name} 執行從物料單號：{mrp.mrp_id} 轉單失敗，庫存不足！批次 {batch.get('batch_number')} 僅剩 {inventory.remaining_qty}，但需要扣除 {used_qty}",
                        )
                        raise ValidationError(
                            f"庫存不足！批次 {batch.get('batch_number')} 僅剩 {inventory.remaining_qty}，但需要扣除 {used_qty}"
                        )

                    # 修正：真實扣除庫存，並將 update_fields 改為 remaining_qty
                    inventory.remaining_qty -= used_qty
                    inventory.save(update_fields=["remaining_qty"])
                    self._record_db_log(
                        inventory,
                        user,
                        f"{user.last_name}{user.first_name} 執行從物料單號：{mrp.mrp_id} 轉單，自動扣除庫存數量 {used_qty}",
                    )

        # 4. 準備產生生產單
        created_pos = []
        child_po_map = {}  # 用來記錄 子 MRP ID 對應到的 子生產單

        # 先建立子單的生產單
        for child_mrp in children_mrps:
            sorted_materials = sorted(
                child_mrp.batch_inventory_info,
                key=lambda x: float(x.get("requiredQty", 0)),
                reverse=True,
            )

            child_po = ProductionOrder.objects.create(
                order_number=child_mrp.mrp_id,
                product=child_mrp.product,
                target_qty=child_mrp.required_qty,
                materials_info=sorted_materials,
                vendor_info=child_mrp.vendor_info,
                created_by=user,
            )
            child_po_map[child_mrp.id] = child_po
            self._record_db_log(
                child_po,
                user,
                f"{user.last_name}{user.first_name} 將單號：{child_mrp.mrp_id} 轉成子生產單",
            )
            created_pos.append(child_po)

        parent_materials_info = []
        for child_mrp in children_mrps:
            parent_materials_info.append(
                {
                    "type": "CHILD_PRODUCT",
                    "code": getattr(child_mrp.product, "code", ""),
                    "unit": getattr(child_mrp.product, "unit", ""),
                    "materialName": child_mrp.product.name,
                    "requiredQty": float(child_mrp.required_qty),
                    "isShortage": False,
                    "child_order_number": child_po_map[child_mrp.id].order_number,
                    "batches": [],
                }
            )

        other_materials = sorted(
            parent_mrp.batch_inventory_info,
            key=lambda x: float(x.get("requiredQty", 0)),
            reverse=True,
        )
        parent_materials_info.extend(other_materials)

        # 建立母生產單
        parent_po = ProductionOrder.objects.create(
            order_number=parent_mrp.mrp_id,
            product=parent_mrp.product,
            target_qty=parent_mrp.required_qty,
            materials_info=parent_materials_info,
            vendor_info=parent_mrp.vendor_info,
            created_by=user,
        )
        created_pos.append(parent_po)
        self._record_db_log(
            parent_po,
            user,
            f"{user.last_name}{user.first_name} 將單號：{parent_mrp.mrp_id} 轉成主生產單",
        )

        for child_po in child_po_map.values():
            child_po.parent_id = parent_po.order_number
            child_po.save(update_fields=["parent_id"])

        for mrp in all_mrps:
            mrp.status = MaterialRequirementPlan.STATUS_CHOICES[1][0]  # conveted
            mrp.save(update_fields=["status"])

        return Response(
            {
                "message": "成功轉為生產單並完成扣庫",
                "created_production_orders": [po.order_number for po in created_pos],
            },
            status=status.HTTP_200_OK,
        )


class MaterialViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    serializer_class = MaterialSerializer
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]

    filterset_fields = ["code", "type", "phase", "is_active"]
    search_fields = ["name", "code", "english_name"]

    def get_permissions(self):
        return [IsAuthenticated()]

        # return [IsAuthenticated(), IsRDOrReadOnly()]

    def get_queryset(self):
        queryset = Material.objects.filter(is_active=True).order_by("-id")

        user = self.request.user
        is_rd = (
            user.is_authenticated
            and hasattr(user, "profile")
            and user.profile.department.upper() == "RD"
        )
        # 只有研發才會 access 到開發中的原物料
        if not is_rd:
            queryset = queryset.filter(phase="IN_PROD")

        # 處理 N+1
        if self.action == "list":
            three_months_ago = timezone.now().date() - timedelta(days=90)

            recent_items = PurchaseRequisitionItem.objects.filter(
                material=OuterRef("pk"),
                is_active=True,
                requisition__is_active=True,
                requisition__status="stocked",
                requisition__request_date__gte=three_months_ago,
            ).values("material")

            recent_avg_cost = recent_items.annotate(
                total_qty=Sum("quantity"),
                total_val=Sum(
                    ExpressionWrapper(
                        F("quantity") * F("purchased_price"), output_field=FloatField()
                    )
                ),
            ).values(
                avg_cost=ExpressionWrapper(
                    F("total_val") / F("total_qty"), output_field=FloatField()
                )
            )[:1]

            fallback_latest_cost = (
                PurchaseRequisitionItem.objects.filter(
                    material=OuterRef("pk"),
                    is_active=True,
                    requisition__is_active=True,
                    requisition__status="stocked",
                )
                .order_by("-requisition__request_date", "-id")
                .values("purchased_price")[:1]
            )

            cost_annotation = Coalesce(
                Subquery(recent_avg_cost, output_field=FloatField()),
                Subquery(fallback_latest_cost, output_field=FloatField()),
                0.0,
                output_field=FloatField(),
            )

            queryset = queryset.annotate(annotated_estimated_cost=cost_annotation)

            annotated_material_qs = Material.objects.filter(is_active=True).annotate(
                annotated_estimated_cost=cost_annotation
            )

            queryset = queryset.prefetch_related(
                Prefetch("main_product__child", queryset=annotated_material_qs),
                Prefetch(
                    "main_product__child__main_product__child",
                    queryset=annotated_material_qs,
                ),
            )

        return queryset


class VendorViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = Vendor.objects.filter(is_deleted=False).order_by("-id")
    serializer_class = VendorSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsRDOrReadOnly()]

    @action(detail=False, methods=["get"], url_path="search")
    def get_vendor_by_code(self, request):
        vendor_code = request.query_params.get("q", "").strip()
        vendor = None
        if vendor_code:
            vendor = Vendor.objects.filter(is_deleted=False, code=vendor_code).first()

        if not vendor:
            return Response({"message": "no data"}, status=status.HTTP_200_OK)

        return Response(self.serializer_class(vendor).data, status=status.HTTP_200_OK)


class MaterialProviderViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = MaterialProvider.objects.filter(is_active=True).order_by("-id")
    serializer_class = MaterialProviderSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsRDOrReadOnly()]


class BatchInventoryViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = BatchInventory.objects.filter(is_active=True).order_by("-id")
    serializer_class = BatchInventorySerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsAdminOrEmployerOrReadOnly()]

    @action(detail=False, methods=["post"], url_path="adjustment")
    @transaction.atomic
    def inventory_adjustment(self, request):
        user = self.get_valid_user()
        payload = request.data
        valid_choices = [choice[0] for choice in BatchInventory.ADJUSTMENT_CHOICES]
        updated_inventories = []

        for item in payload:
            batch_number = item.get("batch_number")
            adjustment_type = item.get("adjustment_type", "")
            adjustment_qty = item.get("adjustment_qty", 0)
            adjustment_code = adjustment_type.upper()

            if not batch_number or adjustment_code not in valid_choices:
                return Response(
                    {"message": "Invalid data"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                inventory = BatchInventory.objects.get(batch_number=batch_number)
                old_type = (
                    inventory.get_adjustment_type_display()
                    if inventory.get_adjustment_type_display()
                    else "無指定"
                )

                inventory.adjustment_type = adjustment_code
                inventory.adjustment_qty = adjustment_qty
                inventory.save(update_fields=["adjustment_type", "adjustment_qty"])

                new_type_name = dict(BatchInventory.ADJUSTMENT_CHOICES).get(
                    adjustment_code
                )
                self._record_db_log(
                    inventory,
                    user,
                    f"{user.last_name}{user.first_name} 執行盤點: 狀態由 '{old_type}' 改為 '{new_type_name}'，數量為 {adjustment_qty}",
                )

                updated_inventories.append(inventory)
            except BatchInventory.DoesNotExist:
                return Response(
                    {"message": f"找不到批號為 {batch_number} 的庫存紀錄"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        serializer = self.get_serializer(updated_inventories, many=True)
        return Response(
            {
                "message": f"成功更新 {len(updated_inventories)} 筆盤點狀態",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="trace")
    def trace_materials(self, request):
        keyword = request.query_params.get("q", "").strip()

        if not keyword:
            return Response(
                {"error": "請提供批號 (batch_number) 或原物料名稱 (name) 進行追溯"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. 找出受波及的批號庫存
        batches = BatchInventory.objects.filter(
            Q(batch_number__icontains=keyword) | Q(material__name__icontains=keyword)
        ).select_related("material")

        if not batches.exists():
            return Response(
                {"message": "找不到對應的批號或物料資訊"},
                status=status.HTTP_404_NOT_FOUND,
            )

        results = []

        for batch in batches:
            batch_num = batch.batch_number

            # ---------------------------------------------------------
            # 2. 追溯生產單與客戶流向 (向下追溯)
            # ---------------------------------------------------------
            candidate_pos = (
                ProductionOrder.objects.annotate(
                    materials_text=Cast("materials_info", output_field=CharField())
                )
                .filter(materials_text__icontains=batch_num, is_active=True)
                .select_related("product")
                .prefetch_related("delivery_notes")
            )

            orders = []

            for po in candidate_pos:
                materials = po.materials_info or []
                is_used = False
                used_qty = 0.0
                unit = ""

                # 🌟 新增：用來收集這張生產單對「這個原料」真正使用了哪些批號
                used_batch_numbers = []

                for mat in materials:
                    # 確保只針對我們正在追溯的這支原料進行統計
                    if mat.get("code") == batch.material.code:
                        mat_batches = mat.get("batches", [])
                        for b in mat_batches:
                            used_val = b.get("used", "")
                            if used_val:
                                try:
                                    val = float(used_val)
                                    if val > 0:
                                        # 只要用量 > 0，就把該批號加入陣列
                                        used_batch_numbers.append(b.get("batch_number"))

                                        # 如果剛好是這次迴圈的主角 batch_num，則加總數量與標記
                                        if b.get("batch_number") == batch_num:
                                            is_used = True
                                            used_qty += val
                                except (ValueError, TypeError):
                                    pass

                        if is_used and not unit:
                            unit = mat.get("unit", "kg")

                # 確實有使用該批號原料，才列入報表
                if is_used and used_qty > 0:
                    delivery_notes_data = []
                    for dn in po.delivery_notes.all():
                        if not dn.is_active:
                            continue

                        dn_customer = dn.customer_info or {}
                        delivery_notes_data.append(
                            {
                                "note_number": dn.note_number,
                                "note_date": dn.note_date,
                                "customer_code": dn_customer.get("code", ""),
                                "customer_name": dn_customer.get("name", ""),
                                "quantity": float(dn.quantity) if dn.quantity else 0,
                                "unit": dn.unit or "kg",
                                "spec": dn.spec or "",
                                "batch_number": dn.batch_number or "",
                            }
                        )

                    po_vendor = po.vendor_info or {}
                    orders.append(
                        {
                            "order_number": po.order_number,
                            "order_created_at": po.created_at.strftime("%Y-%m-%d"),
                            "parent_id": po.parent_id,
                            "product_code": po.product.code,
                            "product_name": po.product.name,
                            "product_spec": po.product.unit,
                            "used_qty": used_qty,
                            "unit": unit,
                            "actual_qty": float(po.actual_qty) if po.actual_qty else 0,
                            "target_qty": float(po.target_qty) if po.target_qty else 0,
                            "po_vendor_info": {
                                "code": po_vendor.get("code", ""),
                                "name": po_vendor.get("name", ""),
                                "phone": po_vendor.get("phone", ""),
                                "address": po_vendor.get("address", ""),
                            },
                            "used_batch_numbers": used_batch_numbers,  # 🌟 將收集到的批號陣列放入
                            "delivery_notes": delivery_notes_data,
                        }
                    )

            # ---------------------------------------------------------
            # 3. 追溯物料需求單 MRP
            # ---------------------------------------------------------
            candidate_mrps = MaterialRequirementPlan.objects.annotate(
                batch_text=Cast("batch_inventory_info", output_field=CharField())
            ).filter(batch_text__icontains=batch_num, is_active=True)

            mrps = []
            for mrp in candidate_mrps:
                inv_info = mrp.batch_inventory_info or []
                is_used = False
                used_qty = 0.0
                unit = ""

                # 🌟 新增：收集 MRP 中對「這個原料」預計使用的所有批號
                used_batch_numbers = []

                for mat in inv_info:
                    if mat.get("code") == batch.material.code:
                        mat_batches = mat.get("batches", [])
                        for b in mat_batches:
                            used_val = b.get("used", "")
                            if used_val:
                                try:
                                    val = float(used_val)
                                    if val > 0:
                                        used_batch_numbers.append(b.get("batch_number"))

                                        if b.get("batch_number") == batch_num:
                                            is_used = True
                                            used_qty += val
                                except (ValueError, TypeError):
                                    pass

                        if is_used and not unit:
                            unit = mat.get("unit", "kg")

                if is_used and used_qty > 0:
                    mrps.append(
                        {
                            "mrp_id": mrp.mrp_id,
                            "used_qty": used_qty,
                            "unit": unit,
                            "used_batch_numbers": used_batch_numbers,  # 🌟 將收集到的批號陣列放入
                        }
                    )

            # ---------------------------------------------------------
            # 4. 彙整結果
            # ---------------------------------------------------------
            results.append(
                {
                    "batch_id": batch.id,
                    "batch_number": batch.batch_number,
                    "material_code": batch.material.code,
                    "material_name": batch.material.name,
                    "remaining_qty": float(batch.remaining_qty),
                    "received_date": batch.received_date.strftime("%Y-%m-%d")
                    if batch.received_date
                    else None,
                    "expiration_date": batch.expiration_date.strftime("%Y-%m-%d")
                    if batch.expiration_date
                    else None,
                    "trace_details": {
                        # "mrps": mrps,
                        "orders": orders,
                    },
                }
            )

        return Response(results, status=status.HTTP_200_OK)


class BOMViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = (
        BOM.objects.filter(is_active=True)
        .select_related("parent", "child")
        .order_by("-id")
    )

    serializer_class = BOMSerializer

    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    filterset_fields = ["parent__code", "parent__type", "child__code", "child__type"]
    search_fields = ["parent__name", "parent__code", "child__name", "child__code"]

    def get_permissions(self):
        return [IsAuthenticated(), IsRDOrReadOnly()]


class PurchaseRequisitionViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    serializer_class = PurchaseRequisitionSerializer

    def get_permissions(self):
        return [IsAuthenticated()]
        # return [IsAuthenticated(), IsAdminOrEmployerOrReadOnly()]

    @action(detail=False, methods=["get"], url_path="prev_purchase_price")
    def get_latest_price(self, request):
        """
        取得特定物料的最近一次採購單價
        API Endpoint: GET /api/purchase_requisitions/prev_purchase_price?material_id=XXX
        """
        material_id = request.query_params.get("material_id")

        if not material_id:
            return Response(
                {"detail": "必須提供 material_id 參數"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        latest_item = (
            PurchaseRequisitionItem.objects.filter(
                material_id=material_id,
                is_active=True,
                purchased_price__isnull=False,
                requisition__status="stocked",
                requisition__is_active=True,
            )
            .select_related("requisition")
            .order_by("-requisition__request_date", "-id")
            .first()
        )
        if latest_item:
            return Response(
                {"latest_price": latest_item.purchased_price}, status=status.HTTP_200_OK
            )

        return Response({"latest_price": None}, status=status.HTTP_200_OK)

    def get_queryset(self):
        active_items_prefetch = Prefetch(
            "items", queryset=PurchaseRequisitionItem.objects.filter(is_active=True)
        )

        queryset = PurchaseRequisition.objects.filter(is_active=True).prefetch_related(
            active_items_prefetch
        )

        if self.action == "list":
            today = timezone.now().date()

            start_date_str = self.request.query_params.get("start_date")
            end_date_str = self.request.query_params.get("end_date")

            if start_date_str or end_date_str:
                if start_date_str:
                    try:
                        start_date = datetime.strptime(
                            start_date_str, "%Y-%m-%d"
                        ).replace(tzinfo=timezone.utc)
                        queryset = queryset.filter(request_date__gte=start_date)
                    except ValueError:
                        pass

                if end_date_str:
                    try:
                        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                        end_date = min(end_date, today)
                        queryset = queryset.filter(request_date__lte=end_date)
                    except ValueError:
                        pass

            else:
                two_weeks_ago = today - timedelta(days=365)
                queryset = queryset.filter(request_date__range=[two_weeks_ago, today])

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        items_data = serializer.validated_data.pop("items", [])
        super().perform_create(serializer)
        instance = serializer.instance

        for item_data in items_data:
            purchased_price = item_data.get("purchased_price")
            material = item_data.get("material")
            if purchased_price in [None, ""]:
                raise ValidationError(
                    {
                        "detail": f"異常資料：id={material.id}, name={material.name}, price={purchased_price}"
                    }
                )

            PurchaseRequisitionItem.objects.create(requisition=instance, **item_data)

    def perform_update(self, serializer):
        user = self.get_valid_user()
        items_data = serializer.validated_data.pop("items", None)

        super().perform_update(serializer)
        instance = serializer.instance

        if items_data is not None:
            existing_items = {
                item.id: item for item in instance.items.filter(is_active=True)
            }
            incoming_item_ids = []

            for item_data in items_data:
                item_id = item_data.get("id")

                if item_id and item_id in existing_items:
                    item_instance = existing_items[item_id]
                    self._record_db_log(
                        instance,
                        user,
                        f"{user.last_name}{user.first_name} 更新了請購明細: {item_instance.material.name}",
                    )
                    for attr, value in item_data.items():
                        setattr(item_instance, attr, value)
                    item_instance.save()
                    incoming_item_ids.append(item_instance.id)
                else:
                    item_data.pop("id", None)
                    new_item = PurchaseRequisitionItem.objects.create(
                        requisition=instance, **item_data
                    )
                    self._record_db_log(
                        instance,
                        user,
                        f"{user.last_name}{user.first_name} 新增了請購明細: {new_item.material.name}",
                    )
                    incoming_item_ids.append(new_item.id)

            for item_id, item_instance in existing_items.items():
                if item_id not in incoming_item_ids:
                    item_instance.is_active = False
                    item_instance.save(update_fields=["is_active"])
                    self._record_db_log(
                        instance,
                        user,
                        f"{user.last_name}{user.first_name} 刪除了請購明細: {item_instance.material.name}",
                    )


class DeliveryNoteFilter(filters.FilterSet):
    """
    銷貨單的進階查詢過濾器
    """

    production_order_id = filters.NumberFilter(field_name="production_order_id")
    customer_tax_id = filters.CharFilter(
        field_name="customer_info__tax_id", lookup_expr="exact"
    )
    customer_code = filters.CharFilter(
        field_name="customer_info__code", lookup_expr="exact"
    )
    customer_name = filters.CharFilter(
        field_name="customer_info__name", lookup_expr="icontains"
    )

    class Meta:
        model = DeliveryNote
        fields = ["note_number", "note_date"]


class DeliveryNoteViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = DeliveryNote.objects.filter(is_active=True).order_by("-id")
    serializer_class = DeliveryNoteSerializer

    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    filterset_class = DeliveryNoteFilter
    search_fields = ["note_number"]

    def get_permissions(self):
        return [IsAuthenticated(), IsAdminOrEmployerOrReadOnly()]

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.get_valid_user()

        today_str = timezone.localtime(timezone.now()).strftime("%Y%m%d")

        last_note = (
            DeliveryNote.objects.select_for_update()
            .filter(note_number__startswith=today_str)
            .order_by("-note_number")
            .first()
        )

        sequence = 1
        if last_note:
            sequence = int(last_note.note_number[-4:]) + 1

        new_note_number = f"{today_str}{sequence:04d}"

        instance = serializer.save(created_by=user, note_number=new_note_number)
        self._record_db_log(
            instance, user, f"{user.last_name}{user.first_name} 建立了此銷貨單"
        )


class CustomerOrderViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = CustomerOrder.objects.filter(deleted_at__isnull=True).order_by("-id")
    serializer_class = CustomerOrderSerializer

    def get_permissions(self):
        return [IsAuthenticated()]
        # return [IsAuthenticated(), IsAdminOrEmployerOrReadOnly()]

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.get_valid_user()
        instance = serializer.save(created_by=user)
        self._record_db_log(
            instance, user, f"{user.last_name}{user.first_name} 建立了客戶訂貨單"
        )

    @action(detail=False, methods=["get"])
    def daily_sequence(self, request):
        """取得今日 訂購單 流水號的下一個可用號碼"""
        today_str = timezone.localtime(timezone.now()).strftime("%Y%m%d")
        prefix = f"CO{today_str}"

        ons = CustomerOrder.objects.filter(order_number__startswith=prefix).values_list(
            "order_number", flat=True
        )

        max_seq = 0
        for oid in ons:
            suffix = oid[len(prefix) :]
            seq_str = suffix.split("-")[0]

            if seq_str.isdigit():
                max_seq = max(max_seq, int(seq_str))

        return Response({"sequence": max_seq + 1, "prefix": prefix})

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


from collections import deque

from rest_framework import viewsets
from rest_framework.decorators import action

from .models import BOM, BatchInventory, Material, ProductionOrder


def to_decimal5(value):
    """轉換為精準的五位小數 Decimal"""
    FOUR_DECIMALS = Decimal("0.00000")
    if value is None or value == "":
        return FOUR_DECIMALS
    try:
        return Decimal(str(value)).quantize(FOUR_DECIMALS, rounding=ROUND_HALF_UP)
    except (ValueError, TypeError, InvalidOperation):
        return FOUR_DECIMALS


class TraceViewSet(viewsets.ViewSet):
    """
    取得特定異常物料的回收計畫書核心指標
    """

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"])
    def recall_report(self, request):
        material_id = request.query_params.get("material_id")

        if not material_id:
            return Response(
                {"error": "必須提供 material_id"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            material = Material.objects.get(id=material_id)
        except Material.DoesNotExist:
            return Response({"error": "找不到該物料"}, status=status.HTTP_404_NOT_FOUND)

        # ---------------------------------------------------------
        # 1. 取得「尚未使用原料總量」 (異常原料在庫總量)
        # ---------------------------------------------------------
        unused_raw_agg = BatchInventory.objects.filter(
            material=material, is_active=True
        ).aggregate(total=Sum("remaining_qty"))["total"]

        used_raw_total = Decimal("0.00000")
        unused_raw_total = to_decimal5(unused_raw_agg or 0)

        total_produced_product = Decimal("0.00000")
        total_in_stock_product = Decimal("0.00000")
        total_shipped_product = Decimal("0.00000")

        # ---------------------------------------------------------
        # 2. 向上追溯 (Bottom-Up Trace) - 🚀 deque & 零 N+1 查詢
        # ---------------------------------------------------------
        tainted_material_ids = {material.id}
        queue = deque([material.id])

        while queue:
            # 批次處理：一次把同階層的 ID 彈出，用 1 次 Query 找齊母件
            current_batch = [queue.popleft() for _ in range(len(queue))]

            parent_ids = BOM.objects.filter(
                child_id__in=current_batch, is_active=True
            ).values_list("parent_id", flat=True)

            for parent_id in parent_ids:
                if parent_id not in tainted_material_ids:
                    tainted_material_ids.add(parent_id)
                    queue.append(parent_id)

        # ---------------------------------------------------------
        # 3. 抓取受污染物料家族的生產單與重量轉換係數
        # ---------------------------------------------------------
        tainted_pos = (
            ProductionOrder.objects.filter(
                product_id__in=tainted_material_ids, is_active=True
            )
            .select_related("product")
            .prefetch_related("delivery_notes")
        )

        if tainted_pos.exists():
            # ---------------------------------------------------------
            # 4. 指標計算
            # ---------------------------------------------------------
            for po in tainted_pos:
                # (A) 指標 1: 異常原料投入總量
                materials_info = (
                    po.materials_info if isinstance(po.materials_info, list) else []
                )
                for mat_info in materials_info:
                    if str(mat_info.get("code")) == material.code:
                        for b in mat_info.get("batches", []):
                            used_raw_total += to_decimal5(b.get("used", 0))

                # (B) 指標 3, 4, 5: 產品相關重量
                # 只有最終成品 (PRODUCT) 才會計入對外通報的回收產品總量
                if po.product.type == "PRODUCT":
                    product_qty_val = (
                        po.actual_qty if po.actual_qty is not None else po.target_qty
                    )
                    total_produced_product += to_decimal5(product_qty_val or 0)

                    po_remaining_batches = po.remaining_qty
                    total_in_stock_product += to_decimal5(po_remaining_batches or 0)

                    po_delivered_batches = po.active_delivered_qty
                    total_shipped_product += to_decimal5(po_delivered_batches or 0)

        # ---------------------------------------------------------
        # 5. 精度強制約束與浮點數誤差吸收
        # ---------------------------------------------------------
        used_raw_total = to_decimal5(used_raw_total)
        total_produced_product = to_decimal5(total_produced_product)
        total_in_stock_product = to_decimal5(total_in_stock_product)
        total_shipped_product = to_decimal5(total_shipped_product)

        # 【浮點數誤差吸收機制】
        total_raw = used_raw_total + unused_raw_total
        if abs(total_raw - total_raw.to_integral_value()) < Decimal("0.0005"):
            corrected_total = total_raw.to_integral_value()
            unused_raw_total = to_decimal5(corrected_total - used_raw_total)
            # 重算修正後的總量 (等同於進貨總量)
            total_raw = corrected_total

        data = {
            "material_id": material.id,
            "material_name": material.name,
            "material_code": material.code,
            # 回收原料總量 = 異常原料進貨總量(kg)
            "total_raw_recalled": to_decimal5(total_raw),
            # 尚未使用原料總量 = 異常原料在庫總量(kg)
            "unused_raw_total": unused_raw_total,
            # 以下指標已經全部轉換為公斤 (KG)
            "total_produced_product": total_produced_product,
            "total_in_stock_product": total_in_stock_product,
            "total_shipped_product": total_shipped_product,
        }

        # 將計算結果透過 Serializer 回傳給前端
        # serializer = RecallReportSerializer(data)
        # return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(data, status=status.HTTP_200_OK)


class CustomerQuotationViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = CustomerQuotation.objects.prefetch_related(
        Prefetch(
            "items",
            queryset=CustomerQuotationItem.objects.filter(
                is_active=True
            ).select_related("product"),
        ),
        "customer",
    ).order_by("-issue_date", "-id")

    serializer_class = CustomerQuotationSerializer
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    filterset_fields = ["status", "customer"]
    search_fields = ["quotation_number", "customer__name"]

    def get_permissions(self):
        return [IsAuthenticated(), IsRDOrReadOnly()]

    @transaction.atomic
    def perform_create(self, serializer):
        today_str = timezone.localtime(timezone.now()).strftime("%Y%m%d")
        last_q = (
            CustomerQuotation.objects.filter(
                quotation_number__startswith=f"Q{today_str}"
            )
            .order_by("-quotation_number")
            .first()
        )

        seq = int(last_q.quotation_number.split("-")[1]) + 1 if last_q else 1
        new_q_number = f"Q{today_str}-{seq:03d}"

        serializer.validated_data["quotation_number"] = new_q_number
        super().perform_create(serializer)

    @transaction.atomic
    def perform_update(self, serializer):
        old_status = self.get_object().status
        new_status = serializer.validated_data.get("status", old_status)

        super().perform_update(serializer)

        instance = serializer.instance
        if old_status != "CONFIRMED" and new_status == "CONFIRMED":
            self._promote_materials_to_prod(instance)

    def _promote_materials_to_prod(self, quotation):
        """推進 BOM 狀態的邏輯"""
        product_ids = [item.product_id for item in quotation.items.all()]
        if not product_ids:
            return

        materials_to_update = set()
        queue = list(product_ids)
        visited = set(product_ids)

        while queue:
            current_id = queue.pop(0)
            materials_to_update.add(current_id)

            child_boms = BOM.objects.filter(
                parent_id=current_id, is_active=True
            ).values_list("child_id", flat=True)
            for child_id in child_boms:
                if child_id not in visited:
                    visited.add(child_id)
                    queue.append(child_id)

        updated_count = Material.objects.filter(
            id__in=materials_to_update, phase="IN_DEV"
        ).update(phase="IN_PROD")

        if updated_count > 0:
            user = self.get_valid_user()
            self._record_db_log(
                quotation,
                user,
                f"系統自動動作：已將 {updated_count} 筆關聯的 IN_DEV 物料推進至 IN_PROD 狀態 單據 #{quotation}",
            )
