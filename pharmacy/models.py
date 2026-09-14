from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Sum
from django.contrib.auth.models import User
from django.utils import timezone


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
    PRODUCT_TYPE_CHOICES = [
        ('medicine', 'دواء'),
        ('vaccine', 'تطعيم'),
        ('syringe', 'سرنجة'),
    ]
    SYRINGE_SIZE_CHOICES = [
        ('0.5', '0.5 مل'),
        ('3.0', '3 مل'),
    ]
    VACCINE_TYPE_CHOICES = [
        ('parenteral', 'حقني'),
        ('oral', 'فموي'),
    ]

    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True)
    book_reference = models.CharField(max_length=50, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    current_stock = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0)
    default_dispense_qty = models.IntegerField(null=True, blank=True)
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default='medicine')
    syringe_size = models.CharField(max_length=10, choices=SYRINGE_SIZE_CHOICES, blank=True)
    is_vaccine = models.BooleanField(default=False)
    vaccine_type = models.CharField(
        max_length=20,
        choices=VACCINE_TYPE_CHOICES,
        blank=True,
    )
    doses_per_vial = models.PositiveIntegerField(null=True, blank=True)
    opened_vial_validity_days = models.PositiveIntegerField(null=True, blank=True)
    requires_three_ml_syringe = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['category', 'id']),
            models.Index(fields=['current_stock', 'reorder_level']),
        ]
        verbose_name = 'صنف'
        verbose_name_plural = 'الأصناف'

    def __str__(self):
        return self.name

    def clean(self):
        if self.current_stock < 0:
            raise ValidationError({'current_stock': 'لا يمكن أن يكون المخزون الحالي قيمة سالبة'})
        if self.reorder_level < 0:
            raise ValidationError({'reorder_level': 'لا يمكن أن يكون حد إعادة الطلب قيمة سالبة'})
        if self.default_dispense_qty is not None and self.default_dispense_qty <= 0:
            raise ValidationError({'default_dispense_qty': 'يجب أن تكون الكمية الافتراضية أكبر من الصفر'})
        if self.product_type == 'syringe' and not self.syringe_size:
            raise ValidationError({'syringe_size': 'مقاس السرنجة مطلوب'})
        if self.product_type != 'syringe' and self.syringe_size:
            raise ValidationError({'syringe_size': 'مقاس السرنجة يستخدم مع منتجات السرنجات فقط'})
        if self.product_type == 'vaccine' and not self.is_vaccine:
            raise ValidationError({'is_vaccine': 'يجب تحديد الصنف كتطعيم'})
        if self.is_vaccine and self.product_type != 'vaccine':
            raise ValidationError({'product_type': 'نوع المنتج يجب أن يكون تطعيماً'})
        if self.is_vaccine:
            if not self.vaccine_type:
                raise ValidationError({'vaccine_type': 'نوع التطعيم مطلوب'})
            if not self.doses_per_vial or self.doses_per_vial <= 0:
                raise ValidationError({'doses_per_vial': 'عدد الجرعات في الفيالة يجب أن يكون أكبر من الصفر'})
            if self.opened_vial_validity_days is None or self.opened_vial_validity_days <= 0:
                raise ValidationError({'opened_vial_validity_days': 'مدة صلاحية الفيالة بعد الفتح مطلوبة'})
        elif any((self.vaccine_type, self.doses_per_vial, self.opened_vial_validity_days)):
            raise ValidationError('بيانات التطعيم لا تستخدم إلا مع الأصناف المحددة كتطعيمات')

    @property
    def is_low_stock(self):
        return self.reorder_level > 0 and self.current_stock <= self.reorder_level

    def recompute_current_stock(self, commit=True):
        """Re-derive current_stock from the sum of Batch.quantity_remaining.

        Use this to fix drift between the denormalized current_stock field
        and the actual sum of remaining batch quantities.
        """
        aggregate = self.batches.aggregate(total=Sum('quantity_remaining'))
        derived = aggregate['total'] or 0
        if self.current_stock != derived:
            self.current_stock = derived
            if commit:
                Medicine.objects.filter(pk=self.pk).update(current_stock=derived)
        return self.current_stock


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
        indexes = [
            models.Index(fields=['expiry_date', 'quantity_remaining']),
        ]
        verbose_name = 'تشغيلة'
        verbose_name_plural = 'التشغيلات'

    def __str__(self):
        return f"{self.medicine.name} - {self.batch_number} - {self.expiry_date}"

    def clean(self):
        if self.quantity_received <= 0:
            raise ValidationError({'quantity_received': 'يجب أن تكون الكمية المستلمة أكبر من الصفر'})
        if self.quantity_remaining < 0:
            raise ValidationError({'quantity_remaining': 'لا يمكن أن تكون الكمية المتبقية سالبة'})
        if self.quantity_remaining > self.quantity_received:
            raise ValidationError({
                'quantity_remaining': 'لا يمكن أن تكون الكمية المتبقية أكبر من الكمية المستلمة'
            })
        if self.expiry_date and self.date_received and self.expiry_date < self.date_received:
            raise ValidationError({
                'expiry_date': 'تاريخ الانتهاء لا يمكن أن يكون قبل تاريخ الاستلام'
            })

    @property
    def is_expired(self):
        return self.expiry_date < timezone.now().date()

    @property
    def expiry_status(self):
        today = timezone.now().date()
        if self.expiry_date < today:
            return 'expired'
        if self.expiry_date <= today + timedelta(days=30):
            return 'expiring'
        return 'valid'


