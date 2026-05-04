from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from django.db import models
from django.db.models import Q, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.forms import formset_factory
from django.http import JsonResponse
from datetime import timedelta
from .decorators import login_required_custom, admin_required
from .models import Medicine, MedicineCode, Supplier, Batch, OrderHeader, OrderItem, Prescription, DispensingItem, UserProfile
from .forms import MedicineForm, SupplierForm, MedicineCodeForm, OrderHeaderForm, OrderItemForm, PrescriptionForm, DispensingItemForm, UserForm, UserProfileForm, PasswordResetForm
import json

from django.views.decorators.csrf import csrf_exempt


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
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة')
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

    total = medicines.count()
    page_obj = paginate_queryset(request, medicines)
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

    total = suppliers.count()
    page_obj = paginate_queryset(request, suppliers)
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
        codes = MedicineCode.objects.filter(medicine=selected_medicine)

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
                codes = MedicineCode.objects.filter(medicine=selected_medicine)

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

    prescriptions = Prescription.objects.all().order_by('-dispensing_date', '-id')

    if search:
        prescriptions = prescriptions.filter(
            prescription_ref__icontains=search
        )

    if date_filter:
        prescriptions = prescriptions.filter(dispensing_date=date_filter)

    total = prescriptions.count()
    page_obj = paginate_queryset(request, prescriptions)
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

            # Check if items were added via JavaScript (from POST data)
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

                _process_dispensing_items(request, prescription)

                messages.success(request, f'تم حفظ التذكرة {prescription.prescription_ref} بنجاح')
                # Redirect to new prescription with same prefix
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

            # Check for duplicate excluding current
            if Prescription.objects.filter(
                prescription_ref=prescription_ref
            ).exclude(pk=pk).exists():
                messages.error(request, f'رقم التذكرة {prescription_ref} مستخدم بالفعل')
            else:
                # Restore stock for existing items
                _restore_stock(prescription)

                # Delete existing items
                prescription.items.all().delete()

                # Update prescription
                prescription = form.save(commit=False)
                prescription.prescription_ref = prescription_ref
                prescription.updated_by = request.user
                prescription.save()

                # Process new dispensing items
                _process_dispensing_items(request, prescription)

                messages.success(request, f'تم تحديث التذكرة {prescription_ref} بنجاح')
                return redirect('prescription_list')
    else:
        # Pre-populate prefix and suffix
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
            _restore_stock(prescription)
            prescription.items.all().delete()
            prescription.delete()
            messages.success(request, f'تم حذف التذكرة {ref} بنجاح')
        except Exception:
            messages.error(request, 'لا يمكن حذف هذه التذكرة')
        return redirect('prescription_list')
    return render(request, 'prescriptions/delete.html', {'prescription': prescription})


def _get_medicines_json():
    """Returns medicines with their codes and available batches as JSON"""
    medicines = []
    for medicine in Medicine.objects.all().order_by('id'):
        codes = list(medicine.codes.values_list('code', flat=True))
        batches = []
        for batch in medicine.batches.filter(
            quantity_remaining__gt=0
        ).order_by('expiry_date'):
            batches.append({
                'id': batch.id,
                'batch_number': batch.batch_number,
                'expiry_date': str(batch.expiry_date),
                'quantity_remaining': batch.quantity_remaining,
            })
        medicines.append({
            'id': medicine.id,
            'name': medicine.name,
            'codes': codes,
            'default_qty': medicine.default_dispense_qty or 1,
            'batches': batches,
        })
    return json.dumps(medicines, ensure_ascii=False)


def _process_dispensing_items(request, prescription):
    """Process dispensing items from POST data"""
    medicine_ids = request.POST.getlist('item_medicine[]')
    batch_ids = request.POST.getlist('item_batch[]')
    quantities = request.POST.getlist('item_quantity[]')

    for i in range(len(medicine_ids)):
        try:
            medicine_id = int(medicine_ids[i])
            batch_id = int(batch_ids[i])
            quantity = int(quantities[i])

            if quantity <= 0:
                continue

            medicine = Medicine.objects.get(pk=medicine_id)
            batch = Batch.objects.get(pk=batch_id)

            # Create dispensing item
            DispensingItem.objects.create(
                prescription=prescription,
                medicine=medicine,
                batch=batch,
                quantity_dispensed=quantity,
                created_by=request.user,
                updated_by=request.user,
            )

            # Update batch quantity remaining
            Batch.objects.filter(pk=batch_id).update(
                quantity_remaining=models.F('quantity_remaining') - quantity
            )

            # Update medicine current stock
            Medicine.objects.filter(pk=medicine_id).update(
                current_stock=models.F('current_stock') - quantity
            )

        except (ValueError, Medicine.DoesNotExist, Batch.DoesNotExist):
            continue


