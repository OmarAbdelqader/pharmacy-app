from django.contrib import admin
from .models import (
    Medicine, MedicineCode, Supplier, Batch,
    OrderHeader, OrderItem, Prescription, DispensingItem, UserProfile
)


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
    list_display = ['po_number', 'supplier', 'order_date', 'status', 'delivery_date']
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

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role']
    # search_fields = ['user__username', 'role']
    list_filter = ['role']