class VaccineVial(TimeStampedModel):
    batch = models.ForeignKey(
        Batch, on_delete=models.PROTECT,
        related_name='vaccine_vials'
    )
    opened_date = models.DateField()
    disposal_date = models.DateField()
    doses_remaining = models.PositiveIntegerField(default=0)
    disposed = models.BooleanField(default=False)

    class Meta:
        ordering = ['opened_date', 'id']
        indexes = [
            models.Index(fields=['batch', 'disposed', 'doses_remaining']),
        ]
        verbose_name = 'فيالة تطعيم مفتوحة'
        verbose_name_plural = 'فيالات التطعيم المفتوحة'

    def __str__(self):
        return f'{self.batch.medicine.name} - {self.batch.batch_number} - {self.opened_date}'

    def clean(self):
        if not self.batch_id:
            raise ValidationError({'batch': 'التشغيلة مطلوبة'})
        medicine = self.batch.medicine
        if not medicine.is_vaccine:
            raise ValidationError({'batch': 'التشغيلة لا تنتمي إلى تطعيم'})
        if self.doses_remaining > medicine.doses_per_vial:
            raise ValidationError({
                'doses_remaining': 'الجرعات المتبقية لا يمكن أن تتجاوز سعة الفيالة'
            })
        if self.disposal_date < self.opened_date:
            raise ValidationError({
                'disposal_date': 'تاريخ الإعدام لا يمكن أن يسبق تاريخ الفتح'
            })

    @property
    def available_doses(self):
        if self.disposed or self.disposal_date < timezone.now().date():
            return 0
        return self.doses_remaining


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
    receive_date = models.DateField(null=True, blank=True,
                                    verbose_name='تاريخ الاستلام الفعلي')
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
        indexes = [
            models.Index(fields=['status', '-order_date']),
        ]
        verbose_name = 'طلب شراء'
        verbose_name_plural = 'طلبات الشراء'

    def __str__(self):
        return f"{self.po_number} - {self.supplier.name}"

    def clean(self):
        if self.status == 'Delivered' and not self.receive_date:
            raise ValidationError({
                'receive_date': (
                    'تاريخ الاستلام مطلوب عند ضبط الحالة "تم التسليم". '
                    'يرجى إدخال تاريخ الاستلام قبل الحفظ.'
                )
            })

    def save(self, *args, **kwargs):
        # Auto-generate PO number
        if not self.po_number:
            last = OrderHeader.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.po_number = f"PO-{next_num:04d}"
        super().save(*args, **kwargs)

    @property
    def effective_receive_date(self):
        """Receive date when delivered; otherwise fall back to order_date.

        Used for batch registration & stock-movement date filtering.
        """
        return self.receive_date or self.order_date


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(
        OrderHeader, on_delete=models.CASCADE,
        related_name='items'
    )
    medicine = models.ForeignKey(
        Medicine, on_delete=models.PROTECT,
        related_name='order_items'
    )
    quantity_ordered = models.IntegerField(default=0, blank=True)
    quantity_received = models.IntegerField(default=0, blank=True)
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

    def clean(self):
        if self.quantity_ordered is not None and self.quantity_ordered < 0:
            raise ValidationError({'quantity_ordered': 'لا يمكن أن تكون الكمية المطلوبة سالبة'})
        if self.quantity_received is not None and self.quantity_received < 0:
            raise ValidationError({'quantity_received': 'لا يمكن أن تكون الكمية المستلمة سالبة'})

    def save(self, *args, **kwargs):
        if self.quantity_ordered is None:
            self.quantity_ordered = 0
        if self.quantity_received is None:
            self.quantity_received = 0
        if self.quantity_received and self.unit_cost:
            self.total_cost = self.quantity_received * self.unit_cost
        super().save(*args, **kwargs)