def _restore_stock(prescription):
    """Restore stock when editing or deleting a prescription"""
    for item in prescription.items.all():
        Batch.objects.filter(pk=item.batch.pk).update(
            quantity_remaining=models.F('quantity_remaining') + item.quantity_dispensed
        )
        Medicine.objects.filter(pk=item.medicine.pk).update(
            current_stock=models.F('current_stock') + item.quantity_dispensed
        )


# ─── PURCHASE ORDERS ─────────────────────────────────────────

@login_required_custom
def order_list(request):
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')

    orders = OrderHeader.objects.all().order_by('-order_date', '-id')

    if status_filter:
        orders = orders.filter(status=status_filter)

    if search:
        orders = orders.filter(
            Q(po_number__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(supplier_reference__icontains=search)
        )

    total = orders.count()
    page_obj = paginate_queryset(request, orders)
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


@csrf_exempt
@login_required_custom
def order_add(request):
    OrderItemFormSet = formset_factory(OrderItemForm, extra=1, can_delete=True, max_num=20)

    print(f"Request method: {request.method}")
    if request.method == 'POST':
        print("POST request received for order_add")
        print(f"POST data keys: {list(request.POST.keys())}")
        try:
            form = OrderHeaderForm(request.POST)
            formset = OrderItemFormSet(request.POST, prefix='items')

            if form.is_valid() and formset.is_valid():
                # Save order header
                order = form.save(commit=False)
                order.created_by = request.user
                order.updated_by = request.user
                order.save()

                # Save order items
                for item_form in formset:
                    if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE'):
                        item = item_form.save(commit=False)
                        item.order = order
                        item.save()

                        # If delivered, create batch and update stock
                        if order.status == 'Delivered' and item.quantity_received > 0:
                            _create_batch_and_update_stock(item, order)

                messages.success(request, f'تم إنشاء الطلب {order.po_number} بنجاح')
                return redirect('order_list')
        except Exception as e:
            print(f"Exception in order_add: {e}")
            import traceback
            traceback.print_exc()
    else:
        form = OrderHeaderForm()
        formset = OrderItemFormSet(prefix='items')

    return render(request, 'orders/form.html', {
        'form': form,
        'formset': formset,
        'title': 'إنشاء طلب شراء جديد',
    })


@login_required_custom
def order_edit(request, pk):
    order = get_object_or_404(OrderHeader, pk=pk)
    OrderItemFormSet = formset_factory(OrderItemForm, extra=1, can_delete=True)

    if request.method == 'POST':
        form = OrderHeaderForm(request.POST, instance=order)
        formset = OrderItemFormSet(request.POST, prefix='items')

        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.updated_by = request.user
            order.save()

            # Delete existing items and recreate
            order.items.all().delete()

            for item_form in formset:
                if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE'):
                    item = item_form.save(commit=False)
                    item.order = order
                    item.save()

                    # If delivered, create batch and update stock
                    if order.status == 'Delivered' and item.quantity_received > 0:
                        _create_batch_and_update_stock(item, order)

            messages.success(request, f'تم تحديث الطلب {order.po_number} بنجاح')
            return redirect('order_list')
    else:
        form = OrderHeaderForm(instance=order)
        # Pre-populate formset with existing items
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
        OrderItemFormSet = formset_factory(OrderItemForm, extra=0, can_delete=True)
        formset = OrderItemFormSet(prefix='items', initial=initial_data)

    return render(request, 'orders/form.html', {
        'form': form,
        'formset': formset,
        'title': f'تعديل الطلب: {order.po_number}',
        'order': order,
    })


@admin_required
def order_delete(request, pk):
    order = get_object_or_404(OrderHeader, pk=pk)
    if request.method == 'POST':
        po_number = order.po_number
        try:
            order.items.all().delete()
            order.delete()
            messages.success(request, f'تم حذف الطلب {po_number} بنجاح')
        except Exception:
            messages.error(request, 'لا يمكن حذف هذا الطلب لوجود بيانات مرتبطة به')
        return redirect('order_list')
    return render(request, 'orders/delete.html', {'order': order})


def _create_batch_and_update_stock(item, order):
    """Helper function to create batch record and update stock"""
    # Check if batch already exists
    if item.batch_number:
        exists = Batch.objects.filter(
            batch_number=item.batch_number,
            medicine=item.medicine
        ).exists()
        if exists:
            return

    # Create batch
    Batch.objects.create(
        medicine=item.medicine,
        batch_number=item.batch_number or 'N/A',
        expiry_date=item.expiry_date or timezone.now().date(),
        quantity_received=item.quantity_received,
        quantity_remaining=item.quantity_received,
        date_received=order.delivery_date or timezone.now().date(),
    )

    # Update current stock
    Medicine.objects.filter(pk=item.medicine.pk).update(
        current_stock=models.F('current_stock') + item.quantity_received
    )


# ─── REPORTS ─────────────────────────────────────────────────

@login_required_custom
def report_stock_movement(request):
    today = timezone.now().date()
    start_date = request.GET.get('from', '')
    end_date = request.GET.get('to', '')
    category_filter = request.GET.get('category', '')

    medicines = Medicine.objects.all().order_by('category', 'id')
    if category_filter:
        medicines = medicines.filter(category__icontains=category_filter)

    categories = Medicine.objects.values_list('category', flat=True).distinct().order_by('category')
    rows = []

    for medicine in medicines:
        purchases_in_range = 0
        dispensed_in_range = 0
        opening_stock = 0
        closing_stock = 0

        if start_date:
            purchases_in_range = OrderItem.objects.filter(
                medicine=medicine,
                order__status='Delivered',
                order__order_date__gte=start_date,
                order__order_date__lte=end_date or today
            ).aggregate(total=Sum('quantity_received'))['total'] or 0

            dispensed_in_range = DispensingItem.objects.filter(
                medicine=medicine,
                prescription__dispensing_date__gte=start_date,
                prescription__dispensing_date__lte=end_date or today
            ).aggregate(total=Sum('quantity_dispensed'))['total'] or 0

            purchases_before = OrderItem.objects.filter(
                medicine=medicine,
                order__status='Delivered',
                order__order_date__lt=start_date
            ).aggregate(total=Sum('quantity_received'))['total'] or 0

            dispensed_before = DispensingItem.objects.filter(
                medicine=medicine,
                prescription__dispensing_date__lt=start_date
            ).aggregate(total=Sum('quantity_dispensed'))['total'] or 0

            opening_stock = purchases_before - dispensed_before
            closing_stock = opening_stock + purchases_in_range - dispensed_in_range
        else:
            purchases_in_range = OrderItem.objects.filter(
                medicine=medicine,
                order__status='Delivered',
                order__order_date__lte=end_date or today
            ).aggregate(total=Sum('quantity_received'))['total'] or 0

            dispensed_in_range = DispensingItem.objects.filter(
                medicine=medicine,
                prescription__dispensing_date__lte=end_date or today
            ).aggregate(total=Sum('quantity_dispensed'))['total'] or 0

            opening_stock = 0
            closing_stock = opening_stock + purchases_in_range - dispensed_in_range

        if purchases_in_range == 0 and dispensed_in_range == 0:
            continue

        nearest_batch = medicine.batches.filter(quantity_remaining__gt=0).order_by('expiry_date').first()
        rows.append({
            'medicine': medicine,
            'opening_stock': opening_stock,
            'purchased': purchases_in_range,
            'total': opening_stock + purchases_in_range,
            'dispensed': dispensed_in_range,
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
    medicines = Medicine.objects.all().order_by('category', 'id')
    return render(request, 'reports/current_stock.html', {
        'medicines': medicines,
    })


@login_required_custom
def report_expiry(request):
    today = timezone.now().date()
    six_months = today + timedelta(days=180)
    batches = Batch.objects.filter(
        expiry_date__gte=today,
        expiry_date__lte=six_months,
        quantity_remaining__gt=0
    ).order_by('expiry_date')
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

    users = User.objects.all().order_by('username')

    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    if role_filter:
        users = users.filter(profile__role=role_filter)

    total = users.count()
    page_obj = paginate_queryset(request, users)
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