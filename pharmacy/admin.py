from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import (
    Medicine, MedicineCode, Supplier, Batch,
    OrderHeader, OrderItem, Prescription, DispensingItem, UserProfile,
    VaccineVial,
)
from .stock_history import record_stock_movement


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'unit', 'current_stock', 'reorder_level', 'is_low_stock']
    search_fields = ['name', 'category', 'book_reference']
    list_filter = ['category']


@admin.register(MedicineCode)
class MedicineCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'medicine']
    search_fields = ['code', 'medicine__name']


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'email']
    search_fields = ['name']


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ['medicine', 'batch_number', 'expiry_date', 'quantity_received', 'quantity_remaining']
    search_fields = ['medicine__name', 'batch_number']
    list_filter = ['expiry_date']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1


@admin.register(OrderHeader)
class OrderHeaderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'supplier', 'order_date', 'status', 'receive_date']
    search_fields = ['po_number', 'supplier__name']
    list_filter = ['status']
    inlines = [OrderItemInline]


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ['prescription_ref', 'dispensing_date', 'created_by']
    search_fields = ['prescription_ref']
    list_filter = ['dispensing_date']


@admin.register(DispensingItem)
class DispensingItemAdmin(admin.ModelAdmin):
    list_display = ['prescription', 'medicine', 'batch', 'quantity_dispensed']
    search_fields = ['prescription__prescription_ref', 'medicine__name']


class VaccineVialAdminForm(forms.ModelForm):
    correction_reason = forms.CharField(
        required=False,
        max_length=500,
        label='سبب تعديل الجرعات',
        widget=forms.Textarea(attrs={'rows': 2}),
    )

    class Meta:
        model = VaccineVial
        fields = ['batch', 'opened_date', 'disposal_date', 'doses_remaining', 'disposed']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'batch' in self.fields:
            self.fields['batch'].queryset = Batch.objects.filter(
                medicine__is_vaccine=True,
            ).select_related('medicine').order_by('medicine__name', 'expiry_date', 'id')
        if self.instance.pk and 'batch' in self.fields:
            self.fields['batch'].disabled = True

    def clean_batch(self):
        batch = self.cleaned_data['batch']
        batch = Batch.objects.select_for_update().select_related('medicine').get(pk=batch.pk)
        if not batch.medicine.is_vaccine:
            raise ValidationError('يجب اختيار تشغيلة تطعيم')
        if not self.instance.pk and batch.quantity_remaining < 1:
            raise ValidationError('لا توجد فيالات غير مفتوحة متبقية في التشغيلة')
        return batch

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.pk and 'doses_remaining' in cleaned_data:
            if cleaned_data['doses_remaining'] != self.instance.doses_remaining:
                if not cleaned_data.get('correction_reason', '').strip():
                    self.add_error('correction_reason', 'سبب تعديل الجرعات مطلوب')
        return cleaned_data


@admin.register(VaccineVial)
class VaccineVialAdmin(admin.ModelAdmin):
    form = VaccineVialAdminForm
    list_display = [
        'batch', 'opened_date', 'disposal_date',
        'doses_remaining', 'disposed',
    ]
    list_filter = ['disposed', 'opened_date', 'disposal_date']
    search_fields = ['batch__medicine__name', 'batch__batch_number']

    def get_readonly_fields(self, request, obj=None):
        return ('batch',) if obj else ()

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change:
            previous = VaccineVial.objects.select_for_update().get(pk=obj.pk)
            old_doses = previous.doses_remaining
            obj.updated_by = request.user
            super().save_model(request, obj, form, change)
            dose_delta = obj.doses_remaining - old_doses
            if dose_delta:
                reason = form.cleaned_data['correction_reason'].strip()
                record_stock_movement(
                    obj.batch.medicine,
                    'vaccine_dose',
                    dose_delta,
                    batch=obj.batch,
                    reference=f'Vial #{obj.pk} admin adjustment by {request.user.username}: {reason}',
                    quantity_unit='جرعة',
                    affects_stock_balance=False,
                )
            return

        batch = Batch.objects.select_for_update().select_related('medicine').get(pk=obj.batch_id)
        if batch.quantity_remaining < 1:
            raise ValidationError('لا توجد فيالات غير مفتوحة متبقية في التشغيلة')
        batch.quantity_remaining -= 1
        batch.updated_by = request.user
        batch.save()
        obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role']
    # search_fields = ['user__username', 'role']
    list_filter = ['role']