class Prescription(TimeStampedModel):
    prescription_ref = models.CharField(max_length=10, unique=True)
    dispensing_date = models.DateField()

    class Meta:
        indexes = [
            models.Index(fields=['dispensing_date', 'prescription_ref']),
        ]
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

    def clean(self):
        if self.quantity_dispensed <= 0:
            raise ValidationError({'quantity_dispensed': 'يجب أن تكون الكمية المصروفة أكبر من الصفر'})
        if self.batch_id and self.medicine_id and self.batch.medicine_id != self.medicine_id:
            raise ValidationError({'batch': 'التشغيلة المختارة لا تنتمي إلى الصنف المحدد'})
        if self.batch_id:
            batch_obj = Batch.objects.filter(pk=self.batch_id).first()
            if batch_obj:
                available = batch_obj.quantity_remaining
                if self.pk:
                    from django.db.models.functions import Coalesce
                    prev_qs = DispensingItem.objects.filter(pk=self.pk).values_list('quantity_dispensed', flat=True)
                    previous = prev_qs.first() or 0
                    available = available + previous
                if self.quantity_dispensed > available:
                    raise ValidationError({
                        'quantity_dispensed': (
                            f'الكمية المصروفة ({self.quantity_dispensed}) '
                            f'تتجاوز الكمية المتوفرة في التشغيلة ({available})'
                        )
                    })


class VaccineDispensing(TimeStampedModel):
    dispensing_date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-dispensing_date', '-id']
        indexes = [models.Index(fields=['dispensing_date', '-id'])]
        verbose_name = 'حركة تطعيم'
        verbose_name_plural = 'حركات التطعيمات'

    def __str__(self):
        return str(self.dispensing_date)


