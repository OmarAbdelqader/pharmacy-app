from django.db import models
from django.contrib.auth.models import User


class TimeStampedModel(models.Model):
    """Abstract base model that adds tracking fields to every model"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='%(class)s_created'
    )
    updated_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='%(class)s_updated'
    )

    class Meta:
        abstract = True


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'مورد'
        verbose_name_plural = 'الموردون'

    def __str__(self):
        return self.name


class Medicine(TimeStampedModel):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True)
    book_reference = models.CharField(max_length=50, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    current_stock = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0)
    default_dispense_qty = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'صنف'
        verbose_name_plural = 'الأصناف'

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        return self.reorder_level > 0 and self.current_stock <= self.reorder_level


class MedicineCode(TimeStampedModel):
    medicine = models.ForeignKey(
        Medicine, on_delete=models.CASCADE,
        related_name='codes'
    )
    code = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = 'كود'
        verbose_name_plural = 'الأكواد'

    def __str__(self):
        return f"{self.code} - {self.medicine.name}"


class Batch(TimeStampedModel):
    medicine = models.ForeignKey(
        Medicine, on_delete=models.PROTECT,
        related_name='batches'
    )
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField()
    quantity_received = models.IntegerField()
    quantity_remaining = models.IntegerField()
    date_received = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['expiry_date']
        verbose_name = 'تشغيلة'
        verbose_name_plural = 'التشغيلات'

    def __str__(self):
        return f"{self.medicine.name} - {self.batch_number} - {self.expiry_date}"

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.expiry_date < timezone.now().date()


class OrderHeader(TimeStampedModel):
    STATUS_CHOICES = [
        ('Pending', 'قيد الانتظار'),
        ('Delivered', 'تم التسليم'),
        ('Cancelled', 'ملغي'),
    ]

    po_number = models.CharField(max_length=20, unique=True, blank=True)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT,
        related_name='orders'
    )
    supplier_reference = models.CharField(max_length=100, blank=True)
    order_date = models.DateField()
    delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Pending'
    )
    received_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='orders_received'
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-order_date']
        verbose_name = 'طلب شراء'
        verbose_name_plural = 'طلبات الشراء'

    def __str__(self):
        return f"{self.po_number} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        # Auto-generate PO number
        if not self.po_number:
            last = OrderHeader.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.po_number = f"PO-{next_num:04d}"
        super().save(*args, **kwargs)


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(
        OrderHeader, on_delete=models.CASCADE,
        related_name='items'
    )
    medicine = models.ForeignKey(
        Medicine, on_delete=models.PROTECT,
        related_name='order_items'
    )
    quantity_ordered = models.IntegerField()
    quantity_received = models.IntegerField(default=0)
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True
    )
    total_cost = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True
    )
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'صنف في الطلب'
        verbose_name_plural = 'أصناف الطلب'

    def __str__(self):
        return f"{self.order.po_number} - {self.medicine.name}"

    def save(self, *args, **kwargs):
        # Auto-calculate total cost
        if self.quantity_received and self.unit_cost:
            self.total_cost = self.quantity_received * self.unit_cost
        super().save(*args, **kwargs)


class Prescription(TimeStampedModel):
    prescription_ref = models.CharField(max_length=10, unique=True)
    dispensing_date = models.DateField()

    class Meta:
        ordering = ['-dispensing_date', 'prescription_ref']
        verbose_name = 'تذكرة'
        verbose_name_plural = 'التذاكر'

    def __str__(self):
        return f"{self.prescription_ref} - {self.dispensing_date}"


class DispensingItem(TimeStampedModel):
    prescription = models.ForeignKey(
        Prescription, on_delete=models.CASCADE,
        related_name='items'
    )
    medicine = models.ForeignKey(
        Medicine, on_delete=models.PROTECT,
        related_name='dispensing_items'
    )
    batch = models.ForeignKey(
        Batch, on_delete=models.PROTECT,
        related_name='dispensing_items'
    )
    quantity_dispensed = models.IntegerField()

    class Meta:
        verbose_name = 'صنف في التذكرة'
        verbose_name_plural = 'أصناف التذكرة'

    def __str__(self):
        return f"{self.prescription.prescription_ref} - {self.medicine.name}"
    
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'مدير'),
        ('pharmacist', 'صيدلي'),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name='profile'
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='pharmacist'
    )

    class Meta:
        verbose_name = 'ملف المستخدم'
        verbose_name_plural = 'ملفات المستخدمين'

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_pharmacist(self):
        return self.role == 'pharmacist'