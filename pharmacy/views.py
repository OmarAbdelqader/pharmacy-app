from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.messages import get_messages
from django.utils import timezone
from django.db import models
from django.db.models import Count, Prefetch, Q, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.forms import formset_factory
from django.http import JsonResponse
from datetime import timedelta
from .decorators import login_required_custom, admin_required
from .models import Medicine, MedicineCode, Supplier, Batch, OrderHeader, OrderItem, Prescription, DispensingItem, UserProfile
from .forms import MedicineForm, SupplierForm, MedicineCodeForm, OrderHeaderForm, OrderItemForm, PrescriptionForm, DispensingItemForm, UserForm, UserProfileForm, PasswordResetForm
import json

from django.views.decorators.csrf import csrf_exempt
import logging
import sys

logger = logging.getLogger(__name__)


def get_order_item_formset(extra=1):
    return formset_factory(OrderItemForm, extra=extra, can_delete=True)


def paginate_queryset(request, queryset, per_page=20):
    paginator = Paginator(queryset, per_page)
    page = request.GET.get('page')
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return page_obj

# ─── AUTH ────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    # Do not carry failed-login or stale action messages into the dashboard.
    list(get_messages(request))
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        return render(request, 'registration/login.html', {
            'login_error': True,
            'username': username,
        })
    return render(request, 'registration/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


# ─── DASHBOARD ───────────────────────────────────────────────

@login_required_custom
def dashboard(request):
    today = timezone.now().date()
    six_months = today + timedelta(days=180)

    total_medicines = Medicine.objects.count()

    low_stock_count = Medicine.objects.filter(
        reorder_level__gt=0,
        current_stock__lte=models.F('reorder_level')
    ).count()

    expiring_soon_count = Batch.objects.filter(
        expiry_date__lte=six_months,
        expiry_date__gte=today,
        quantity_remaining__gt=0
    ).count()

    today_prescriptions = Prescription.objects.filter(
        dispensing_date=today
    ).count()

    context = {
        'today': today,
        'total_medicines': total_medicines,
        'low_stock_count': low_stock_count,
        'expiring_soon_count': expiring_soon_count,
        'today_prescriptions': today_prescriptions,
    }
    return render(request, 'dashboard.html', context)


# ─── MEDICINES ───────────────────────────────────────────────

@login_required_custom
def medicine_list(request):
    search = request.GET.get('search', '')
    category_filter = request.GET.get('category', '')

    medicines = Medicine.objects.all().order_by('id')

    if search:
        medicines = medicines.filter(
            Q(name__icontains=search) |
            Q(book_reference__icontains=search) |
            Q(category__icontains=search)
        )

    if category_filter:
        medicines = medicines.filter(category__iexact=category_filter)

    categories = Medicine.objects.exclude(category='').values_list(
        'category', flat=True
    ).distinct().order_by('category')

    page_obj = paginate_queryset(request, medicines)
    total = page_obj.paginator.count
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = query_params.urlencode()

    context = {
        'medicines': page_obj,
        'search': search,
        'category_filter': category_filter,
        'categories': categories,
        'total': total,
        'page_obj': page_obj,
        'query_string': query_string,
    }
    return render(request, 'medicines/list.html', context)


@login_required_custom
def medicine_add(request):
    if request.method == 'POST':
        form = MedicineForm(request.POST)
        if form.is_valid():
            medicine = form.save(commit=False)
            medicine.created_by = request.user
            medicine.updated_by = request.user
            medicine.save()
            messages.success(request, f'تم إضافة {medicine.name} بنجاح')
            return redirect('medicine_list')
    else:
        form = MedicineForm()
    return render(request, 'medicines/form.html', {
        'form': form,
        'title': 'إضافة صنف جديد'
    })


@login_required_custom
def medicine_edit(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    if request.method == 'POST':
        form = MedicineForm(request.POST, instance=medicine)
        if form.is_valid():
            medicine = form.save(commit=False)
            medicine.updated_by = request.user
            medicine.save()
            messages.success(request, f'تم تحديث {medicine.name} بنجاح')
            return redirect('medicine_list')
    else:
        form = MedicineForm(instance=medicine)
    return render(request, 'medicines/form.html', {
        'form': form,
        'title': f'تعديل: {medicine.name}',
        'medicine': medicine
    })


@admin_required
def medicine_delete(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    if request.method == 'POST':
        name = medicine.name
        try:
            medicine.delete()
            messages.success(request, f'تم حذف {name} بنجاح')
        except Exception:
            messages.error(request, 'لا يمكن حذف هذا الصنف لوجود بيانات مرتبطة به')
        return redirect('medicine_list')
    return render(request, 'medicines/delete.html', {'medicine': medicine})


# ─── SUPPLIERS ───────────────────────────────────────────────

@login_required_custom
def supplier_list(request):
    search = request.GET.get('search', '')
    suppliers = Supplier.objects.all().order_by('id')

    if search:
        suppliers = suppliers.filter(
            Q(name__icontains=search) |
            Q(contact_person__icontains=search) |
            Q(phone__icontains=search)
        )

    page_obj = paginate_queryset(request, suppliers)
    total = page_obj.paginator.count
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = query_params.urlencode()

    context = {
        'suppliers': page_obj,
        'search': search,
        'total': total,
        'page_obj': page_obj,
        'query_string': query_string,
    }
    return render(request, 'suppliers/list.html', context)


@login_required_custom
def supplier_add(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.created_by = request.user
            supplier.updated_by = request.user
            supplier.save()
            messages.success(request, f'تم إضافة {supplier.name} بنجاح')
            return redirect('supplier_list')
    else:
        form = SupplierForm()
    return render(request, 'suppliers/form.html', {
        'form': form,
        'title': 'إضافة مورد جديد'
    })


@login_required_custom
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.updated_by = request.user
            supplier.save()
            messages.success(request, f'تم تحديث {supplier.name} بنجاح')
            return redirect('supplier_list')
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'suppliers/form.html', {
        'form': form,
        'title': f'تعديل: {supplier.name}',
        'supplier': supplier
    })


@admin_required
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        name = supplier.name
        try:
            supplier.delete()
            messages.success(request, f'تم حذف {name} بنجاح')
        except Exception:
            messages.error(request, 'لا يمكن حذف هذا المورد لوجود بيانات مرتبطة به')
        return redirect('supplier_list')
    return render(request, 'suppliers/delete.html', {'supplier': supplier})

# ─── MEDICINE CODES ──────────────────────────────────────────

@login_required_custom
def code_list(request):
    search = request.GET.get('search', '')
    selected_medicine_id = request.GET.get('medicine', '')

    medicines = Medicine.objects.all().order_by('id')
    codes = MedicineCode.objects.none()
    selected_medicine = None

    if selected_medicine_id:
        selected_medicine = get_object_or_404(Medicine, pk=selected_medicine_id)
        codes = MedicineCode.objects.filter(medicine=selected_medicine).select_related('medicine')

    if search:
        medicines = medicines.filter(
            Q(name__icontains=search) |
            Q(codes__code__icontains=search)
        ).distinct()

        # If searching by code, auto select the medicine
        if not selected_medicine_id:
            code_match = MedicineCode.objects.filter(
                code__icontains=search
            ).first()
            if code_match:
                selected_medicine = code_match.medicine
                codes = MedicineCode.objects.filter(medicine=selected_medicine).select_related('medicine')

    page_obj = paginate_queryset(request, codes)
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = query_params.urlencode()

    context = {
        'medicines': medicines,
        'codes': page_obj,
        'selected_medicine': selected_medicine,
        'search': search,
        'page_obj': page_obj,
        'query_string': query_string,
    }
    return render(request, 'codes/list.html', context)


@login_required_custom
def code_add(request):
    medicine_id = request.GET.get('medicine', '')
    initial = {}
    if medicine_id:
        initial['medicine'] = medicine_id

    if request.method == 'POST':
        form = MedicineCodeForm(request.POST)
        if form.is_valid():
            code_value = form.cleaned_data['code']
            medicine = form.cleaned_data['medicine']

            # Check for duplicate code
            if MedicineCode.objects.filter(code=code_value).exists():
                existing = MedicineCode.objects.get(code=code_value)
                messages.error(request, f'الكود "{code_value}" مستخدم بالفعل للصنف: {existing.medicine.name}')
            else:
                code = form.save(commit=False)
                code.created_by = request.user
                code.save()
                messages.success(request, f'تم إضافة الكود "{code_value}" بنجاح')
                return redirect(f'/codes/?medicine={medicine.pk}')
    else:
        form = MedicineCodeForm(initial=initial)

    return render(request, 'codes/form.html', {
        'form': form,
        'title': 'إضافة كود جديد',
        'medicine_id': medicine_id,
    })


@login_required_custom
def code_delete(request, pk):
    code = get_object_or_404(MedicineCode, pk=pk)
    medicine_id = code.medicine.pk
    if request.method == 'POST':
        code_value = code.code
        code.delete()
        messages.success(request, f'تم حذف الكود "{code_value}" بنجاح')
        return redirect(f'/codes/?medicine={medicine_id}')
    return render(request, 'codes/delete.html', {'code': code})


# ─── PRESCRIPTIONS ───────────────────────────────────────────

@login_required_custom
def medicine_api(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    return JsonResponse({
        'reorder_level': medicine.reorder_level,
        'current_stock': medicine.current_stock,
        'suggested_qty': max(0, medicine.reorder_level - medicine.current_stock),
    })

@login_required_custom
def medicine_search_api(request):
    query = request.GET.get('q', '')
    medicines = Medicine.objects.filter(
        Q(name__icontains=query) |
        Q(codes__code__icontains=query)
    ).distinct()[:10]

    results = []
    for medicine in medicines:
        results.append({
            'id': medicine.id,
            'name': medicine.name,
            'category': medicine.category,
            'default_qty': medicine.default_dispense_qty or 1,
            'current_stock': medicine.current_stock,
        })
    return JsonResponse({'results': results})


def medicine_batches_api(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    batches = Batch.objects.filter(
        medicine=medicine,
        quantity_remaining__gt=0
    ).order_by('expiry_date')

    results = []
    for batch in batches:
        results.append({
            'id': batch.id,
            'batch_number': batch.batch_number,
            'expiry_date': str(batch.expiry_date),
            'quantity_remaining': batch.quantity_remaining,
        })
    return JsonResponse({'batches': results, 'medicine_name': medicine.name})

@login_required_custom
def prescription_list(request):
    search = request.GET.get('search', '')
    date_filter = request.GET.get('date', '')

    prescriptions = Prescription.objects.select_related('created_by').annotate(
        item_count=Count('items')
    ).order_by('-dispensing_date', '-id')

    if search:
        prescriptions = prescriptions.filter(
            prescription_ref__icontains=search
        )

    if date_filter:
        prescriptions = prescriptions.filter(dispensing_date=date_filter)

    page_obj = paginate_queryset(request, prescriptions)
    total = page_obj.paginator.count
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = query_params.urlencode()

    context = {
        'prescriptions': page_obj,
        'search': search,
        'date_filter': date_filter,
        'total': total,
        'today': timezone.now().date(),
        'page_obj': page_obj,
        'query_string': query_string,
    }
    return render(request, 'prescriptions/list.html', context)


@login_required_custom
def prescription_add(request):
    today = timezone.now().date()
    last_prefix = request.GET.get('prefix', '')
    DispensingItemFormSet = formset_factory(DispensingItemForm, extra=1, can_delete=True)

    if request.method == 'POST':
        form = PrescriptionForm(request.POST)
        formset = DispensingItemFormSet(request.POST, prefix='items')

        if form.is_valid():
            ref = form.cleaned_data.get('prescription_ref') or (
                form.cleaned_data.get('prefix_digits', '') +
                form.cleaned_data.get('suffix_digits', '')
            )

            medicine_ids = request.POST.getlist('item_medicine[]')
            
            if not medicine_ids:
                messages.error(request, 'يجب إضافة صنف واحد على الأقل قبل حفظ التذكرة')
            elif Prescription.objects.filter(prescription_ref=ref).exists():
                messages.error(request, f'رقم التذكرة "{ref}" مستخدم بالفعل')
            else:
                prescription = form.save(commit=False)
                prescription.prescription_ref = ref
                prescription.created_by = request.user
                prescription.updated_by = request.user
                prescription.save()

                ok = _process_dispensing_items(request, prescription)
                if not ok:
                    prescription.delete()
                else:
                    messages.success(request, f'تم حفظ التذكرة {prescription.prescription_ref} بنجاح')
                    prefix = form.cleaned_data.get('prefix_digits', '')
                    return redirect(f'/prescriptions/add/?prefix={prefix}')
    else:
        form = PrescriptionForm(initial={
            'dispensing_date': today,
            'prefix_digits': last_prefix,
        })
        formset = DispensingItemFormSet(prefix='items')

    return render(request, 'prescriptions/form.html', {
        'form': form,
        'formset': formset,
        'title': 'إضافة تذكرة جديدة',
        'today': today,
        'last_prefix': last_prefix,
        'medicines_json': _get_medicines_json(),
    })


@login_required_custom
def prescription_edit(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)

    if request.method == 'POST':
        form = PrescriptionForm(request.POST, instance=prescription)
        if form.is_valid():
            prescription_ref = form.cleaned_data['prescription_ref']

            if Prescription.objects.filter(
                prescription_ref=prescription_ref
            ).exclude(pk=pk).exists():
                messages.error(request, f'رقم التذكرة {prescription_ref} مستخدم بالفعل')
            else:
                # Snapshot existing items BEFORE any mutation
                existing_items_snapshot = list(prescription.items.select_related(
                    'medicine', 'batch'
                ).all())

                # 1. VALIDATE NEW ITEMS FIRST — zero DB side effects
                parsed, errors = _validate_dispensing_items(
                    request, prescription_snapshot=existing_items_snapshot
                )
                if errors:
                    # Validation failed: re-render form, PRESERVE existing prescription
                    return render(request, 'prescriptions/form.html', {
                        'form': form,
                        'title': f'تعديل التذكرة: {prescription_ref}',
                        'prescription': prescription,
                        'existing_items': existing_items_snapshot,
                        'medicines_json': _get_medicines_json(),
                    })

                # 2. Validation OK — now it's safe to mutate
                flagged_items = _restore_stock(prescription)
                for existing in flagged_items:
                    existing.delete()

                prescription = form.save(commit=False)
                prescription.prescription_ref = prescription_ref
                prescription.updated_by = request.user
                prescription.save()

                _apply_dispensing_items(request, prescription, parsed)
                messages.success(request, f'تم تحديث التذكرة {prescription_ref} بنجاح')
                return redirect('prescription_list')
    else:
        ref = prescription.prescription_ref
        form = PrescriptionForm(instance=prescription, initial={
            'prefix_digits': ref[:3] if len(ref) >= 3 else ref,
            'suffix_digits': ref[3:] if len(ref) > 3 else '',
        })

    return render(request, 'prescriptions/form.html', {
        'form': form,
        'title': f'تعديل التذكرة: {prescription.prescription_ref}',
        'prescription': prescription,
        'existing_items': prescription.items.select_related('medicine', 'batch').all(),
        'medicines_json': _get_medicines_json(),
    })


@admin_required
def prescription_delete(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    if request.method == 'POST':
        ref = prescription.prescription_ref
        try:
            flagged_items = _restore_stock(prescription)
            for item in flagged_items:
                item.delete()
            prescription.delete()
            messages.success(request, f'تم حذف التذكرة {ref} بنجاح')
        except Exception:
            messages.error(request, 'لا يمكن حذف هذه التذكرة')
        return redirect('prescription_list')
    return render(request, 'prescriptions/delete.html', {'prescription': prescription})


def _get_medicines_json():
    """Returns medicines with their codes and available batches as JSON"""
    medicines = Medicine.objects.all().order_by('id').prefetch_related(
        Prefetch(
            'codes',
            queryset=MedicineCode.objects.only('medicine_id', 'code'),
            to_attr='prefetched_codes',
        ),
        Prefetch(
            'batches',
            queryset=Batch.objects.filter(
                quantity_remaining__gt=0
            ).only(
                'id', 'medicine_id', 'batch_number',
                'expiry_date', 'quantity_remaining',
            ).order_by('expiry_date'),
            to_attr='available_batches',
        ),
    )
    medicines_json = []
    for medicine in medicines:
        codes = [code.code for code in medicine.prefetched_codes]
        batches = []
        for batch in medicine.available_batches:
            batches.append({
                'id': batch.id,
                'batch_number': batch.batch_number,
                'expiry_date': str(batch.expiry_date),
                'quantity_remaining': batch.quantity_remaining,
            })
        medicines_json.append({
            'id': medicine.id,
            'name': medicine.name,
            'codes': codes,
            'default_qty': medicine.default_dispense_qty or 1,
            'batches': batches,
        })
    return json.dumps(medicines_json, ensure_ascii=False)


def _validate_dispensing_items(request, prescription_snapshot=None):
    """Return (parsed_list, errors) for dispensing items in POST — zero mutations.

    prescription_snapshot is the *existing* items QuerySet (edit case). When
    supplied, validation accounts for edits (old qty restored before the new
    qty is applied) so net-change checks match reality at apply time.
    """
    medicine_ids = request.POST.getlist('item_medicine[]')
    batch_ids = request.POST.getlist('item_batch[]')
    quantities = request.POST.getlist('item_quantity[]')

    parsed = []
    errors = []

    for i in range(len(medicine_ids)):
        try:
            medicine_id = int(medicine_ids[i])
            batch_id = int(batch_ids[i])
            quantity = int(quantities[i])
        except (ValueError, IndexError):
            continue
        if quantity <= 0:
            errors.append(f'السطر {i + 1}: الكمية المصروفة يجب أن تكون أكبر من الصفر')
            continue
        parsed.append((medicine_id, batch_id, quantity, i + 1))

    # Build "net deltas" for the new items (used to compare against available stock)
    # For the edit case, an item might switch batch / change qty. So we compute
    # for each (medicine, batch) the net change = new_qty - old_qty. When no
    # old qty exists for that batch, the delta is just new_qty.
    old_batch_qty = {}  # (batch_id) -> quantity_dispensed
    old_med_qty = {}    # (medicine_id) -> quantity_dispensed
    if prescription_snapshot is not None:
        for item in prescription_snapshot:
            bid = getattr(item, 'batch_id', None)
            mid = getattr(item, 'medicine_id', None)
            q = item.quantity_dispensed or 0
            if bid is not None:
                old_batch_qty[bid] = old_batch_qty.get(bid, 0) + q
            if mid is not None:
                old_med_qty[mid] = old_med_qty.get(mid, 0) + q

    new_batch_qty = {}
    new_med_qty = {}
    for medicine_id, batch_id, quantity, _line_no in parsed:
        new_batch_qty[batch_id] = new_batch_qty.get(batch_id, 0) + quantity
        new_med_qty[medicine_id] = new_med_qty.get(medicine_id, 0) + quantity

    # Net change: positive means MORE stock consumed than before (more risky)
    # We check: new_qty_for_this_batch <= old_qty_for_this_batch + batch.remaining
    # Because at apply-time we will first restore the old then subtract the new.
    medicines_by_id = Medicine.objects.in_bulk(new_med_qty)
    batches_by_id = Batch.objects.in_bulk(new_batch_qty)

    # ── Pass 1: Validate every item (no mutations yet) ──────────────────
    for medicine_id, batch_id, quantity, line_no in parsed:
        medicine = medicines_by_id.get(medicine_id)
        if medicine is None:
            errors.append(f'الصنف في السطر {line_no} غير موجود')
            continue
        batch = batches_by_id.get(batch_id)
        if batch is None:
            errors.append(f'التشغيلة في السطر {line_no} غير موجودة')
            continue
        if batch.medicine_id != medicine_id:
            errors.append(
                f'السطر {line_no}: التشغيلة {batch.batch_number} '
                f'لا تنتمي إلى الصنف {medicine.name}'
            )
            continue
        if quantity > old_batch_qty.get(batch_id, 0) + batch.quantity_remaining:
            errors.append(
                f'السطر {line_no}: الكمية المطلوبة ({quantity}) '
                f'تتجاوز المتوفر في التشغيلة ({batch.quantity_remaining}) '
                f'للصنف {medicine.name}'
            )
            continue
        if quantity > old_med_qty.get(medicine_id, 0) + medicine.current_stock:
            errors.append(
                f'السطر {line_no}: الكمية المطلوبة ({quantity}) '
                f'تتجاوز المخزون الحالي ({medicine.current_stock}) '
                f'للصنف {medicine.name}'
            )

    if errors:
        for msg in errors:
            messages.error(request, msg)
    return parsed, errors


def _apply_dispensing_items(request, prescription, parsed):
    """Apply items previously validated by _validate_dispensing_items().

    NOTE: callers MUST have already restored old stock & deleted old items
          (if editing) before invoking this.
    """
    medicines_by_id = Medicine.objects.in_bulk({item[0] for item in parsed})
    batches_by_id = Batch.objects.in_bulk({item[1] for item in parsed})

    for medicine_id, batch_id, quantity, _line_no in parsed:
        medicine = medicines_by_id.get(medicine_id)
        batch = batches_by_id.get(batch_id)
        if medicine is None or batch is None:
            continue

        dispensing_item = DispensingItem(
            prescription=prescription,
            medicine=medicine,
            batch=batch,
            quantity_dispensed=quantity,
            created_by=request.user,
            updated_by=request.user,
        )
        dispensing_item._skip_stock_signal = True
        dispensing_item.save()

        Batch.objects.filter(pk=batch_id).update(
            quantity_remaining=models.F('quantity_remaining') - quantity
        )
        Medicine.objects.filter(pk=medicine_id).update(
            current_stock=models.F('current_stock') - quantity
        )
    return True


def _process_dispensing_items(request, prescription):
    """Legacy wrapper used by prescription_add (prescription is brand new,
    no existing items — snapshot is empty).
    """
    parsed, errors = _validate_dispensing_items(request, prescription_snapshot=[])
    if errors:
        return False
    return _apply_dispensing_items(request, prescription, parsed)


def _restore_stock(prescription):
    """Restore stock when editing or deleting a prescription.

    Returns the list of item instances so callers can delete them with
    the _skip_stock_signal flag already set (prevents post_delete signals
    from double-restoring).
    """
    items = list(prescription.items.all())
    for item in items:
        qty = item.quantity_dispensed or 0
        if qty <= 0:
            continue
        if item.batch_id:
            Batch.objects.filter(pk=item.batch_id).update(
                quantity_remaining=models.F('quantity_remaining') + qty
            )
        if item.medicine_id:
            Medicine.objects.filter(pk=item.medicine_id).update(
                current_stock=models.F('current_stock') + qty
            )
        item._skip_stock_signal = True
    return items


# ─── PURCHASE ORDERS ─────────────────────────────────────────

@login_required_custom
def order_list(request):
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')

    orders = OrderHeader.objects.select_related(
        'supplier', 'received_by', 'created_by'
    ).order_by('-order_date', '-id')

    if status_filter:
        orders = orders.filter(status=status_filter)

    if search:
        orders = orders.filter(
            Q(po_number__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(supplier_reference__icontains=search)
        )

    page_obj = paginate_queryset(request, orders)
    total = page_obj.paginator.count
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = query_params.urlencode()

    context = {
        'orders': page_obj,
        'status_filter': status_filter,
        'search': search,
        'total': total,
        'pending_count': OrderHeader.objects.filter(status='Pending').count(),
        'page_obj': page_obj,
        'query_string': query_string,
    }
    return render(request, 'orders/list.html', context)


@login_required_custom
def order_add(request):
    OrderItemFormSet = get_order_item_formset(extra=1)

    form_errors = []
    formset_errors = []
    
    logger.info(f"order_add view called with method: {request.method}")
    
    if request.method == 'POST':
        logger.info("POST request received for order_add")
        logger.info(f"POST data keys: {list(request.POST.keys())}")
        logger.info(f"TOTAL_FORMS value: {request.POST.get('items-TOTAL_FORMS', 'NOT FOUND')}")
        
        try:
            form = OrderHeaderForm(request.POST)
            formset = OrderItemFormSet(request.POST, prefix='items')

            # Validate form
            form_valid = form.is_valid()
            logger.info(f"Form valid: {form_valid}")
            if not form_valid:
                logger.error(f"Form errors: {form.errors}")
                form_errors = [str(error) for error in form.errors.values()]
            
            # Validate formset
            formset_valid = formset.is_valid()
            logger.info(f"Formset valid: {formset_valid}")
            logger.info(f"Number of forms in formset: {len(formset)}")
            if not formset_valid:
                logger.error(f"Formset errors: {formset.errors}")
                logger.error(f"Formset non-form errors: {formset.non_form_errors()}")
                formset_errors = [str(error) for error in formset.non_form_errors()]
                for i, error in enumerate(formset.errors):
                    formset_errors.append(f"Form {i}: {error}")
            
            if form_valid and formset_valid:
                logger.info("Both form and formset are valid, proceeding to save")
                order = form.save(commit=False)
                order.created_by = request.user
                order.updated_by = request.user
                order.save()
                logger.info(f"Order saved with PO number: {order.po_number}")

                item_count = _save_order_items(order, formset)
                logger.info(f"Saved {item_count} order items")
                messages.success(request, f'تم إنشاء الطلب {order.po_number} بنجاح')
                return redirect('order_list')
            else:
                logger.warning("Form or formset validation failed")
                
        except Exception as e:
            logger.exception(f"Exception in order_add: {e}")
    else:
        form = OrderHeaderForm()
        formset = OrderItemFormSet(prefix='items')

    return render(request, 'orders/form.html', {
        'form': form,
        'formset': formset,
        'title': 'إنشاء طلب شراء جديد',
        'form_errors': form_errors,
        'formset_errors': formset_errors,
    })


@login_required_custom
def order_edit(request, pk):
    order = get_object_or_404(OrderHeader, pk=pk)
    OrderItemFormSet = get_order_item_formset(extra=1)

    if request.method == 'POST':
        previous_status = order.status
        form = OrderHeaderForm(request.POST, instance=order)
        formset = OrderItemFormSet(request.POST, prefix='items')

        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.updated_by = request.user
            order.save()

            _restore_order_stock(order, was_delivered=(previous_status == 'Delivered'))

            for existing in order.items.all():
                existing._skip_stock_signal = True
                existing.delete()
            _save_order_items(order, formset)

            messages.success(request, f'تم تحديث الطلب {order.po_number} بنجاح')
            return redirect('order_list')
    else:
        form = OrderHeaderForm(instance=order)
        initial_data = []
        for item in order.items.all():
            initial_data.append({
                'medicine': item.medicine,
                'quantity_ordered': item.quantity_ordered,
                'quantity_received': item.quantity_received,
                'unit_cost': item.unit_cost,
                'batch_number': item.batch_number,
                'expiry_date': item.expiry_date,
            })
        OrderItemFormSet = get_order_item_formset(extra=0)
        formset = OrderItemFormSet(prefix='items', initial=initial_data)

    return render(request, 'orders/form.html', {
        'form': form,
        'formset': formset,
        'title': f'تعديل الطلب: {order.po_number}',
        'order': order,
        'form_errors': [str(error) for error in form.errors.values()],
        'formset_errors': [str(error) for error in formset.errors],
    })


def _save_order_items(order, formset):
    """Persist order line items and create batches/stock updates when present."""
    saved_items = 0

    for form in formset.forms:
        if not form.is_valid():
            continue

        cleaned = form.cleaned_data
        if not cleaned:
            continue

        if form.cleaned_data.get('DELETE'):
            continue

        medicine = cleaned.get('medicine')
        quantity_ordered = cleaned.get('quantity_ordered') or 0
        quantity_received = cleaned.get('quantity_received') or 0
        unit_cost = cleaned.get('unit_cost')
        batch_number = cleaned.get('batch_number') or ''
        expiry_date = cleaned.get('expiry_date')

        if not medicine:
            continue

        item = OrderItem(
            order=order,
            medicine=medicine,
            quantity_ordered=quantity_ordered,
            quantity_received=quantity_received,
            unit_cost=unit_cost,
            batch_number=batch_number,
            expiry_date=expiry_date,
        )
        item.total_cost = item.quantity_received * item.unit_cost if item.quantity_received and item.unit_cost else None
        item._skip_stock_signal = True
        item.save()

        if order.status == 'Delivered' and quantity_received > 0:
            _create_batch_and_update_stock(item, order)
            saved_items += 1

    return saved_items


@admin_required
def order_delete(request, pk):
    order = get_object_or_404(OrderHeader, pk=pk)
    if request.method == 'POST':
        po_number = order.po_number
        try:
            _restore_order_stock(order, was_delivered=(order.status == 'Delivered'))
            for item in order.items.all():
                item._skip_stock_signal = True
                item.delete()
            order.delete()
            messages.success(request, f'تم حذف الطلب {po_number} بنجاح')
        except Exception:
            messages.error(request, 'لا يمكن حذف هذا الطلب لوجود بيانات مرتبطة به')
        return redirect('order_list')
    return render(request, 'orders/delete.html', {'order': order})


def _restore_order_stock(order, was_delivered=True):
    """Reverse batch & medicine stock updates created by an order's received items."""
    if not was_delivered:
        return
    for item in order.items.all():
        qty = item.quantity_received or 0
        if qty <= 0 or not item.medicine_id:
            continue

        Medicine.objects.filter(pk=item.medicine_id).update(
            current_stock=models.F('current_stock') - qty
        )

        if item.batch_number:
            batch = Batch.objects.filter(
                medicine_id=item.medicine_id,
                batch_number=item.batch_number,
            ).first()
            if batch:
                new_remaining = batch.quantity_remaining - qty
                new_received = batch.quantity_received - qty
                if new_remaining <= 0 and new_received <= 0:
                    batch._skip_stock_signal = True
                    batch.delete()
                else:
                    Batch.objects.filter(pk=batch.pk).update(
                        quantity_remaining=max(0, new_remaining),
                        quantity_received=max(0, new_received),
                    )
        Medicine.objects.get(pk=item.medicine_id).recompute_current_stock()


def _create_batch_and_update_stock(item, order):
    """Helper function to create batch record and update stock.

    If the batch already exists (same batch_number + medicine), the new
    quantity is *added* to the existing batch.

    Batch.date_received is always set to the order's effective_receive_date
    (receive_date when the PO is marked Delivered, otherwise order_date) —
    this ensures stock-movement reports match the physical receipt date.
    """
    received_on = getattr(order, 'effective_receive_date', None) or (
        order.receive_date or order.order_date or timezone.now().date()
    )

    batch_id = None
    if item.batch_number:
        existing = Batch.objects.filter(
            batch_number=item.batch_number,
            medicine=item.medicine,
        ).first()
        if existing:
            batch_id = existing.pk
            Batch.objects.filter(pk=existing.pk).update(
                quantity_received=models.F('quantity_received') + item.quantity_received,
                quantity_remaining=models.F('quantity_remaining') + item.quantity_received,
                date_received=received_on,  # Always (re)set to match order
            )

    if batch_id is None:
        batch = Batch(
            medicine=item.medicine,
            batch_number=item.batch_number or 'N/A',
            expiry_date=item.expiry_date or timezone.now().date(),
            quantity_received=item.quantity_received,
            quantity_remaining=item.quantity_received,
            date_received=received_on,
            created_by=order.created_by,
            updated_by=order.updated_by,
        )
        batch._skip_stock_signal = True
        batch.save()

    Medicine.objects.filter(pk=item.medicine.pk).update(
        current_stock=models.F('current_stock') + item.quantity_received
    )


# ─── REPORTS ─────────────────────────────────────────────────

@login_required_custom
def report_stock_movement(request):
    today = timezone.now().date()
    start_date = request.GET.get('from', '')
    end_date = request.GET.get('to', '') or today
    category_filter = request.GET.get('category', '')

    medicines = Medicine.objects.all().order_by('category', 'id')
    if category_filter:
        medicines = medicines.filter(category__icontains=category_filter)

    categories = Medicine.objects.values_list('category', flat=True).distinct().order_by('category')
    medicine_ids = list(medicines.values_list('id', flat=True))

    def _purchase_totals(start=None, end=None, end_exclusive=False):
        queryset = OrderItem.objects.filter(
            medicine_id__in=medicine_ids,
            order__status='Delivered',
        ).annotate(
            effective=models.Case(
                models.When(order__receive_date__isnull=False,
                            then=models.F('order__receive_date')),
                default=models.F('order__order_date'),
                output_field=models.DateField(),
            )
        )
        if start is not None:
            queryset = queryset.filter(effective__gte=start)
        if end is not None:
            queryset = queryset.filter(
                effective__lt=end if end_exclusive else end
            )
        return {
            row['medicine_id']: row['total'] or 0
            for row in queryset.values('medicine_id').annotate(
                total=Sum('quantity_received')
            )
        }

    def _dispensing_totals(start=None, end=None, end_exclusive=False):
        queryset = DispensingItem.objects.filter(medicine_id__in=medicine_ids)
        if start is not None:
            queryset = queryset.filter(prescription__dispensing_date__gte=start)
        if end is not None:
            lookup = 'prescription__dispensing_date__lt' if end_exclusive else 'prescription__dispensing_date__lte'
            queryset = queryset.filter(**{lookup: end})
        return {
            row['medicine_id']: row['total'] or 0
            for row in queryset.values('medicine_id').annotate(
                total=Sum('quantity_dispensed')
            )
        }

    if start_date:
        purchases_in_range = _purchase_totals(start=start_date, end=end_date)
        dispensed_in_range = _dispensing_totals(start=start_date, end=end_date)
        purchases_before = _purchase_totals(end=start_date, end_exclusive=True)
        dispensed_before = _dispensing_totals(end=start_date, end_exclusive=True)
    else:
        purchases_in_range = _purchase_totals(end=end_date)
        dispensed_in_range = _dispensing_totals(end=end_date)
        purchases_before = {}
        dispensed_before = {}

    medicines = medicines.prefetch_related(Prefetch(
        'batches',
        queryset=Batch.objects.filter(
            quantity_remaining__gt=0
        ).only('medicine_id', 'expiry_date', 'batch_number').order_by('expiry_date'),
        to_attr='available_batches',
    ))
    rows = []

    for medicine in medicines:
        purchased = purchases_in_range.get(medicine.id, 0)
        dispensed = dispensed_in_range.get(medicine.id, 0)
        opening_stock = purchases_before.get(medicine.id, 0) - dispensed_before.get(medicine.id, 0)
        closing_stock = opening_stock + purchased - dispensed

        if purchased == 0 and dispensed == 0:
            continue

        nearest_batch = medicine.available_batches[0] if medicine.available_batches else None
        rows.append({
            'medicine': medicine,
            'opening_stock': opening_stock,
            'purchased': purchased,
            'total': opening_stock + purchased,
            'dispensed': dispensed,
            'closing_stock': closing_stock,
            'nearest_expiry': nearest_batch.expiry_date if nearest_batch else None,
            'nearest_batch_number': nearest_batch.batch_number if nearest_batch else '—',
        })

    context = {
        'rows': rows,
        'categories': categories,
        'category_filter': category_filter,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'reports/stock_movement.html', context)


@login_required_custom
def report_current_stock(request):
    # Get all batches with remaining quantity > 0, ordered by medicine and expiry
    batches = Batch.objects.filter(
        quantity_remaining__gt=0
    ).select_related('medicine').order_by('medicine__category', 'medicine__name', 'expiry_date')
    
    return render(request, 'reports/current_stock.html', {
        'batches': batches,
    })


@login_required_custom
def report_expiry(request):
    today = timezone.now().date()
    six_months = today + timedelta(days=180)
    batches = Batch.objects.filter(
        expiry_date__gte=today,
        expiry_date__lte=six_months,
        quantity_remaining__gt=0
    ).select_related('medicine').order_by('expiry_date')
    return render(request, 'reports/expiry.html', {
        'batches': batches,
        'today': today,
        'six_months': six_months,
    })


@login_required_custom
def report_under_supply(request):
    rows = []
    for medicine in Medicine.objects.filter(current_stock=0).order_by('category', 'id'):
        latest_item = OrderItem.objects.filter(medicine=medicine).order_by('-order__order_date', '-order__id').first()
        if not latest_item or latest_item.quantity_received != 0:
            continue

        last_successful = OrderItem.objects.filter(
            medicine=medicine,
            quantity_received__gt=0
        ).order_by('-order__order_date', '-order__id').first()

        last_supply_date = last_successful.order.order_date if last_successful else None

        events = []
        for item in OrderItem.objects.filter(medicine=medicine).select_related('order'):
            if item.order.order_date:
                events.append({
                    'date': item.order.order_date,
                    'change': item.quantity_received,
                    'type': 'order',
                })
        for item in DispensingItem.objects.filter(medicine=medicine).select_related('prescription'):
            if item.prescription.dispensing_date:
                events.append({
                    'date': item.prescription.dispensing_date,
                    'change': -item.quantity_dispensed,
                    'type': 'dispense',
                })

        events.sort(key=lambda e: (e['date'], 0 if e['type'] == 'order' else 1))
        running_balance = 0
        zero_date = None
        for event in events:
            running_balance += event['change']
            if running_balance == 0:
                zero_date = event['date']

        rows.append({
            'medicine': medicine,
            'zero_date': zero_date,
            'last_supply_date': last_supply_date,
        })
    return render(request, 'reports/under_supply.html', {
        'rows': rows,
    })


@login_required_custom
def report_low_stock(request):
    category_filter = request.GET.get('category', '')
    medicines = Medicine.objects.filter(
        reorder_level__gt=0,
        current_stock__lte=models.F('reorder_level')
    ).order_by('category', 'id')

    if category_filter:
        medicines = medicines.filter(category__icontains=category_filter)

    categories = Medicine.objects.values_list('category', flat=True).distinct().order_by('category')
    return render(request, 'reports/low_stock.html', {
        'medicines': medicines,
        'categories': categories,
        'category_filter': category_filter,
    })


@login_required_custom
def report_daily_dispensing(request):
    date_filter = request.GET.get('date', '')
    today = timezone.now().date()
    selected_date = date_filter or today

    prescriptions = Prescription.objects.filter(
        dispensing_date=selected_date
    ).annotate(item_count=Count('items')).prefetch_related(
        Prefetch(
            'items',
            queryset=DispensingItem.objects.select_related('medicine'),
        )
    ).order_by('prescription_ref')

    return render(request, 'reports/daily_dispensing.html', {
        'prescriptions': prescriptions,
        'selected_date': selected_date,
    })


# ─── USERS ───────────────────────────────────────────────────

@admin_required
def user_list(request):
    search = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')

    users = User.objects.select_related('profile').order_by('username')

    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    if role_filter:
        users = users.filter(profile__role=role_filter)

    page_obj = paginate_queryset(request, users)
    total = page_obj.paginator.count
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = query_params.urlencode()

    context = {
        'users': page_obj,
        'page_obj': page_obj,
        'query_string': query_string,
        'search': search,
        'role_filter': role_filter,
        'roles': UserProfile.ROLE_CHOICES,
        'total': total,
    }
    return render(request, 'users/list.html', context)


@admin_required
def user_add(request):
    if request.method == 'POST':
        form = UserForm(request.POST)
        profile_form = UserProfileForm(request.POST)
        if form.is_valid() and profile_form.is_valid():
            user = form.save(commit=False)
            password = form.cleaned_data.get('password')
            if password:
                user.set_password(password)
            else:
                user.set_unusable_password()
            user.save()

            profile = profile_form.save(commit=False)
            profile.user = user
            profile.save()

            messages.success(request, f'تم إضافة المستخدم {user.username} بنجاح')
            return redirect('user_list')
    else:
        form = UserForm()
        profile_form = UserProfileForm()

    return render(request, 'users/form.html', {
        'form': form,
        'profile_form': profile_form,
        'title': 'إضافة مستخدم جديد',
    })


@admin_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == 'POST':
        form = UserForm(request.POST, instance=user)
        profile_form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid() and profile_form.is_valid():
            user = form.save(commit=False)
            password = form.cleaned_data.get('password')
            if password:
                user.set_password(password)
            user.save()

            profile = profile_form.save(commit=False)
            profile.user = user
            profile.save()

            messages.success(request, f'تم تحديث المستخدم {user.username} بنجاح')
            return redirect('user_list')
    else:
        form = UserForm(instance=user)
        profile_form = UserProfileForm(instance=profile)

    return render(request, 'users/form.html', {
        'form': form,
        'profile_form': profile_form,
        'title': f'تعديل المستخدم: {user.username}',
        'user_object': user,
    })


@admin_required
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            user.set_password(new_password)
            user.save()
            messages.success(request, f'تم إعادة تعيين كلمة المرور للمستخدم {user.username} بنجاح')
            return redirect('user_list')
    else:
        form = PasswordResetForm()

    return render(request, 'users/reset_password.html', {
        'form': form,
        'title': f'إعادة تعيين كلمة المرور: {user.username}',
        'user_object': user,
    })