class VaccineDispensingItem(TimeStampedModel):
    ACTION_CHOICES = [
        ('dispensed', 'منصرف'),
        ('waste', 'هادر'),
        ('disposal', 'إعدام'),
    ]

    dispensing = models.ForeignKey(
        VaccineDispensing, on_delete=models.CASCADE,
        related_name='items'
    )
    medicine = models.ForeignKey(
        Medicine, on_delete=models.PROTECT,
        related_name='vaccine_dispensing_items'
    )
    batch = models.ForeignKey(
        Batch, on_delete=models.PROTECT,
        related_name='vaccine_dispensing_items'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    quantity_doses = models.PositiveIntegerField()
    vials_opened = models.PositiveIntegerField(default=0)
    syringe_half_ml_used = models.PositiveIntegerField(default=0)
    syringe_three_ml_used = models.PositiveIntegerField(default=0)
    vial_consumption = models.JSONField(default=dict, blank=True)
    created_vial_ids = models.JSONField(default=list, blank=True)
    syringe_consumption = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'صنف في حركة التطعيمات'
        verbose_name_plural = 'أصناف حركة التطعيمات'

    def __str__(self):
        return f'{self.medicine.name} - {self.get_action_display()}'

    def clean(self):
        if not self.medicine_id or not self.medicine.is_vaccine:
            raise ValidationError({'medicine': 'الصنف المحدد ليس تطعيماً'})
        if self.batch_id and self.batch.medicine_id != self.medicine_id:
            raise ValidationError({'batch': 'التشغيلة المختارة لا تنتمي إلى التطعيم المحدد'})
        if not self.quantity_doses:
            raise ValidationError({'quantity_doses': 'عدد الجرعات يجب أن يكون أكبر من الصفر'})


class StockDisposal(TimeStampedModel):
    dispensing_date = models.DateField()
    medicine = models.ForeignKey(
        Medicine, on_delete=models.PROTECT,
        related_name='stock_disposals'
    )
    batch = models.ForeignKey(
        Batch, on_delete=models.PROTECT,
        related_name='stock_disposals'
    )
    quantity = models.PositiveIntegerField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-dispensing_date', '-id']
        verbose_name = 'إعدام مخزون'
        verbose_name_plural = 'إعدامات المخزون'

    def clean(self):
        if self.batch_id and self.medicine_id and self.batch.medicine_id != self.medicine_id:
            raise ValidationError({'batch': 'التشغيلة لا تنتمي إلى الصنف المحدد'})
        if not self.quantity:
            raise ValidationError({'quantity': 'الكمية يجب أن تكون أكبر من الصفر'})


class InternalDispensing(TimeStampedModel):
    DESTINATION_CHOICES = [
        ('internal', 'جهة داخلية'),
        ('external', 'جهة خارجية'),
    ]

    dispensing_ref = models.CharField(max_length=20, unique=True, blank=True)
    dispensing_date = models.DateField()
    destination_type = models.CharField(
        max_length=20,
        choices=DESTINATION_CHOICES,
        default='internal',
    )
    destination_name = models.CharField(max_length=255)
    destination_reference = models.CharField(max_length=100, blank=True)
    destination_medicine = models.ForeignKey(
        Medicine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='internal_receipts',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-dispensing_date', '-id']
        indexes = [
            models.Index(fields=['dispensing_date', 'dispensing_ref']),
        ]
        verbose_name = 'منصرف داخلي'
        verbose_name_plural = 'المنصرف الداخلي'

    def __str__(self):
        return f'{self.dispensing_ref} - {self.destination_name}'

    def clean(self):
        if not self.destination_name.strip():
            raise ValidationError({'destination_name': 'اسم الجهة مطلوب'})

    def save(self, *args, **kwargs):
        if not self.dispensing_ref:
            last = InternalDispensing.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.dispensing_ref = f'ID-{next_num:04d}'
        super().save(*args, **kwargs)


class InternalDispensingItem(TimeStampedModel):
    dispensing = models.ForeignKey(
        InternalDispensing,
        on_delete=models.CASCADE,
        related_name='items',
    )
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name='internal_dispensing_items',
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.PROTECT,
        related_name='internal_dispensing_items',
    )
    destination_medicine = models.ForeignKey(
        Medicine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='internal_receipt_items',
    )
    destination_batch = models.ForeignKey(
        Batch,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='internal_destination_items',
    )
    quantity_dispensed = models.IntegerField()

    class Meta:
        verbose_name = 'صنف في المنصرف الداخلي'
        verbose_name_plural = 'أصناف المنصرف الداخلي'

    def __str__(self):
        return f'{self.dispensing.dispensing_ref} - {self.medicine.name}'

    def clean(self):
        if self.quantity_dispensed <= 0:
            raise ValidationError({
                'quantity_dispensed': 'يجب أن تكون الكمية المصروفة أكبر من الصفر'
            })
        if self.batch_id and self.medicine_id and self.batch.medicine_id != self.medicine_id:
            raise ValidationError({'batch': 'التشغيلة المختارة لا تنتمي إلى الصنف المحدد'})
        if self.destination_batch_id and self.destination_batch.medicine_id != self.destination_medicine_id:
            raise ValidationError({'destination_batch': 'تشغيلة الوجهة لا تنتمي إلى صنف الوجهة المحدد'})
    
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