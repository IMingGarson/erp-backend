from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import models, transaction
from django.db.models import (
    Avg,
    CharField,
    DecimalField,
    ExpressionWrapper,
    F,
    FloatField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Cast, Coalesce, TruncMonth
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
    BatchQCRecord,
    BOMLog,
    CustomerOrder,
    CustomerOrderLog,
    CustomerQuotation,
    CustomerQuotationItem,
    CustomerQuotationLog,
    DeliveryNote,
    DeliveryNoteLog,
    Ingredient,
    Material,
    MaterialIngredient,
    MaterialLog,
    MaterialProvider,
    MaterialProviderPrice,
    MaterialProviderQuotation,
    MaterialRequirementPlan,
    MaterialRequirementPlanLog,
    MiscTransactionRecord,
    MiscTransactionRecordLog,
    PackageOrder,
    PackageOrderLog,
    PaymentRecord,
    PaymentRecordLog,
    ProductionLog,
    ProductionOrder,
    ProductProfile,
    PurchaseRequisition,
    PurchaseRequisitionItem,
    PurchaseRequisitionLog,
    Vendor,
    VendorLog,
)
from .permissions import IsAdminOrEmployerOrReadOnly, IsRDOrReadOnly
from .serializers import (
    BatchInventorySerializer,
    BatchQCRecordSerializer,
    BOMMaterialDropdownSerializer,
    BOMSerializer,
    CustomerOrderSerializer,
    CustomerQuotationSerializer,
    DeliveryNoteSerializer,
    IngredientSerializer,
    MaterialProviderQuotationSerializer,
    MaterialProviderSerializer,
    MaterialRequirementPlanSerializer,
    MaterialSerializer,
    MiscTransactionRecordSerializer,
    PackageOrderSerializer,
    PaymentRecordSerializer,
    ProductionOrderSerializer,
    ProductProfileSerializer,
    PurchaseRequisitionSerializer,
    VendorSerializer,
)
from .services import TFDALoopUpService, UtilsFuncService


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
        MiscTransactionRecord: (MiscTransactionRecordLog, "transaction_record"),
        PaymentRecord: (PaymentRecordLog, "payment_record"),
        PackageOrder: (PackageOrderLog, "package_order"),
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

        elif model_name == "PackageOrder":
            action_detail = f"{full_username} 建立了包裝單 #{instance.order_number}"

        else:
            action_detail = f"{full_username} 建立了此筆資料 (ID: {instance.pk})"

        self._record_db_log(instance, user, action_detail)

    def perform_update(self, serializer):
        user = self.get_valid_user()
        old_instance = serializer.instance
        full_username = f"{user.last_name}{user.first_name}"

        changes = []
        for field_name, new_val in serializer.validated_data.items():
            if field_name in ["updated_at", "updated_by", "created_at", "created_by"]:
                continue

            try:
                field = old_instance._meta.get_field(field_name)
                old_val = getattr(old_instance, field_name)
                verbose_name = getattr(field, "verbose_name", field_name)

                if isinstance(field, models.JSONField) or isinstance(
                    old_val, (dict, list)
                ):
                    json_diffs = self.get_json_diff(old_val or {}, new_val or {})
                    if json_diffs:
                        for diff in json_diffs:
                            changes.append(
                                f"修改 ID {old_instance.pk} 的 {verbose_name}，{diff}"
                            )
                    continue

                if old_val != new_val:
                    old_display = self._get_field_display_value(
                        old_instance, field, old_val
                    )
                    new_display = self._get_field_display_value(
                        old_instance, field, new_val
                    )

                    changes.append(
                        f"修改 ID {old_instance.pk} 的 {verbose_name}，把 '{old_display}' 改成 '{new_display}'"
                    )
            except Exception:
                pass

        save_kwargs = {}
        if hasattr(serializer.Meta.model, "updated_by"):
            save_kwargs["updated_by"] = user

        instance = serializer.save(**save_kwargs)

        if changes:
            action_detail = f"{full_username} " + "；".join(changes)
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

        elif model_name == "PackageOrder":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            action_detail = f"{full_username} 刪除了包裝單 #{instance.order_number}"

        elif model_name == "CustomerQuotation":
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            instance.items.update(is_active=False)
            action_detail = f"{full_username} 刪除了報價單 #{instance.quotation_number}"

        else:
            action_detail = f"{full_username} 停用此筆資料 (ID: {instance.pk})"

        if user and action_detail:
            self._record_db_log(instance, user, action_detail)

    # 🌟 修正：移除遞迴 Path 的追蹤，只比對值的變化
    def get_json_diff(self, old_obj, new_obj):
        local_changes = []

        if isinstance(old_obj, dict) and isinstance(new_obj, dict):
            all_keys = set(old_obj.keys()).union(set(new_obj.keys()))
            for k in all_keys:
                if k not in old_obj:
                    local_changes.append(f"新增了 '{new_obj[k]}'")
                elif k not in new_obj:
                    local_changes.append(f"移除了 '{old_obj[k]}'")
                else:
                    local_changes.extend(self.get_json_diff(old_obj[k], new_obj[k]))

        elif isinstance(old_obj, list) and isinstance(new_obj, list):
            max_len = max(len(old_obj), len(new_obj))
            for i in range(max_len):
                if i >= len(old_obj):
                    local_changes.append(f"新增了 '{new_obj[i]}'")
                elif i >= len(new_obj):
                    local_changes.append(f"移除了 '{old_obj[i]}'")
                else:
                    local_changes.extend(self.get_json_diff(old_obj[i], new_obj[i]))

        else:
            # 只有當值真的不同時才記錄，避免紀錄空的字串與 None 等價的變化
            if str(old_obj or "") != str(new_obj or ""):
                local_changes.append(f"把 '{old_obj}' 改成 '{new_obj}'")

        return local_changes


class ProductionOrderViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = ProductionOrder.objects.filter(is_active=True).order_by("-created_at")
    serializer_class = ProductionOrderSerializer

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=True, methods=["post"], url_path="replace_batch")
    @transaction.atomic
    def replace_batch(self, request, pk=None):
        """
        替換生產單與 MRP 中的原物料批號
        並依據新舊使用量歸還與扣除庫存 (使用 select_for_update 避免 Race Condition)
        包含嚴謹的 Try-Except 與 Rollback 機制。
        """
        user = self.get_valid_user()
        po = self.get_object()

        material_code = request.data.get("material_code")
        old_batch_number = request.data.get("old_batch_number")
        new_batch_number = request.data.get("new_batch_number")

        try:
            old_used_qty = Decimal(str(request.data.get("old_used_qty", 0)))
            new_used_qty = Decimal(str(request.data.get("new_used_qty", 0)))
        except (InvalidOperation, ValueError, TypeError):
            return Response(
                {"error": "數量格式錯誤"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not all([material_code, old_batch_number, new_batch_number]):
            return Response(
                {"error": "缺少必要參數"}, status=status.HTTP_400_BAD_REQUEST
            )

        if old_batch_number == new_batch_number:
            return Response(
                {"error": "新舊批號相同，無需替換"}, status=status.HTTP_400_BAD_REQUEST
            )

        if old_used_qty < 0 or new_used_qty <= 0:
            return Response(
                {"error": "替換的新使用量必須大於零"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 1. 鎖定舊批號與新批號庫存
            try:
                old_batch = BatchInventory.objects.select_for_update().get(
                    batch_number=old_batch_number,
                    material__code=material_code,
                    is_active=True,
                )
            except BatchInventory.DoesNotExist:
                return Response(
                    {"error": f"找不到舊批號庫存: {old_batch_number}"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            try:
                new_batch = BatchInventory.objects.select_for_update().get(
                    batch_number=new_batch_number,
                    material__code=material_code,
                    is_active=True,
                )
            except BatchInventory.DoesNotExist:
                return Response(
                    {"error": f"找不到新批號庫存: {new_batch_number}"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # 2. 驗證新批號的庫存是否足夠扣除
            if new_batch.remaining_qty < new_used_qty:
                return Response(
                    {
                        "error": f"新批號 {new_batch_number} 庫存不足 (當前剩餘: {new_batch.remaining_qty})"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 3. 執行庫存增減
            old_batch.remaining_qty += old_used_qty
            new_batch.remaining_qty -= new_used_qty

            old_batch.save(update_fields=["remaining_qty"])
            new_batch.save(update_fields=["remaining_qty"])

            # 4. 安全重建 JSON 陣列邏輯 (避免 remove 造成的重複或跳號)
            def update_json_materials(materials_list):
                for mat in materials_list:
                    if mat.get("code") == material_code:
                        batches = mat.get("batches", [])

                        # 確認新批號是否已經在清單內
                        exists_new = any(
                            b.get("batch_number") == new_batch_number for b in batches
                        )
                        updated_batches = []

                        for b in batches:
                            current_b_num = b.get("batch_number")

                            if current_b_num == old_batch_number:
                                if exists_new:
                                    # 情況 A: 新批號已在列表中，直接拋棄這個舊批號的節點 (合併效果)
                                    pass
                                else:
                                    # 情況 B: 新批號不在列表中，將舊批號節點原址更新為新批號
                                    b["id"] = new_batch.id
                                    b["batch_number"] = new_batch.batch_number
                                    b["used"] = str(new_used_qty)
                                    b["available"] = float(new_batch.remaining_qty)
                                    b["received_date"] = (
                                        new_batch.received_date.strftime("%Y-%m-%d")
                                        if new_batch.received_date
                                        else None
                                    )
                                    updated_batches.append(b)

                            elif current_b_num == new_batch_number:
                                # 累加到已存在的新批號節點上
                                curr_used = Decimal(
                                    str(b.get("used", "0")).strip() or "0"
                                )
                                b["used"] = str(curr_used + new_used_qty)
                                b["available"] = float(new_batch.remaining_qty)
                                b["received_date"] = (
                                    new_batch.received_date.strftime("%Y-%m-%d")
                                    if new_batch.received_date
                                    else None
                                )
                                updated_batches.append(b)

                            else:
                                # 其他無關的批號，原封不動保留
                                updated_batches.append(b)

                        mat["batches"] = updated_batches

            # 5. 更新 ProductionOrder 的 materials_info JSON
            po_materials = po.materials_info or []
            update_json_materials(po_materials)
            po.materials_info = po_materials
            po.save(update_fields=["materials_info"])

            # 6. 同步更新關聯的 MRP JSON
            try:
                mrp = MaterialRequirementPlan.objects.get(
                    mrp_id=po.order_number, is_active=True
                )
                mrp_info = mrp.batch_inventory_info or []
                update_json_materials(mrp_info)
                mrp.batch_inventory_info = mrp_info
                mrp.save(update_fields=["batch_inventory_info"])
                self._record_db_log(
                    mrp,
                    user,
                    f"{user.last_name}{user.first_name} 同步更新了 MRP {mrp.mrp_id} 的批號分配",
                )
            except MaterialRequirementPlan.DoesNotExist:
                pass

            # 7. 寫入生產單修改日誌
            self._record_db_log(
                po,
                user,
                f"{user.last_name}{user.first_name} 替換了生產單 {po.order_number} 內物料 [{material_code}] 的批號，將 {old_batch_number} (用量 {old_used_qty}) 替換為 {new_batch_number} (用量 {new_used_qty})",
            )

            return Response(
                {"message": "批號替換與庫存更新成功"}, status=status.HTTP_200_OK
            )

        except Exception as e:
            # 發生任何未預期的 Error，強制觸發 Rollback，確保庫存不被錯誤寫入
            transaction.set_rollback(True)
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Replace batch API failed: {e!s}")
            return Response(
                {"error": f"系統發生未預期錯誤，已自動還原庫存 ({e!s})"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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
                | models.Q(product__code__icontains=search_keyword)
            )

        product_keyword = request.query_params.get("product")
        if product_keyword:
            queryset = queryset.filter(
                models.Q(product__name__icontains=product_keyword)
                | models.Q(product__code__icontains=product_keyword)
            )

        vendor_keyword = request.query_params.get("vendor")
        if vendor_keyword:
            queryset = queryset.filter(vendor_info__name__icontains=vendor_keyword)

        parent_id = request.query_params.get("parent_id")
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)

        is_root = request.query_params.get("is_root")
        if is_root == "true":
            queryset = queryset.filter(models.Q(parent_id__isnull=True))

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                    tzinfo=UTC,
                )

                queryset = queryset.filter(created_at__gte=start_date)
            except ValueError:
                pass

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
                    hour=23,
                    minute=59,
                    second=59,
                    microsecond=999999,
                    tzinfo=UTC,
                )

                queryset = queryset.filter(created_at__lte=end_date)
            except ValueError:
                pass
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
            prefix = f"{instance.order_number}-"
            children = (
                self.get_queryset()
                .filter(order_number__startswith=prefix)
                .order_by("created_at")
            )

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
            # 🌟 防禦性處理：相容 Frontend 傳來的 Object 或 Array
            batch_info_raw = mrp_data.get("batch_inventory_info", [])
            if isinstance(batch_info_raw, dict):
                batch_info = list(batch_info_raw.values())
            else:
                batch_info = batch_info_raw

            if not batch_info:
                return False

            mrp_id = mrp_data.get("id")
            product_id = mrp_data.get("productId")
            qty = mrp_data.get("qty")

            # 🌟 修正：qty 有可能是 0，所以不能只用 truthy 判斷，需明確檢查 is not None
            if not mrp_id or not product_id or qty is None:
                return False

            new_mrp = MaterialRequirementPlan.objects.create(
                mrp_id=mrp_id,
                parent_id=parent_id,
                vendor_info=v_info_json,
                batch_inventory_info=batch_info,
                product_id=product_id,
                required_qty=qty,
                created_by=user,
            )

            created_mrps.append(
                {
                    "id": new_mrp.id,
                    "parent_id": parent_id,
                    "product_id": product_id,
                }
            )
            self._record_db_log(
                new_mrp, user, f"{user.last_name}{user.first_name} 建立此需求單草稿"
            )

            children = mrp_data.get("children_mrp", [])
            for child in children:
                save_mrp_recursive(child, parent_id=mrp_id)

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

        # 🌟 直接從 Frontend payload 接收精確的包裝、規格與報價單資訊
        outer_pack_id = request.data.get("outer_pack_id")
        inner_pack_id = request.data.get("inner_pack_id")
        spec = request.data.get("spec", "")
        sales_unit = request.data.get("sales_unit", "")
        sales_pack_unit = request.data.get("sales_pack_unit", "")
        quotation_id = request.data.get("quotation_id")

        if not mrp_id:
            return Response({"error": "Invalid ID"})

        # 1. 撈出母單
        try:
            parent_mrp = self.get_queryset().get(
                id=mrp_id, status=MaterialRequirementPlan.STATUS_CHOICES[0][0]
            )
        except MaterialRequirementPlan.DoesNotExist:
            return Response(
                {"error": "找不到此 MRP 母單"}, status=status.HTTP_404_NOT_FOUND
            )

        # 2. 遞迴撈出對應的所有層級子單
        children_mrps = []
        current_parent_ids = [parent_mrp.mrp_id]

        while current_parent_ids:
            layer_children = list(
                MaterialRequirementPlan.objects.filter(
                    parent_id__in=current_parent_ids,
                    status=MaterialRequirementPlan.STATUS_CHOICES[0][0],
                )
            )
            if not layer_children:
                break

            children_mrps.extend(layer_children)
            current_parent_ids = [c.mrp_id for c in layer_children]

        all_mrps = [parent_mrp] + children_mrps

        # 3. 檢查並真實扣除庫存
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
                        raise ValidationError(
                            f"庫存不足！批次 {batch.get('batch_number')} 僅剩 {inventory.remaining_qty}，但需要扣除 {used_qty}"
                        )

                    inventory.remaining_qty -= used_qty
                    inventory.save(update_fields=["remaining_qty"])

        def _generate_qc_metrics(product):
            standards = getattr(product, "qc_standards", [])
            if not standards:
                return []
            metrics = []
            for std in standards:
                metric = dict(std)
                metric.update(
                    {
                        "actual_value_num": None,
                        "actual_value_text": None,
                        "is_passed": None,
                        "remark": "",
                    }
                )
                metrics.append(metric)
            return metrics

        def _smart_sort_key(item):
            seq = item.get("sequence_num")
            seq_str = str(seq).strip() if seq is not None else ""
            req_qty = float(item.get("requiredQty", 0))

            if seq_str:
                return (0, seq_str, -req_qty)
            else:
                return (1, "", -req_qty)

        created_pos = []
        mrp_to_po_map = {}

        children_by_parent = {}
        for child in children_mrps:
            if child.parent_id not in children_by_parent:
                children_by_parent[child.parent_id] = []
            children_by_parent[child.parent_id].append(child)

        other_materials = sorted(parent_mrp.batch_inventory_info, key=_smart_sort_key)

        # 🌟 將 Frontend 傳入的包裝資訊與報價單ID，直接寫入生產單 vendor_info 以供後續查找
        parent_vendor_info = (
            parent_mrp.vendor_info.copy() if parent_mrp.vendor_info else {}
        )
        if outer_pack_id is not None:
            parent_vendor_info["outer_pack_id"] = outer_pack_id
        if inner_pack_id is not None:
            parent_vendor_info["inner_pack_id"] = inner_pack_id
        if spec:
            parent_vendor_info["spec"] = spec
        if sales_unit:
            parent_vendor_info["sales_unit"] = sales_unit
        if sales_pack_unit:
            parent_vendor_info["sales_pack_unit"] = sales_pack_unit
        if quotation_id is not None:
            parent_vendor_info["quotation_id"] = quotation_id

        parent_po = ProductionOrder.objects.create(
            order_number=parent_mrp.mrp_id,
            product=parent_mrp.product,
            target_qty=parent_mrp.required_qty,
            materials_info=other_materials,
            vendor_info=parent_vendor_info,
            qc_metrics=_generate_qc_metrics(parent_mrp.product),
            created_by=user,
        )
        created_pos.append(parent_po)
        mrp_to_po_map[parent_mrp.mrp_id] = parent_po

        def create_child_pos(current_mrp_id, current_po):
            if current_mrp_id not in children_by_parent:
                return

            layer_children = sorted(
                children_by_parent[current_mrp_id], key=lambda x: x.created_at
            )

            child_po_infos = []

            for child_mrp in layer_children:
                # 🌟 1. 捨棄 global_suffix，直接沿用 MRP 的精準流水號，確保單號完全對齊
                new_order_number = child_mrp.mrp_id

                child_product_code = getattr(child_mrp.product, "code", "")

                semi_seq = ""
                for m in current_po.materials_info:
                    if m.get("code") == child_product_code and m.get("type") == "SEMI":
                        semi_seq = m.get("sequence_num", "")
                        break

                # 🌟 2. 判斷此子單是否為「包裝作業節點」 (依據我們寫入的 is_pack 標籤)
                is_packaging = False
                if isinstance(child_mrp.batch_inventory_info, list):
                    for info in child_mrp.batch_inventory_info:
                        if info.get("is_pack") in [1, "1", True]:
                            is_packaging = True
                            break

                sorted_materials = sorted(
                    child_mrp.batch_inventory_info, key=_smart_sort_key
                )

                child_po = ProductionOrder.objects.create(
                    order_number=new_order_number,
                    parent_id=current_po.order_number,
                    product=child_mrp.product,
                    target_qty=child_mrp.required_qty,
                    materials_info=sorted_materials,
                    vendor_info=child_mrp.vendor_info,
                    qc_metrics=_generate_qc_metrics(child_mrp.product),
                    created_by=user,
                )
                mrp_to_po_map[child_mrp.mrp_id] = child_po
                created_pos.append(child_po)

                # 🌟 3. 在母單中加入這層子單的追蹤資訊，若為包裝單則換上專屬的標示
                display_type = "PACKAGING" if is_packaging else "CHILD_PRODUCT"
                display_name = (
                    f"{child_mrp.product.name} (包裝作業)"
                    if is_packaging
                    else child_mrp.product.name
                )

                child_po_infos.append(
                    {
                        "type": display_type,
                        "code": child_product_code,
                        "unit": getattr(child_mrp.product, "unit", ""),
                        "materialName": display_name,
                        "requiredQty": float(child_mrp.required_qty),
                        "isShortage": False,
                        "child_order_number": new_order_number,
                        "batches": [],
                        "sequence_num": semi_seq,
                    }
                )

                create_child_pos(child_mrp.mrp_id, child_po)

            current_po.materials_info = sorted(
                current_po.materials_info + child_po_infos, key=_smart_sort_key
            )
            current_po.save(update_fields=["materials_info"])

        create_child_pos(parent_mrp.mrp_id, parent_po)

        for mrp in all_mrps:
            mrp.status = MaterialRequirementPlan.STATUS_CHOICES[1][0]
            mrp.save(update_fields=["status"])

        return Response(
            {
                "message": "成功轉為生產單並完成扣庫",
                "created_production_orders": [po.order_number for po in created_pos],
            },
            status=status.HTTP_200_OK,
        )


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class MaterialFilter(filters.FilterSet):
    type__in = CharInFilter(field_name="type", lookup_expr="in")
    type = filters.CharFilter(field_name="type", lookup_expr="exact")

    class Meta:
        model = Material
        fields = ["code", "type", "phase", "is_active"]


class MaterialViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    serializer_class = MaterialSerializer
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]

    filterset_class = MaterialFilter
    search_fields = ["name", "code", "english_name"]

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.query_params.get("lite") == "true":
            return BOMMaterialDropdownSerializer
        return MaterialSerializer

    @action(detail=False, methods=["get"], url_path="tfda_lookup")
    def tfda_lookup(self, request):
        search_term = request.query_params.get("q", "").strip()
        if not search_term:
            return Response(
                {"message": "error", "error": "請提供搜尋關鍵字 (參數: q)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            results = TFDALoopUpService.import_tfda_open_data(search_term)
            return Response(results, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"message": "error", "data": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"])
    def historical_prices(self, request, pk=None):
        material = self.get_object()

        # ==========================================
        # 情況一：RAW 與 PACK (回傳明細，供前端畫圖與切換供應商)
        # ==========================================
        if material.type in ["RAW", "PACK"]:
            items = (
                PurchaseRequisitionItem.objects.filter(
                    material=material,
                    is_active=True,
                    requisition__is_active=True,
                    requisition__status="stocked",
                )
                .select_related("requisition", "material_provider")
                .order_by("requisition__request_date")
            )

            data = [
                {
                    "date": item.requisition.request_date.strftime("%Y-%m-%d"),
                    "unit_price": float(item.purchased_price),  # 模型定義的「採購單價」
                    "quantity": float(item.quantity),  # 購買數量
                    "total_price": float(
                        item.purchased_price * item.quantity
                    ),  # 總金額由後端算好
                    "provider": item.material_provider.name
                    if item.material_provider
                    else "未知供應商",
                }
                for item in items
            ]
            return Response({"type": material.type, "data": data})

        # ==========================================
        # 情況二：SEMI 與 PRODUCT (後端處理 BOM 展開與月份斷層 LOCF)
        # ==========================================
        elif material.type in ["SEMI", "PRODUCT"]:
            boms = material.main_product.filter(is_active=True)
            if not boms.exists():
                return Response({"type": material.type, "data": []})

            base_qty = float(boms.first().base_quantity)
            components_history = {}
            all_months = set()

            # 1. 收集每個子物料的「歷史月平均單價」
            for bom in boms:
                child = bom.child
                req_ratio = float(bom.quantity_required) / base_qty

                monthly_avg = (
                    PurchaseRequisitionItem.objects.filter(
                        material=child,
                        is_active=True,
                        requisition__is_active=True,
                        requisition__status="stocked",
                    )
                    .annotate(month=TruncMonth("requisition__request_date"))
                    .values("month")
                    .annotate(avg_price=Avg("purchased_price"))
                    .order_by("month")
                )

                history_map = {
                    m["month"].strftime("%Y-%m"): float(m["avg_price"])
                    for m in monthly_avg
                    if m["month"]
                }
                components_history[child.id] = {
                    "name": child.name,  # 🌟 紀錄子物料名稱供前端顯示
                    "ratio": req_ratio,
                    "history": history_map,
                    "fallback_price": float(child.estimated_cost),
                }
                all_months.update(history_map.keys())

            # 2. 處理「月份斷層」並加總當月 BOM 總成本與成本結構
            sorted_months = sorted(all_months)
            data = []

            last_known_price = {
                child_id: info["fallback_price"]
                for child_id, info in components_history.items()
            }

            for month_str in sorted_months:
                total_monthly_cost = 0
                breakdown = []  # 🌟 準備存放該月的成本細項

                for child_id, info in components_history.items():
                    if month_str in info["history"]:
                        last_known_price[child_id] = info["history"][month_str]

                    # 該物料當月貢獻的成本
                    cost_contribution = last_known_price[child_id] * info["ratio"]
                    total_monthly_cost += cost_contribution

                    # 🌟 寫入 breakdown
                    breakdown.append(
                        {"name": info["name"], "cost": round(cost_contribution, 2)}
                    )

                # 依成本佔比由高到低排序，讓前端顯示更直觀
                breakdown = sorted(breakdown, key=lambda x: x["cost"], reverse=True)

                data.append(
                    {
                        "month": month_str,
                        "unit_price": round(total_monthly_cost, 2),
                        "breakdown": breakdown,  # 🌟 傳給前端
                    }
                )

            return Response({"type": material.type, "data": data})

    def _get_historical_base_cost(self, material):
        """輔助函數：計算不受最新報價影響的歷史純採購成本"""

        three_months_ago = timezone.now().date() - timedelta(days=90)
        recent_purchases = PurchaseRequisitionItem.objects.filter(
            material=material,
            is_active=True,
            requisition__is_active=True,
            requisition__status="stocked",
            requisition__request_date__gte=three_months_ago,
        )
        aggregates = recent_purchases.aggregate(
            total_qty=Sum("quantity"),
            total_val=Sum(
                ExpressionWrapper(
                    F("quantity") * F("purchased_price"), output_field=DecimalField()
                )
            ),
        )
        if aggregates.get("total_qty") and aggregates.get("total_val"):
            return float(round(aggregates["total_val"] / aggregates["total_qty"], 4))

        latest = (
            PurchaseRequisitionItem.objects.filter(
                material=material,
                is_active=True,
                requisition__is_active=True,
                requisition__status="stocked",
            )
            .order_by("-requisition__request_date", "-id")
            .first()
        )
        return float(latest.purchased_price) if latest else 0.0

    @action(detail=False, methods=["get"], url_path="active_alerts")
    def active_alerts(self, request):
        """主動預警：抓出有漲跌幅的原料，確保同原料的多家供應商都能獨立顯示"""
        today = timezone.now().date()

        active_prices = (
            MaterialProviderPrice.objects.filter(
                is_active=True,
                quotation__is_active=True,
            )
            .filter(
                Q(quotation__valid_until__gte=today)
                | Q(quotation__valid_until__isnull=True)
            )
            .select_related("material", "quotation", "quotation__provider")
            .order_by("-quotation__effective_date", "-id")
        )

        checked_quotes = {}
        for p in active_prices:
            m_id = p.material.id
            prov_id = p.quotation.provider_id if p.quotation else 0
            key = (m_id, prov_id)

            if key not in checked_quotes:
                new_price = float(p.price) if p.price else 0.0
                old_price = (
                    float(p.material.estimated_cost)
                    if p.material.estimated_cost
                    else 0.0
                )
                diff = new_price - old_price

                checked_quotes[key] = {
                    "material": p.material,
                    "new_price": new_price,
                    "old_price": old_price,
                    "diff_percent": round((diff / old_price * 100), 1)
                    if old_price > 0
                    else 0,
                    "provider_name": p.quotation.provider.name
                    if p.quotation.provider
                    else "未知廠商",
                    "effective_date": p.quotation.effective_date,
                }

        def find_parent_ids(curr_mat, ids_set):
            parent_boms = curr_mat.sub_material.filter(is_active=True).values_list(
                "parent_id", flat=True
            )
            for pid in parent_boms:
                if pid not in ids_set:
                    ids_set.add(pid)
                    parent_obj = Material.objects.filter(id=pid).first()
                    if parent_obj:
                        find_parent_ids(parent_obj, ids_set)

        alerts = []
        for key, info in checked_quotes.items():
            material = info["material"]
            affected_product_ids = set()

            find_parent_ids(material, affected_product_ids)

            if affected_product_ids and info["new_price"] != info["old_price"]:
                q_count = (
                    CustomerQuotationItem.objects.filter(
                        product_id__in=affected_product_ids,
                        is_active=True,
                        quotation__is_active=True,
                    )
                    .values("quotation_id")
                    .distinct()
                    .count()
                )

                alerts.append(
                    {
                        "material_id": material.id,
                        "material_code": material.code,
                        "material_name": material.name,
                        "material_type": material.type,
                        "old_price": info["old_price"],
                        "new_price": info["new_price"],
                        "diff_percent": info["diff_percent"],
                        "provider_name": info["provider_name"],
                        "effective_date": info["effective_date"],
                        "affected_products_count": len(affected_product_ids),
                        "affected_quotations_count": q_count,
                    }
                )

        return Response(alerts)

    @action(detail=True, methods=["get"])
    def impact_analysis(self, request, pk=None):
        """詳細追溯分析：並精準抓出該原料在各別 BOM 階層中的實際成本狀況"""
        material = self.get_object()
        today = timezone.now().date()

        global_estimated_cost = (
            float(material.estimated_cost) if material.estimated_cost else 0.0
        )

        active_prices = (
            material.provider_prices.filter(is_active=True, quotation__is_active=True)
            .filter(
                Q(quotation__valid_until__gte=today)
                | Q(quotation__valid_until__isnull=True)
            )
            .select_related("quotation", "quotation__provider")
            .order_by("quotation__provider_id", "-quotation__effective_date", "-id")
        )

        provider_quotes_map = {}
        for pq in active_prices:
            pid = pq.quotation.provider_id
            if pid not in provider_quotes_map:
                new_price = float(pq.price) if pq.price else 0.0
                price_diff = new_price - global_estimated_cost
                diff_percent = (
                    round((price_diff / global_estimated_cost * 100), 2)
                    if global_estimated_cost > 0
                    else 0
                )
                provider_quotes_map[pid] = {
                    "id": pq.id,
                    "provider_id": pid,
                    "provider_name": pq.quotation.provider.name
                    if pq.quotation.provider
                    else "未知廠商",
                    "new_price": new_price,
                    "price_diff": price_diff,
                    "diff_percent": diff_percent,
                    "effective_date": pq.quotation.effective_date.strftime("%Y-%m-%d"),
                }
        provider_quotes = sorted(
            provider_quotes_map.values(), key=lambda x: x["new_price"]
        )

        affected_products_map = {}

        def find_parents(current_material, current_ratio, chain, target_cost_info=None):
            parent_boms = current_material.sub_material.filter(
                is_active=True
            ).select_related("parent", "selected_price", "selected_price__quotation")

            for bom in parent_boms:
                parent_mat = bom.parent
                req = float(bom.quantity_required)
                base = float(bom.base_quantity)
                step_ratio = req / base if base > 0 else 0
                accumulated_ratio = current_ratio * step_ratio

                if target_cost_info is None:
                    cost = 0.0
                    c_type = "NO_DATA"
                    q_id = None
                    is_expired = False

                    if bom.set_cost is not None:
                        cost = float(bom.set_cost)
                        c_type = "SET_COST"
                        q_id = None
                    elif bom.selected_price:
                        q = bom.selected_price.quotation
                        if q and q.valid_until and q.valid_until < today:
                            is_expired = True
                            cost = (
                                float(current_material.estimated_cost)
                                if current_material.estimated_cost
                                else 0.0
                            )
                            c_type = "EXPIRED_PRICE"
                        else:
                            cost = float(bom.selected_price.price)
                            c_type = "SELECTED_PRICE"
                            q_id = bom.selected_price.id
                    elif current_material.estimated_cost:
                        cost = float(current_material.estimated_cost)
                        c_type = "ESTIMATED"
                    else:
                        cost = 0.0
                        c_type = "NO_DATA"

                    step_target_info = {
                        "current_cost": cost,
                        "cost_type": c_type,
                        "bound_quote_id": q_id,
                        "is_expired": is_expired,
                    }
                else:
                    step_target_info = target_cost_info

                # 🌟 將 current_material 的屬性獨立抓出，方便前端取用
                new_chain = chain + [
                    {
                        "code": current_material.code,
                        "name": current_material.name,
                        "req": req,
                        "base": base,
                        "step_ratio": step_ratio,
                    }
                ]

                if parent_mat.id not in affected_products_map:
                    affected_products_map[parent_mat.id] = {
                        "obj": parent_mat,
                        "accumulated_ratio": 0.0,
                        "paths": [],
                    }

                affected_products_map[parent_mat.id]["accumulated_ratio"] += (
                    accumulated_ratio
                )

                is_direct = len(new_chain) == 1
                if is_direct:
                    text = f"直接添加：基準 {base:g} KG 內含 {req:g} KG ({step_ratio * 100:.2f}%)"
                else:
                    text = f"透過「{new_chain[-1]['name']}」帶入：基準 {base:g} KG 內含 {req:g} KG，換算佔比 {accumulated_ratio * 100:.2f}%"

                # 🌟 傳入 step_code, step_name 以及 is_direct 供前端 Stack UI 使用
                affected_products_map[parent_mat.id]["paths"].append(
                    {
                        "text": text,
                        "step_code": new_chain[-1]["code"],
                        "step_name": new_chain[-1]["name"],
                        "is_direct": is_direct,
                        "ratio": accumulated_ratio,
                        "target_cost_info": step_target_info,
                    }
                )

                find_parents(parent_mat, accumulated_ratio, new_chain, step_target_info)

        find_parents(material, 1.0, [])

        product_details = []
        for pid, data in affected_products_map.items():
            parent_mat = data["obj"]

            # 🌟 強制將 is_direct (直投成品原料) 排序在最上面第一列
            sorted_paths = sorted(
                data["paths"], key=lambda x: 0 if x["is_direct"] else 1
            )

            product_details.append(
                {
                    "id": parent_mat.id,
                    "code": parent_mat.code,
                    "name": parent_mat.name,
                    "type": parent_mat.type,
                    "accumulated_ratio": data["accumulated_ratio"],
                    "paths": sorted_paths,
                }
            )

        affected_quotations = []
        if affected_products_map:
            try:
                quotation_items = CustomerQuotationItem.objects.filter(
                    product_id__in=list(affected_products_map.keys()),
                    is_active=True,
                    quotation__is_active=True,
                ).select_related("quotation", "quotation__customer", "product")

                quotation_map = {}
                for item in quotation_items:
                    q_id = item.quotation.id
                    if q_id not in quotation_map:
                        quotation_map[q_id] = {
                            "quotation_id": q_id,
                            "quotation_number": item.quotation.quotation_number,
                            "customer_name": item.quotation.customer.name
                            if item.quotation.customer
                            else "未知客戶",
                            "date": item.quotation.created_at.strftime("%Y-%m-%d"),
                            "affected_items": [],
                        }
                    quotation_map[q_id]["affected_items"].append(
                        {
                            "product_id": item.product.id,
                            "product_code": item.product.code,
                            "product_name": item.product.name,
                            "pricing_multiplier": float(item.pricing_multiplier)
                            if item.pricing_multiplier
                            else 1.000,
                            "accumulated_ratio": affected_products_map[item.product.id][
                                "accumulated_ratio"
                            ],
                        }
                    )
                affected_quotations = list(quotation_map.values())
            except Exception as e:
                print(f"Quotation query error: {e}")

        return Response(
            {
                "material_base_cost": global_estimated_cost,
                "provider_quotes": provider_quotes,
                "affected_products": product_details,
                "affected_quotations": sorted(
                    affected_quotations, key=lambda x: x["date"], reverse=True
                ),
            }
        )

    def get_queryset(self):
        queryset = Material.objects.filter(is_active=True).order_by("-id")
        user = self.request.user

        is_rd = (
            user.is_authenticated
            and hasattr(user, "profile")
            and user.profile.department.upper() == "RD"
        )
        if not is_rd:
            queryset = queryset.filter(phase="IN_PROD")

        is_list = self.action == "list"
        is_lite = self.request.query_params.get("lite") == "true"

        # 不管是普通列表還是輕量下拉選單，都需要算預估成本
        if is_list or is_lite:
            today = timezone.now().date()
            three_months_ago = today - timedelta(days=90)

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

            active_ingredients_prefetch = Prefetch(
                "material_ingredients",
                queryset=MaterialIngredient.objects.filter(
                    is_active=True
                ).select_related("ingredient"),
            )

            if is_lite:
                queryset = queryset.prefetch_related(
                    active_ingredients_prefetch,
                    Prefetch("main_product__child", queryset=annotated_material_qs),
                    Prefetch(
                        "main_product__child__main_product__child",
                        queryset=annotated_material_qs,
                    ),
                )
            else:
                queryset = queryset.prefetch_related(
                    "product_profiles",
                    active_ingredients_prefetch,
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

    @action(detail=True, methods=["get"], url_path="historical_records")
    def historical_records(self, request, pk=None):
        """取得指定客戶的歷史訂購與出貨紀錄"""
        vendor = self.get_object()

        # 1. 抓取下單但未出貨之客戶訂單 (Customer Orders)
        # 🌟 補上 mrp 關聯查詢
        co_qs = (
            CustomerOrder.objects.filter(
                deleted_at__isnull=True, customer_info__code=vendor.code
            )
            .select_related("product", "mrp")
            .order_by("-order_date")
        )

        # 2. 抓取已出貨之銷貨單 (Delivery Notes)
        # 🌟 確保 production_order 有被 prefetch
        dn_qs = (
            DeliveryNote.objects.filter(is_active=True, customer_info__code=vendor.code)
            .select_related("production_order__product")
            .order_by("-note_date")
        )

        # 3. 取得目前生效的包裝單 (PackageOrder) 以供對照包裝單號
        active_pack_orders = PackageOrder.objects.filter(is_active=True).values(
            "product_id", "order_number"
        )
        pack_order_map = {
            po["product_id"]: po["order_number"] for po in active_pack_orders
        }

        history = []

        for co in co_qs:
            prod_id = co.product.id if co.product else None
            pack_order_num = pack_order_map.get(prod_id, "-") if prod_id else "-"

            # 🌟 替換為未來的生產單號 (MRP ID)
            po_number = co.mrp.mrp_id if co.mrp else co.order_number

            history.append(
                {
                    "type": "ORDER",
                    "date": co.order_date.strftime("%Y-%m-%d") if co.order_date else "",
                    "number": po_number,
                    "product_id": prod_id,
                    "product_name": co.product.name if co.product else "",
                    "product_code": co.product.code if co.product else "",
                    "package_order_number": pack_order_num,
                    "spec": co.spec,
                    "quantity": float(co.quantity) if co.quantity else 0,
                    "unit": co.unit,
                    "price": float(co.unit_price) if co.unit_price else 0,
                }
            )

        for dn in dn_qs:
            prod = (
                dn.production_order.product
                if dn.production_order and dn.production_order.product
                else None
            )
            prod_id = prod.id if prod else None
            pack_order_num = pack_order_map.get(prod_id, "-") if prod_id else "-"

            # 🌟 替換為實際關聯的生產單號
            po_number = (
                dn.production_order.order_number
                if dn.production_order
                else dn.note_number
            )

            history.append(
                {
                    "type": "DELIVERY",
                    "date": dn.note_date.strftime("%Y-%m-%d") if dn.note_date else "",
                    "number": po_number,
                    "product_id": prod_id,
                    "product_name": prod.name if prod else "",
                    "product_code": prod.code if prod else "",
                    "package_order_number": pack_order_num,
                    "spec": dn.spec,
                    "quantity": float(dn.quantity) if dn.quantity else 0,
                    "unit": dn.unit,
                    "price": float(dn.sales_price) if dn.sales_price else 0,
                }
            )

        # 依日期降冪排序 (由新到舊)
        history.sort(key=lambda x: x["date"], reverse=True)

        return Response(history, status=status.HTTP_200_OK)


class MaterialProviderViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = MaterialProvider.objects.filter(is_active=True).order_by("-id")
    serializer_class = MaterialProviderSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsRDOrReadOnly()]


class BatchInventoryViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = BatchInventory.objects.filter(is_active=True).order_by("-id")
    serializer_class = BatchInventorySerializer

    def get_permissions(self):
        # return [IsAuthenticated(), IsAdminOrEmployerOrReadOnly()]
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"], url_path="replaceable_batches")
    def replaceable_batches(self, request):
        """
        取得特定物料可用來替換的批號清單
        需傳入 material_id，並可選傳入 required_qty 以過濾庫存足夠的批號，
        並可用 exclude_batch 排除目前正在使用的批號
        """
        material_id = request.query_params.get("material_id")
        required_qty = request.query_params.get("required_qty", 0)
        exclude_batch = request.query_params.get("exclude_batch")

        if not material_id:
            return Response(
                {"error": "必須提供 material_id 參數"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            req_qty_val = Decimal(str(required_qty))
        except InvalidOperation:
            req_qty_val = Decimal(0)

        queryset = self.get_queryset().filter(
            material_id=material_id, remaining_qty__gte=req_qty_val, remaining_qty__gt=0
        )

        if exclude_batch:
            queryset = queryset.exclude(batch_number=exclude_batch)

        queryset = queryset.order_by("received_date", "id")

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
                        "mrps": mrps,
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

    @transaction.atomic
    def perform_destroy(self, instance):
        parent_mat = instance.parent
        super().perform_destroy(instance)

        if parent_mat:
            parent_mat.recalculate_from_ingredients()

    @action(detail=False, methods=["get"], url_path="mapping")
    def mapping(self, request):
        import math

        # 1. 取得 PRODUCT 到 SEMI 的對應表
        package_orders = PackageOrder.objects.filter(is_active=True).values(
            "product_id", "semi_material_id"
        )
        product_to_semi = {
            str(po["product_id"]): str(po["semi_material_id"])
            for po in package_orders
            if po["product_id"]
        }

        # 2. 拉出所有物料的 Annotated 成本
        today = timezone.now().date()
        three_months_ago = today - timedelta(days=90)

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

        # 抓出所有有效物料，並預先載入第一層 BOM
        all_materials = (
            Material.objects.filter(is_active=True)
            .annotate(annotated_estimated_cost=cost_annotation)
            .prefetch_related("main_product")
        )

        # 建立快查字典
        mat_dict = {m.id: m for m in all_materials}
        cost_cache = {}

        # 🌟 記憶體級別的精準成本計算，徹底消滅 N+1
        def calculate_cost_in_memory(mat_id):
            if mat_id in cost_cache:
                return cost_cache[mat_id]

            mat = mat_dict.get(mat_id)
            if not mat:
                return 0

            if mat.type == "PRODUCT":
                semi_id = product_to_semi.get(str(mat.id))
                if semi_id:
                    cost = calculate_cost_in_memory(int(semi_id))
                    cost_cache[mat.id] = math.ceil(cost)
                    return cost_cache[mat.id]
                cost_cache[mat.id] = 0
                return 0

            if mat.type == "SEMI":
                boms = [bom for bom in mat.main_product.all() if bom.is_active]
                if not boms:
                    cost_cache[mat.id] = 0
                    return 0

                total_cost = sum(
                    calculate_cost_in_memory(bom.child_id)
                    * float(bom.quantity_required)
                    for bom in boms
                )
                base_qty = float(boms[0].base_quantity)
                cost = math.ceil(total_cost / base_qty) if base_qty > 0 else 0
                cost_cache[mat.id] = cost
                return cost

            # RAW / PACK: 無條件進位
            raw_cost = math.ceil(getattr(mat, "annotated_estimated_cost", 0) or 0)
            cost_cache[mat.id] = raw_cost
            return raw_cost

        # 遞迴展開所有配方
        def get_expanded_boms(mat_id, current_ratio=1.0):
            results = []
            mat = mat_dict.get(mat_id)
            if not mat:
                return results

            for bom in mat.main_product.all():
                if not bom.is_active:
                    continue

                child = mat_dict.get(bom.child_id)
                if not child:
                    continue

                base_qty = float(bom.base_quantity) if bom.base_quantity else 1.0
                req_qty = float(bom.quantity_required) if bom.quantity_required else 0.0

                step_ratio = (req_qty / base_qty) if base_qty > 0 else 0
                acc_ratio = current_ratio * step_ratio

                if child.type == "SEMI":
                    results.extend(get_expanded_boms(child.id, acc_ratio))
                elif child.type not in ["PACK", "STICKER", "OTHER", "PRODUCT"]:
                    # 取得這支原料算完無條件進位的單位成本
                    raw_cost = calculate_cost_in_memory(child.id)
                    results.append(
                        {
                            "childCode": child.code,
                            "childName": child.name,
                            "childUnit": child.unit,
                            "cost": raw_cost,
                            "qty": acc_ratio,
                            "total_cost": raw_cost
                            * acc_ratio,  # 前端無腦加總用的精準浮點數
                        }
                    )
            return results

        # 3. 生成 SEMI 到 展開後 BOMs 的字典
        semi_to_boms = {}
        for mat_id, mat in mat_dict.items():
            if mat.type == "SEMI":
                raw_items = get_expanded_boms(mat_id, 1.0)

                # 合併相同的原料
                merged = {}
                for item in raw_items:
                    code = item["childCode"]
                    if code in merged:
                        merged[code]["qty"] += item["qty"]
                        merged[code]["total_cost"] += item["total_cost"]
                    else:
                        merged[code] = item.copy()

                semi_to_boms[str(mat_id)] = list(merged.values())

        return Response(
            {"product_to_semi": product_to_semi, "semi_to_boms": semi_to_boms},
            status=status.HTTP_200_OK,
        )


class PurchaseRequisitionViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    serializer_class = PurchaseRequisitionSerializer

    def get_permissions(self):
        return [IsAuthenticated()]
        # return [IsAuthenticated(), IsAdminOrEmployerOrReadOnly()]

    @action(detail=False, methods=["get"], url_path="prev_purchase_price")
    def get_latest_price(self, request):
        material_id = request.query_params.get("material_id")
        provider_id = request.query_params.get("provider_id")

        if not material_id:
            raise ValidationError("必須提供 material_id 參數")

        today = timezone.now().date()

        stock_agg = BatchInventory.objects.filter(
            material_id=material_id, is_active=True, remaining_qty__gt=0
        ).aggregate(total_stock=Sum("remaining_qty"))
        current_stock = stock_agg["total_stock"] or 0.0

        price_query = MaterialProviderPrice.objects.filter(
            material_id=material_id,
            is_active=True,
            quotation__is_active=True,
            quotation__effective_date__lte=today,
        ).order_by("-quotation__effective_date", "-id")

        if provider_id:
            price_query = price_query.filter(quotation__provider_id=provider_id)

        latest_provider_price = price_query.first()
        PROVIDER_QUOTATION = None
        if latest_provider_price:
            PROVIDER_QUOTATION = {
                "latest_price": latest_provider_price.price,
                "latest_spec": latest_provider_price.spec_text or "",
                "latest_aux_unit": latest_provider_price.aux_unit or "",
                "latest_aux_quantity": latest_provider_price.aux_quantity or "",
                "is_tax_included": latest_provider_price.quotation.is_tax_included,
                "current_stock": current_stock,
                "quote_date": latest_provider_price.quotation.quote_date,
                "valid_until": latest_provider_price.quotation.valid_until,
                "source": "PROVIDER",
            }

        item_query = PurchaseRequisitionItem.objects.filter(
            material_id=material_id,
            is_active=True,
            purchased_price__isnull=False,
            requisition__status="stocked",
            requisition__is_active=True,
        ).select_related("requisition")

        if provider_id:
            item_query = item_query.filter(material_provider_id=provider_id)

        latest_item = item_query.order_by("-requisition__request_date", "-id").first()

        latest_batch = (
            BatchInventory.objects.filter(material_id=material_id, is_active=True)
            .order_by("-received_date", "-id")
            .first()
        )

        latest_spec = getattr(latest_batch, "in_stock_spec", None) or getattr(
            latest_item, "in_stock_spec", ""
        )
        latest_aux_unit = getattr(latest_batch, "aux_unit", None) or getattr(
            latest_item, "aux_unit", ""
        )
        latest_aux_qty = getattr(latest_batch, "aux_quantity", None) or getattr(
            latest_item, "aux_quantity", ""
        )

        HISTORICAL_PR_DATA = {
            "latest_price": latest_item.purchased_price if latest_item else None,
            "latest_spec": latest_spec,
            "latest_aux_unit": latest_aux_unit,
            "latest_aux_quantity": latest_aux_qty,
            "current_stock": current_stock,
            "quote_date": None,
            "valid_until": None,
            "is_tax_included": True,
            "source": "HISTORY",
        }

        return Response(
            {
                "from_provider": PROVIDER_QUOTATION,
                "from_historical_pr": HISTORICAL_PR_DATA,
            },
            status=status.HTTP_200_OK,
        )

    def _create_batches_from_incoming_data(
        self, instance, user, items_data, existing_items
    ):
        today = timezone.now().date()
        date_str = today.strftime("%Y%m%d")

        for item_data in items_data:
            item_id = item_data.get("id")
            pr_item = existing_items.get(item_id)
            if not pr_item:
                continue

            material = pr_item.material

            # 1. 計算該 Material 在今天的最大流水號
            existing_batches = BatchInventory.objects.filter(
                material=material, batch_number__startswith=date_str
            ).values_list("batch_number", flat=True)

            max_seq = 0
            for b_num in existing_batches:
                try:
                    seq = int(b_num.replace(date_str, ""))
                    max_seq = max(max_seq, seq)
                except ValueError:
                    continue

            new_batch_number = f"{date_str}{max_seq + 1:03d}"

            # 2. 建立批號，使用 payload 傳來的「真實驗收資料」，並綁定 source_pr_item
            BatchInventory.objects.create(
                material=material,
                batch_number=new_batch_number,
                original_qty=item_data.get("quantity", pr_item.quantity),
                remaining_qty=item_data.get("quantity", pr_item.quantity),
                received_date=today,
                in_stock_spec=item_data.get("in_stock_spec", pr_item.in_stock_spec),
                package_qty=item_data.get("package_qty", pr_item.package_qty),
                aux_unit=item_data.get("aux_unit", pr_item.aux_unit),
                aux_quantity=item_data.get("aux_quantity", pr_item.aux_quantity),
                note=item_data.get("remark", pr_item.remark),
                created_by=user,
                source_pr_item=pr_item,  # 🌟 重點綁定
            )

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

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.get_valid_user()
        items_data = serializer.validated_data.pop("items", [])

        super().perform_create(serializer)
        instance = serializer.instance

        existing_items = {}
        for item_data in items_data:
            new_item = PurchaseRequisitionItem.objects.create(
                requisition=instance, **item_data
            )
            existing_items[new_item.id] = new_item
            item_data["id"] = new_item.id

        if instance.status == "stocked":
            self._create_batches_from_incoming_data(
                instance, user, items_data, existing_items
            )
            self._record_db_log(
                instance,
                user,
                f"{user.last_name}{user.first_name} 建立已入庫請購單，並自動產生批號",
            )

    @transaction.atomic
    def perform_update(self, serializer):
        user = self.get_valid_user()
        items_data = serializer.validated_data.pop("items", None)

        old_status = serializer.instance.status
        new_status = serializer.validated_data.get("status", old_status)

        super().perform_update(serializer)
        instance = serializer.instance

        if items_data is not None:
            existing_items = {
                item.id: item for item in instance.items.filter(is_active=True)
            }
            incoming_item_ids = []

            if old_status == "waiting" and new_status == "stocked":
                # 若是入庫動作，不做 PR 更新，拿真實填寫的 payload 去建立 Batch
                self._create_batches_from_incoming_data(
                    instance, user, items_data, existing_items
                )
                self._record_db_log(
                    instance,
                    user,
                    f"{user.last_name}{user.first_name} 將單據轉為已入庫，自動產生對應批號",
                )
                for item_data in items_data:
                    if item_data.get("id"):
                        incoming_item_ids.append(item_data.get("id"))
            else:
                for item_data in items_data:
                    item_id = item_data.get("id")
                    if item_id and item_id in existing_items:
                        item_instance = existing_items[item_id]
                        for attr, value in item_data.items():
                            setattr(item_instance, attr, value)
                        item_instance.save()
                        incoming_item_ids.append(item_instance.id)
                    else:
                        item_data.pop("id", None)
                        new_item = PurchaseRequisitionItem.objects.create(
                            requisition=instance, **item_data
                        )
                        incoming_item_ids.append(new_item.id)

            for item_id, item_instance in existing_items.items():
                if item_id not in incoming_item_ids:
                    item_instance.is_active = False
                    item_instance.save(update_fields=["is_active"])


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
        unused_raw_total = UtilsFuncService.to_decimal5(unused_raw_agg or 0)

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
                            used_raw_total += UtilsFuncService.to_decimal5(
                                b.get("used", 0)
                            )

                # (B) 指標 3, 4, 5: 產品相關重量
                # 只有最終成品 (PRODUCT) 才會計入對外通報的回收產品總量
                if po.product.type == "PRODUCT":
                    product_qty_val = (
                        po.actual_qty if po.actual_qty is not None else po.target_qty
                    )
                    total_produced_product += UtilsFuncService.to_decimal5(
                        product_qty_val or 0
                    )

                    po_remaining_batches = po.remaining_qty
                    total_in_stock_product += UtilsFuncService.to_decimal5(
                        po_remaining_batches or 0
                    )

                    po_delivered_batches = po.active_delivered_qty
                    total_shipped_product += UtilsFuncService.to_decimal5(
                        po_delivered_batches or 0
                    )

        # ---------------------------------------------------------
        # 5. 精度強制約束與浮點數誤差吸收
        # ---------------------------------------------------------
        used_raw_total = UtilsFuncService.to_decimal5(used_raw_total)
        total_produced_product = UtilsFuncService.to_decimal5(total_produced_product)
        total_in_stock_product = UtilsFuncService.to_decimal5(total_in_stock_product)
        total_shipped_product = UtilsFuncService.to_decimal5(total_shipped_product)

        # 【浮點數誤差吸收機制】
        total_raw = used_raw_total + unused_raw_total
        if abs(total_raw - total_raw.to_integral_value()) < Decimal("0.0005"):
            corrected_total = total_raw.to_integral_value()
            unused_raw_total = UtilsFuncService.to_decimal5(
                corrected_total - used_raw_total
            )
            # 重算修正後的總量 (等同於進貨總量)
            total_raw = corrected_total

        data = {
            "material_id": material.id,
            "material_name": material.name,
            "material_code": material.code,
            # 回收原料總量 = 異常原料進貨總量(kg)
            "total_raw_recalled": UtilsFuncService.to_decimal5(total_raw),
            # 尚未使用原料總量 = 異常原料在庫總量(kg)
            "unused_raw_total": unused_raw_total,
            # 以下指標已經全部轉換為公斤 (KG)
            "total_produced_product": total_produced_product,
            "total_in_stock_product": total_in_stock_product,
            "total_shipped_product": total_shipped_product,
        }

        return Response(data, status=status.HTTP_200_OK)


class CustomerQuotationViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = (
        CustomerQuotation.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch(
                "items",
                queryset=CustomerQuotationItem.objects.filter(
                    is_active=True
                ).select_related("product"),
            ),
            "customer",
        )
        .order_by("-issue_date", "-id")
    )

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


class ProductProfileViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = (
        ProductProfile.objects.select_related(
            "material", "outer_pack", "inner_pack", "vendor"
        )
        .filter(is_active=True)
        .order_by("-id")
    )

    serializer_class = ProductProfileSerializer

    def get_permissions(self):
        return [IsAuthenticated()]


class MaterialProviderQuotationViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    serializer_class = MaterialProviderQuotationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            MaterialProviderQuotation.objects.filter(is_active=True)
            .select_related("provider")
            .prefetch_related("items")
        )

        provider_id = self.request.query_params.get("provider_id")
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)

        return queryset.order_by("-effective_date", "-id")

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.get_valid_user()
        items_data = serializer.validated_data.pop("items", [])
        instance = serializer.save(created_by=user)

        for item_data in items_data:
            MaterialProviderPrice.objects.create(quotation=instance, **item_data)

        self._record_db_log(instance, user, f"新增了 {instance.provider.name} 的報價單")

    @transaction.atomic
    def perform_update(self, serializer):
        user = self.get_valid_user()
        items_data = serializer.validated_data.pop("items", None)
        instance = serializer.save()

        if items_data is not None:
            existing_items = {
                item.id: item for item in instance.items.filter(is_active=True)
            }
            incoming_ids = []

            for item_data in items_data:
                item_id = item_data.get("id")
                if item_id and item_id in existing_items:
                    item_instance = existing_items[item_id]
                    for attr, val in item_data.items():
                        setattr(item_instance, attr, val)
                    item_instance.save()
                    incoming_ids.append(item_instance.id)
                else:
                    item_data.pop("id", None)
                    new_item = MaterialProviderPrice.objects.create(
                        quotation=instance, **item_data
                    )
                    incoming_ids.append(new_item.id)

            for item_id, item_instance in existing_items.items():
                if item_id not in incoming_ids:
                    item_instance.is_active = False
                    item_instance.save(update_fields=["is_active"])

        self._record_db_log(instance, user, f"更新了 {instance.provider.name} 的報價單")


class BatchQCRecordViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    serializer_class = BatchQCRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 預先 select_related，避免 N+1 Query 問題
        queryset = (
            BatchQCRecord.objects.filter(is_active=True)
            .select_related("batch", "material", "inspector")
            .order_by("-test_date", "-id")
        )

        # ==========================================
        # 支援多維度檢索 (對應查核人員的需求)
        # ==========================================
        material_id = self.request.query_params.get("material_id")
        batch_id = self.request.query_params.get("batch_id")
        batch_number = self.request.query_params.get("batch_number")
        is_passed = self.request.query_params.get("is_passed")
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")

        if material_id:
            queryset = queryset.filter(material_id=material_id)

        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)

        if batch_number:
            # 支援模糊搜尋批號 (因應客訴時通常只提供部分批號字串)
            queryset = queryset.filter(batch__batch_number__icontains=batch_number)

        if is_passed is not None:
            is_passed_bool = str(is_passed).lower() in ["true", "1", "t", "y", "yes"]
            queryset = queryset.filter(is_passed=is_passed_bool)

        if start_date:
            queryset = queryset.filter(test_date__gte=start_date)

        if end_date:
            queryset = queryset.filter(test_date__lte=end_date)

        return queryset

    def perform_create(self, serializer):
        user = self.get_valid_user()

        batch = serializer.validated_data.get("batch")
        material = serializer.validated_data.get("material")

        if batch and not material:
            serializer.validated_data["material"] = batch.material

        instance = serializer.save(inspector=user)
        self._record_db_log(
            instance,
            user,
            f"{user.last_name}{user.first_name} 新增了批號 {instance.batch.batch_number} 的品管檢驗紀錄",
        )

    def perform_update(self, serializer):
        user = self.get_valid_user()
        instance = serializer.save()
        self._record_db_log(
            instance,
            user,
            f"{user.last_name}{user.first_name} 更新了批號 {instance.batch.batch_number} 的品管檢驗紀錄",
        )

    def perform_destroy(self, instance):
        user = self.get_valid_user()
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        self._record_db_log(
            instance,
            user,
            f"{user.last_name}{user.first_name} 移除了批號 {instance.batch.batch_number} 的品管檢驗紀錄",
        )


class IngredientViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    serializer_class = IngredientSerializer
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    search_fields = ["name", "tfda_code"]

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_queryset(self):
        return Ingredient.objects.all().order_by("-id")

    def perform_create(self, serializer):
        user = self.get_valid_user()
        instance = serializer.save(created_by=user)
        self._sync_to_raw_material(instance, user)

    def perform_update(self, serializer):
        user = self.get_valid_user()
        super().perform_update(serializer)
        instance = serializer.instance
        self._sync_to_raw_material(instance, user)

    def _sync_to_raw_material(self, ingredient, user):
        """
        當成分 (Ingredient) 帶有 source_material 且為 RAW 時，
        自動將營養標示、過敏原寫回該物料，並建立成分綁定，以共享添加物屬性。
        """
        mat = ingredient.source_material

        # 若沒有來源物料，或來源不是 RAW，則不需要雙向寫回
        if not mat or mat.type != "RAW":
            return

        is_updated = False

        # 1. 同步營養標示與法定過敏原
        if mat.nutrition_fact != ingredient.nutrition_fact:
            mat.nutrition_fact = ingredient.nutrition_fact
            is_updated = True

        if mat.allergen_info != ingredient.allergen_info:
            mat.allergen_info = ingredient.allergen_info
            is_updated = True

        if is_updated:
            mat.save(update_fields=["nutrition_fact", "allergen_info"])
            self._record_db_log(
                mat,
                user,
                f"系統自動動作：因關聯成分「{ingredient.name}」被設定，自動同步其營養標示與過敏原",
            )

        # 2. 自動綁定此 Ingredient，讓 RAW 物料完美繼承法定添加物屬性
        if not MaterialIngredient.objects.filter(
            material=mat, ingredient=ingredient, is_active=True
        ).exists():
            MaterialIngredient.objects.create(
                material=mat, ingredient=ingredient, is_active=True
            )
            self._record_db_log(
                mat,
                user,
                f"系統自動動作：自動綁定關聯成分「{ingredient.name}」以共享其法定添加物屬性",
            )


class AccountingReportViewSet(viewsets.ViewSet):
    """
    會計報表專用 ViewSet (階段一：動態計算應收/應付帳款)
    不更動資料庫，純依賴現有 DeliveryNote 與 PurchaseRequisitionItem 動態計算
    """

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"])
    def accumulated_debt(self, request):
        """
        取得各客戶的「累積欠額」
        公式：該客戶歷史總應收 (DeliveryNote) - 該客戶歷史總已收 (PaymentRecord)
        """
        from django.db.models import Sum

        customers = Vendor.objects.filter(is_deleted=False)
        debt_list = []

        for customer in customers:
            # 1. 歷史總應收 (從所有銷貨單加總)
            total_ar = (
                DeliveryNote.objects.filter(
                    is_active=True, customer_info__code=customer.code
                ).aggregate(total=Sum("grand_total"))["total"]
                or 0
            )

            # 2. 歷史總已收 (從金流表加總)
            total_paid = (
                PaymentRecord.objects.filter(
                    is_active=True, partner_type="CUSTOMER", customer=customer
                ).aggregate(total=Sum("amount"))["total"]
                or 0
            )

            # 3. 算出累積欠額
            debt = float(total_ar) - float(total_paid)

            # 若欠款大於 0 才回傳 (可依需求改為全傳)
            if debt > 0:
                debt_list.append(
                    {
                        "customer_id": customer.id,
                        "customer_name": customer.name,
                        "customer_code": customer.code,
                        "total_ar": float(total_ar),
                        "total_paid": float(total_paid),
                        "accumulated_debt": debt,
                    }
                )

        # 依照欠款金額由高到低排序
        debt_list = sorted(debt_list, key=lambda x: x["accumulated_debt"], reverse=True)
        return Response(debt_list, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def ar_report(self, request):
        """
        應收帳款 (Accounts Receivable) 對帳查詢
        以 DeliveryNote (銷貨單) 為基礎，依據時間區間動態加總。
        """
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        customer_code = request.query_params.get(
            "customer_code"
        )  # 可選：依客戶代號過濾

        queryset = DeliveryNote.objects.filter(is_active=True).order_by("note_date")

        if start_date:
            queryset = queryset.filter(note_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(note_date__lte=end_date)
        if customer_code:
            queryset = queryset.filter(customer_info__code=customer_code)

        # 依客戶分組加總 (因為 customer_info 是 JSON，在 Python 端做 Grouping 最穩定)
        ar_data = {}
        for note in queryset:
            c_code = note.customer_info.get("code", "UNKNOWN")
            c_name = note.customer_info.get("name", "未知名稱")

            if c_code not in ar_data:
                ar_data[c_code] = {
                    "customer_code": c_code,
                    "customer_name": c_name,
                    "total_sales_amount": 0.0,
                    "total_tax_amount": 0.0,
                    "grand_total": 0.0,
                    "delivery_notes": [],
                }

            # 加總單筆金額
            total_amt = float(note.total_amount or 0)
            tax_amt = float(note.tax_amount or 0)
            grand_total = float(note.grand_total or 0)

            ar_data[c_code]["total_sales_amount"] += total_amt
            ar_data[c_code]["total_tax_amount"] += tax_amt
            ar_data[c_code]["grand_total"] += grand_total

            # 將單據明細一併附上，讓前端對帳單有明細可查
            ar_data[c_code]["delivery_notes"].append(
                {
                    "id": note.id,
                    "note_number": note.note_number,
                    "note_date": note.note_date,
                    "total_amount": total_amt,
                    "tax_amount": tax_amt,
                    "grand_total": grand_total,
                }
            )

        # 回傳時將 dict 轉為 list
        return Response(list(ar_data.values()), status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def ap_report(self, request):
        """
        應付帳款 (Accounts Payable) 對帳查詢
        以 PurchaseRequisitionItem (已入庫請購單) 為基礎，依據時間區間動態加總。
        """
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        provider_id = request.query_params.get("provider_id")  # 可選：依供應商過濾

        # 只抓已入庫且有效的請購單明細
        queryset = (
            PurchaseRequisitionItem.objects.filter(
                is_active=True,
                requisition__status="stocked",
                requisition__is_active=True,
            )
            .select_related("material_provider", "material", "requisition")
            .order_by("requisition__request_date")
        )

        if start_date:
            queryset = queryset.filter(requisition__request_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(requisition__request_date__lte=end_date)
        if provider_id:
            queryset = queryset.filter(material_provider_id=provider_id)

        ap_data = {}
        for item in queryset:
            p_id = item.material_provider.id if item.material_provider else "UNKNOWN"
            p_name = (
                item.material_provider.name if item.material_provider else "未知廠商"
            )

            if p_id not in ap_data:
                ap_data[p_id] = {
                    "provider_id": p_id,
                    "provider_name": p_name,
                    "grand_total": 0.0,
                    "items": [],
                }

            # 應付金額 = 實際數量 * 採購單價
            qty = float(item.quantity or 0)
            price = float(item.purchased_price or 0)
            item_total = qty * price

            ap_data[p_id]["grand_total"] += item_total

            ap_data[p_id]["items"].append(
                {
                    "item_id": item.id,
                    "requisition_id": item.requisition.id,
                    "request_date": item.requisition.request_date,
                    "material_name": item.material.name,
                    "quantity": qty,
                    "purchased_price": price,
                    "item_total": item_total,
                    "remark": item.remark or "",
                }
            )

        return Response(list(ap_data.values()), status=status.HTTP_200_OK)


class MiscTransactionRecordViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    """管理公司雜支、零用金提領紀錄"""

    queryset = MiscTransactionRecord.objects.filter(is_active=True).order_by(
        "-transaction_date", "-id"
    )
    serializer_class = MiscTransactionRecordSerializer

    def get_permissions(self):
        return [IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if start_date:
            queryset = queryset.filter(transaction_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(transaction_date__lte=end_date)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class PaymentRecordViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    """管理客戶收款與廠商付款、支票紀錄"""

    queryset = PaymentRecord.objects.filter(is_active=True).order_by(
        "-payment_date", "-id"
    )
    serializer_class = PaymentRecordSerializer

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"])
    def pending_checks(self, request):
        """取得尚未兌現的支票列表"""
        # 利用 Django 的 JSONField 查詢語法
        checks = self.get_queryset().filter(
            payment_method="CHECK", check_info__is_cleared=False
        )
        serializer = self.get_serializer(checks, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def clear_check(self, request, pk=None):
        """將支票標記為已兌現"""
        record = self.get_object()
        if record.payment_method != "CHECK":
            return Response(
                {"error": "此紀錄並非支票"}, status=status.HTTP_400_BAD_REQUEST
            )

        check_info = record.check_info or {}
        check_info["is_cleared"] = True
        record.check_info = check_info
        record.save(update_fields=["check_info"])

        user = self.get_valid_user()
        self._record_db_log(
            record, user, f"{user.last_name}{user.first_name} 將此支票標記為已兌現"
        )

        return Response({"message": "支票已成功兌現"}, status=status.HTTP_200_OK)


class PackageOrderViewSet(CRUDAuditMixin, viewsets.ModelViewSet):
    queryset = (
        PackageOrder.objects.filter(is_active=True)
        .select_related("product", "semi_material")
        .order_by("-id")
    )
    serializer_class = PackageOrderSerializer
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    search_fields = ["order_number", "product__name", "semi_material__name"]

    def get_permissions(self):
        return [IsAuthenticated()]

    @transaction.atomic
    def perform_create(self, serializer):
        try:
            user = self.get_valid_user()
            data = serializer.validated_data

            order_number = data.get("order_number")
            semi_mat = data.get("semi_material")
            product_code = data.pop("new_product_code", None)
            if not product_code:
                raise ValidationError("請輸入成品代碼")

            if Material.objects.filter(code=product_code).exists():
                raise ValidationError(f"物料代號 {product_code} 已存在")

            if PackageOrder.objects.filter(order_number=order_number).exists():
                raise ValidationError(f"包裝單號 {order_number} 已存在")

            new_product = Material.objects.create(
                code=product_code,
                name=semi_mat.name,
                type="PRODUCT",
                unit=semi_mat.unit,  # 複製 unit
                is_active=semi_mat.is_active,  # 複製 is_active
                allergen_info=semi_mat.allergen_info,  # 複製 allergen_info
                description=semi_mat.description,  # 複製 description
                english_name=semi_mat.english_name,  # 複製 english_name
                origin="台灣",  # 固定為台灣
                phase="IN_DEV",  # 預設 IN_DEV
                product_registration_no=semi_mat.product_registration_no,  # 複製產品登錄號
                storage_life=semi_mat.storage_life,  # 複製保存期限
                pack_capacity=None,  # 固定為 null
                nutrition_fact=semi_mat.nutrition_fact,  # 複製營養標示
                dietary_type=semi_mat.dietary_type,  # 複製素食類別
                storage_method=semi_mat.storage_method,  # 複製保存方式
                qc_standards=semi_mat.qc_standards,  # 複製品管標準
                created_by=user,
            )
            self._record_db_log(
                new_product,
                user,
                f"{user.last_name}{user.first_name} 透過包裝單自動建立了成品 {new_product.name}",
            )

            serializer.validated_data["product"] = new_product
            super().perform_create(serializer)
            return Response(serializer.data)

        except Exception as e:
            return Response(
                {"message": str(e), "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
